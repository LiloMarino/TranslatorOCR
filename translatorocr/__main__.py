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
from .core.ledger import BlockLedger
from .core.scroll import ScrollThread
from .core.tracker import merge_tracked, shift_blocks
from .core.worker import WorkerThread
from .models import Region
from .ui import console
from .ui.area_store import load_area, save_area
from .ui.commands import Command
from .ui.coords import screen_physical_region
from .ui.foreground import foreground_title
from .ui.hotkey import GlobalHotkeys
from .ui.overlay import OverlayWindow
from .ui.selection import SelectionOverlay
from .ui.tray import TrayIcon

log = logging.getLogger("translatorocr")

# PER_MONITOR_AWARE_V2. Sem isso o Windows mente sobre a resolução para o processo,
# o MSS e o Qt discordam sobre coordenadas, e a região capturada sai deslocada num
# display escalado.
DPI_AWARENESS_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)

# Tempo para a janela de seleção sair da tela antes de a área nova ser fotografada.
SELECTOR_GONE_MS = 150


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
        "--image",
        metavar="CAMINHO",
        help="roda contra uma imagem em vez da tela, numa janela própria — a roda do "
        "mouse rola a página. Serve para conferir leitura e tradução sem prender a "
        "máquina nem depender do que está aberto na frente.",
    )
    parser.add_argument(
        "--debug-dump",
        action="store_true",
        help="salva a captura com os bboxes desenhados, para conferir coordenadas e o "
        "que a captura enxergou",
    )
    parser.add_argument(
        "--collect",
        action="store_true",
        help="grava cada tela traduzida em eval/captures/, com o que o app leu, para os "
        "scripts de avaliação",
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
    # Para o rastreio, que vive na terceira thread.
    scroll_start = pyqtSignal()
    scroll_stop = pyqtSignal()
    scroll_region = pyqtSignal(object)
    scroll_read = pyqtSignal()

    def __init__(
        self,
        config: Config,
        screen: QScreen | None,
        verbose: bool,
        viewer=None,
        capture=None,
    ) -> None:
        super().__init__()
        self._cfg = config
        self._screen = screen or QApplication.primaryScreen()
        self._selected_region: Region | None = None
        if viewer is None:
            self._selected_region = load_area(
                config.capture.area_path, screen_physical_region(self._screen)
            )
        self._selector: SelectionOverlay | None = None
        self._loaded = False
        self._capture_started = 0.0
        # Modo de leitura: acompanha a rolagem em vez de traduzir um quadro só.
        self._scroll_on = False
        # Quanto a página andou desde que o modo ligou, e quanto tinha andado quando o
        # pipeline foi acionado. A diferença corrige o resultado que chega atrasado.
        self._scroll_offset = 0
        self._capture_offset = 0
        self._busy = False
        self._settle_pending = False

        # No modo `--image` a janela da imagem faz o papel do overlay: mesma interface,
        # desenhando as caixas nela mesma em vez de por cima da tela.
        self.overlay = viewer if viewer is not None else OverlayWindow(config.overlay)
        self._viewer = viewer
        self.overlay.cover_screen(self._screen)
        self.overlay.set_status("Carregando modelos...")
        self.overlay.show()

        self._outline_timer = QTimer(self)
        self._outline_timer.setSingleShot(True)
        self._outline_timer.setInterval(config.overlay.outline_ms)
        self._outline_timer.timeout.connect(self.overlay.hide_region_outline)

        self._current_blocks: list = []

        keys = config.hotkeys
        self.commands = [
            Command(
                keys.reading,
                "Tradução",
                "ligar/desligar a tradução — ela acompanha a rolagem e o que entra é "
                "traduzido sozinho quando você para",
                self._on_toggle_scroll,
                toggle=True,
            ),
            Command(
                keys.hide_translation,
                "Ocultar tradução",
                "ocultar/mostrar a tradução para conferir o original",
                self._on_toggle_translation,
                toggle=True,
            ),
            Command(
                keys.select_area,
                "Selecionar área",
                "selecionar área — clique e arraste; um clique sem arrastar volta à tela cheia",
                self._on_select_area,
            ),
            Command(None, "Traduzir uma vez", "", self._on_capture),
        ]
        self.quit_command = Command(None, "Sair", "", self.quit)

        # Histórico do que já foi lido: o worker o consulta antes de traduzir, e a GUI o
        # alimenta com a rolagem e com os momentos em que o rastreio se perde.
        self.ledger = BlockLedger(config.ledger, config.scroll)
        self.worker = WorkerThread(config, self._region_for_capture(), capture, self.ledger)
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

        self.scroll = ScrollThread(config, capture)
        self.scroll_start.connect(self.scroll.tracker.start)
        self.scroll_stop.connect(self.scroll.tracker.stop)
        self.scroll_region.connect(self.scroll.tracker.set_region)
        self.scroll_read.connect(self.scroll.tracker.mark_read)
        self.scroll.tracker.moved.connect(self._on_scrolled)
        self.scroll.tracker.settled.connect(self._on_settled)
        self.scroll.tracker.lost.connect(self._on_lost)
        self.scroll.start()

        self.hotkeys = GlobalHotkeys()
        self.hotkeys.install()
        for command in self.commands:
            if command.key and not self.hotkeys.register(command.key, command.run):
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
        console.ready(seconds, self.commands)
        if self._selected_region is not None:
            console.info(
                f"usando a área da sessão anterior — {self._cfg.hotkeys.select_area} troca"
            )
        self.tray.set_state("Pronto")
        message = f"Pronto — {self._cfg.hotkeys.reading} para traduzir"
        self.overlay.set_status(message)
        QTimer.singleShot(2500, lambda: self.overlay.clear_status(message))

    # -- comandos -----------------------------------------------------------

    def _on_capture(self) -> None:
        if not self._loaded or self._busy:
            return
        if not self._scroll_on and self.overlay.translation_hidden:
            # Quem pede uma tradução quer vê-la; com a tradução ligada as leituras são
            # automáticas e a escolha de ocultar permanece até o usuário mudá-la.
            self._set_translation_hidden(False)
        if not self.overlay.hidden_from_capture:
            # O overlay entraria na foto e o OCR releria a própria tradução.
            self.overlay.clear()
        # Lido a cada leitura, e não a cada quadro do rastreio.
        self.ledger.observe_title(foreground_title())
        if not self._scroll_on:
            # Sem rastreio de rolagem não há como comparar posições com a leitura anterior.
            self.ledger.lost()
        self.tray.set_state("Traduzindo...")
        self._capture_started = time.perf_counter()
        self._capture_offset = self._scroll_offset
        self._busy = True
        # O worker vive em outra thread; o sinal despacha a chamada pra lá em vez de
        # rodar a inferência aqui e travar a GUI. Sem área selecionada, a captura é a
        # tela escolhida inteira.
        self.capture_requested.emit(self._region_for_capture())

    def _on_toggle_translation(self) -> None:
        self._set_translation_hidden(not self.overlay.translation_hidden)

    def _set_translation_hidden(self, hidden: bool) -> None:
        # `_current_blocks` segue o tempo todo (rolagem, novas leituras): ocultar só
        # tira o desenho, então mostrar de novo já traz tudo em dia.
        self.overlay.set_translation_hidden(hidden)
        self.tray.set_checked(self._cfg.hotkeys.hide_translation, hidden)

    def _region_for_capture(self) -> Region:
        if self._viewer is not None:
            return self._viewer.capture_region()
        return self._selected_region or screen_physical_region(self._screen, work_area=True)

    def _on_select_area(self) -> None:
        if self._viewer is not None:
            console.info("seleção de área não se aplica ao modo --image")
            return
        selector = SelectionOverlay(self._screen, self._on_area_selected)
        selector.show()
        selector.activateWindow()
        self._selector = selector  # segura a referência viva até o callback fechar

    def _on_area_selected(self, region: Region | None) -> None:
        self._selected_region = region
        self._selector = None
        save_area(self._cfg.capture.area_path, region)
        self._on_capture_area_changed()

    def _on_capture_area_changed(self) -> None:
        self._current_blocks = []
        self.ledger.lost()
        self.overlay.clear()
        self.scroll_region.emit(self._region_for_capture())
        self._flash_outline()
        if self._scroll_on:
            # O rastreio só pede leitura depois de movimento, e a área nova está parada.
            QTimer.singleShot(SELECTOR_GONE_MS, self._on_settled)

    def _flash_outline(self) -> None:
        """Marca a área selecionada por alguns segundos. A tela cheia dispensa a borda."""
        if self._selected_region is None:
            self.overlay.hide_region_outline()
            return
        self.overlay.show_region_outline(self._selected_region)
        self._outline_timer.start()

    def _on_screen_chosen(self, screen: QScreen) -> None:
        if screen is self._screen:
            return
        self._screen = screen
        # A área selecionada era de outra tela; mantê-la capturaria o monitor errado.
        self._selected_region = None
        self.overlay.cover_screen(screen)
        self._on_capture_area_changed()
        console.info(f"capturando no monitor {QApplication.screens().index(screen) + 1}")

    # -- tradução ligada ----------------------------------------------------

    def _on_toggle_scroll(self) -> None:
        key = self._cfg.hotkeys.reading
        if not self._loaded:
            self.tray.set_checked(key, False)
            return
        if not self._scroll_on and not self.overlay.hidden_from_capture:
            # Sem esconder o overlay da captura, cada quadro veria as próprias caixas
            # paradas e a medição da rolagem sairia errada (ver `ui/overlay.py`).
            console.error(
                "acompanhar a rolagem precisa esconder o overlay da captura, e o Windows "
                "recusou nesta máquina; use Traduzir uma vez, no ícone da bandeja."
            )
            self.tray.set_checked(key, False)
            return

        self._scroll_on = not self._scroll_on
        self.tray.set_checked(key, self._scroll_on)
        self._set_translation_hidden(False)
        if self._scroll_on:
            self._scroll_offset = 0
            self._capture_offset = 0
            self.ledger.lost()
            self.scroll_region.emit(self._region_for_capture())
            self.scroll_start.emit()
            self._flash_outline()
            self.tray.set_state("Acompanhando a rolagem")
            console.info("tradução ligada — role à vontade")
        else:
            self.scroll_stop.emit()
            self._current_blocks = []
            self.overlay.clear()
            self.tray.set_state("Pronto")
            console.info("tradução desligada")

    def _on_scrolled(self, dy: int) -> None:
        self._scroll_offset += dy
        self.ledger.scrolled(dy)
        region = self._region_for_capture()
        had_blocks = bool(self._current_blocks)
        shifted = shift_blocks(self._current_blocks, dy, region)
        # O que o registro conhece e voltou à viewport é redesenhado sem OCR.
        self._current_blocks = [*shifted, *self.ledger.restore(region, shifted)]
        if had_blocks or self._current_blocks:
            self.overlay.set_blocks(self._current_blocks)

    def _on_settled(self) -> None:
        if not self._scroll_on:
            return
        if self._busy:
            # Rolou e parou de novo enquanto a leitura anterior corria. Perder isto
            # deixaria o que entrou na tela sem tradução até o próximo movimento.
            self._settle_pending = True
            return
        self._on_capture()

    def _on_lost(self) -> None:
        """Zoom, troca de página, conteúdo recarregando: o que está desenhado não
        descreve mais a tela, e arrastar as caixas seria pior que limpar."""
        self.ledger.lost()
        if self._current_blocks:
            self._current_blocks = []
            self.overlay.clear()

    # -- resultado ----------------------------------------------------------

    def _on_ready(self, blocks: list) -> None:
        self._busy = False
        self.tray.set_state("Acompanhando a rolagem" if self._scroll_on else "Pronto")
        seconds = time.perf_counter() - self._capture_started

        if self._scroll_on:
            # A página pode ter rolado enquanto o pipeline rodava: a leitura descreve a
            # viewport de meio segundo atrás, então entra corrigida pelo que andou desde
            # o pedido.
            drift = self._scroll_offset - self._capture_offset
            region = self._region_for_capture()
            fresh = shift_blocks(blocks, drift, region) if drift else blocks
            self._current_blocks = merge_tracked(self._current_blocks, fresh, self._cfg.scroll)
            self.scroll_read.emit()
            if self._settle_pending:
                self._settle_pending = False
                QTimer.singleShot(0, self._on_settled)
            console.translated(
                len(self._current_blocks),
                sum(1 for b in self._current_blocks if b.needs_review),
                seconds,
            )
            self.overlay.set_blocks(self._current_blocks)
            return

        self._current_blocks = blocks
        console.translated(len(blocks), sum(1 for b in blocks if b.needs_review), seconds)
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
        self._busy = False
        console.error(message)
        self.tray.set_state("Erro")
        self.overlay.set_status(f"Erro: {message}")

    def quit(self) -> None:
        self.hotkeys.unregister_all()
        self.tray.hide()
        self.scroll.stop()
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
    config.collect = args.collect

    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)

    screens = app.screens()
    screen = screens[args.monitor - 1] if 1 <= args.monitor <= len(screens) else None
    if screen is None:
        log.warning(
            "Monitor %d não existe (há %d); usando o principal.", args.monitor, len(screens)
        )

    console.header()
    if config.collect:
        console.info(f"gravando as telas traduzidas em {config.collector.root}")
    viewer, capture = _build_image_mode(args.image, config)
    controller = App(config, screen, args.verbose, viewer=viewer, capture=capture)
    try:
        return app.exec()
    finally:
        controller.quit()


def _build_image_mode(path: str | None, config: Config):
    """No `--image`, a fonte da captura é o arquivo e a janela da imagem faz o papel
    do overlay. Fora dele, os dois são `None` e o app segue normal."""
    if not path:
        return None, None
    from pathlib import Path

    from .backends.capture_still import StillCapture
    from .ui.viewer import ImageViewer

    capture = StillCapture()
    capture.load(path)
    console.info(f"lendo de {Path(path).name} — a tela não participa")
    return ImageViewer(config.overlay, capture, Path(path).name), capture


if __name__ == "__main__":
    raise SystemExit(main())
