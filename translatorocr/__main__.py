"""Entrypoint.

Ordem importa: DPI awareness **antes** do QApplication, e `preload_dlls` do
onnxruntime antes de qualquer sessão de inferência.
"""

from __future__ import annotations

import argparse
import ctypes
import logging
import sys
import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QScreen
from PyQt6.QtWidgets import QApplication

from .backends._ort import preload_cuda_dlls
from .config import Config
from .core.worker import WorkerThread
from .models import Region
from .ui import console
from .ui.commands import Command
from .ui.coords import screen_physical_region
from .ui.hotkey import GlobalHotkeys
from .ui.overlay import OverlayWindow
from .ui.selection import SelectionOverlay
from .ui.tray import TrayIcon

log = logging.getLogger("translatorocr")

# PER_MONITOR_AWARE_V2. Sem isso o Windows mente sobre a resolução para o processo,
# o MSS e o Qt discordam sobre coordenadas, e a região capturada sai deslocada num
# display escalado.
DPI_AWARENESS_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)


def enable_dpi_awareness() -> None:
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_PER_MONITOR_AWARE_V2)
    except Exception:  # noqa: BLE001 — Windows < 10 1703
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:  # noqa: BLE001
            log.warning("Não foi possível declarar DPI awareness; coordenadas podem sair erradas.")


def set_verbose(on: bool) -> None:
    """Detalhes internos no console. Desligado, só aviso e erro aparecem."""
    logging.getLogger().setLevel(logging.INFO if on else logging.WARNING)
    log.setLevel(logging.DEBUG if on else logging.WARNING)
    console.inline_progress = not on


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="translatorocr", description=__doc__)
    parser.add_argument(
        "--monitor",
        type=int,
        default=1,
        help="em qual monitor capturar, a partir de 1 (default: o principal). "
        "Também dá para trocar pelo ícone da bandeja.",
    )
    parser.add_argument(
        "--debug-dump",
        action="store_true",
        help="salva a captura com os bboxes desenhados, para conferir coordenadas",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="mostra os detalhes internos no console"
    )
    return parser.parse_args(argv)


class App(QObject):
    """Controlador da GUI thread.

    Precisa ser QObject: os sinais do worker são emitidos de outra thread, e é a
    afinidade de thread de um QObject receptor que faz o Qt escolher
    QueuedConnection. Com um objeto Python comum a conexão vira direta e os updates
    de overlay executariam na thread do worker — acesso a widget fora da GUI thread.
    """

    # `region` é `Region | None`; `object` porque `Region` não é tipo Qt registrado
    # (ver nota em `PipelineWorker.capture`).
    capture_requested = pyqtSignal(object)

    def __init__(self, config: Config, screen: QScreen | None, verbose: bool) -> None:
        super().__init__()
        self._cfg = config
        self._screen = screen or QApplication.primaryScreen()
        self._selected_region: Region | None = None
        self._outline_visible = False
        self._selector: SelectionOverlay | None = None
        self._loaded = False
        self._capture_started = 0.0
        self.overlay = OverlayWindow(config.overlay)
        self.overlay.cover_screen(self._screen)
        self.overlay.set_status("Carregando modelos...")
        self.overlay.show()

        self._current_blocks: list = []

        keys = config.hotkeys
        self.commands = [
            Command(
                keys.capture,
                "Traduzir",
                "traduzir a tela (ou a área selecionada)",
                self._on_capture,
            ),
            Command(
                keys.select_area,
                "Selecionar área",
                "selecionar área — clique e arraste; um clique sem arrastar volta à tela cheia",
                self._on_select_area,
            ),
            Command(
                keys.show_region_outline,
                "Mostrar área",
                f"mostrar/esconder a borda da área que o {keys.capture} captura",
                self._on_toggle_outline,
                toggle=True,
            ),
            Command(keys.dismiss, "Limpar", "limpar a tradução da tela", self.overlay.clear),
        ]
        self.quit_command = Command(keys.quit, "Sair", "sair", self.quit)

        self.worker = WorkerThread(config, self._region_for_capture())
        self.worker.worker.ready.connect(self._on_ready)
        self.worker.worker.refined.connect(self._on_refined)
        self.worker.worker.failed.connect(self._on_failed)
        self.worker.worker.loading_progress.connect(self._on_loading_progress)
        self.worker.worker.finished_loading.connect(self._on_loaded)
        # Conexão entre threads: como o receptor (`PipelineWorker`) tem afinidade com
        # a thread do worker, o Qt escolhe QueuedConnection sozinho — mesma razão
        # pela qual `App` precisa ser QObject (ver docstring da classe).
        self.capture_requested.connect(self.worker.worker.capture)
        self.worker.start()

        self.hotkeys = GlobalHotkeys()
        self.hotkeys.install()
        for command in [*self.commands, self.quit_command]:
            if not self.hotkeys.register(command.key, command.run):
                console.error(
                    f"a tecla {command.key} ({command.label.lower()}) já está em uso por "
                    "outro programa; use o ícone da bandeja para esse comando."
                )

        self.tray = TrayIcon(
            self.commands,
            self.quit_command,
            current_screen=lambda: self._screen,
            on_screen=self._on_screen_chosen,
            on_verbose=set_verbose,
            verbose=verbose,
        )
        self.tray.show()

    # -- carga --------------------------------------------------------------

    def _on_loading_progress(self, message: str) -> None:
        console.progress(message)
        self.overlay.set_status(message)
        self.tray.set_state(message)

    def _on_loaded(self, seconds: float) -> None:
        self._loaded = True
        console.ready(seconds, [*self.commands, self.quit_command])
        self.tray.set_state("Pronto")
        message = f"Pronto — {self._cfg.hotkeys.capture} para traduzir"
        self.overlay.set_status(message)
        QTimer.singleShot(2500, lambda: self.overlay.clear_status(message))

    # -- comandos -----------------------------------------------------------

    def _on_capture(self) -> None:
        if not self._loaded:
            return
        self.overlay.clear()
        self.tray.set_state("Traduzindo...")
        self._capture_started = time.perf_counter()
        # O worker vive em outra thread; o sinal despacha a chamada pra lá em vez de
        # rodar a inferência aqui e travar a GUI. Sem área selecionada, a captura é a
        # tela escolhida inteira.
        self.capture_requested.emit(self._region_for_capture())

    def _region_for_capture(self) -> Region:
        return self._selected_region or screen_physical_region(self._screen, work_area=True)

    def _on_select_area(self) -> None:
        selector = SelectionOverlay(self._screen, self._on_area_selected)
        selector.show()
        selector.activateWindow()
        self._selector = selector  # segura a referência viva até o callback fechar

    def _on_area_selected(self, region: Region | None) -> None:
        self._selected_region = region
        self._selector = None
        if self._outline_visible:
            self._show_outline()

    def _show_outline(self) -> None:
        self.overlay.show_region_outline(self._region_for_capture())

    def _on_toggle_outline(self) -> None:
        self._outline_visible = not self._outline_visible
        self.tray.set_checked(self._cfg.hotkeys.show_region_outline, self._outline_visible)
        if self._outline_visible:
            self._show_outline()
        else:
            self.overlay.hide_region_outline()

    def _on_screen_chosen(self, screen: QScreen) -> None:
        if screen is self._screen:
            return
        self._screen = screen
        # A área selecionada era de outra tela; mantê-la capturaria o monitor errado.
        self._selected_region = None
        self.overlay.clear()
        self.overlay.cover_screen(screen)
        if self._outline_visible:
            self._show_outline()
        console.info(f"capturando no monitor {QApplication.screens().index(screen) + 1}")

    # -- resultado ----------------------------------------------------------

    def _on_ready(self, blocks: list) -> None:
        self._current_blocks = blocks
        self.tray.set_state("Pronto")
        console.translated(
            len(blocks),
            sum(1 for b in blocks if b.needs_review),
            time.perf_counter() - self._capture_started,
        )
        if not blocks:
            message = "Nenhum texto encontrado"
            self.overlay.set_status(message)
            QTimer.singleShot(1500, lambda: self.overlay.clear_status(message))
            return
        self.overlay.set_blocks(blocks)

    def _on_refined(self, changed: list) -> None:
        """`changed` são os mesmos objetos `TextBlock` de `_current_blocks` — um
        sinal Qt tipado `list` carrega a referência Python através da fila entre
        threads, não uma cópia — então `block.translated` já está atualizado por
        identidade; só falta mandar o overlay redesenhar."""
        if changed:
            self.overlay.set_blocks(self._current_blocks)

    def _on_failed(self, message: str) -> None:
        console.error(message)
        self.tray.set_state("Erro")
        self.overlay.set_status(f"Erro: {message}")

    def quit(self) -> None:
        self.hotkeys.unregister_all()
        self.tray.hide()
        self.worker.stop()
        QApplication.quit()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    console.setup()
    logging.basicConfig(format="%(levelname)s %(name)s: %(message)s")
    set_verbose(args.verbose)

    enable_dpi_awareness()
    preload_cuda_dlls()

    config = Config()
    if args.debug_dump:
        config.debug_dump = True

    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)

    screens = app.screens()
    screen = screens[args.monitor - 1] if 1 <= args.monitor <= len(screens) else None
    if screen is None:
        log.warning(
            "Monitor %d não existe (há %d); usando o principal.", args.monitor, len(screens)
        )

    console.header()
    controller = App(config, screen, args.verbose)
    try:
        return app.exec()
    finally:
        controller.quit()


if __name__ == "__main__":
    raise SystemExit(main())
