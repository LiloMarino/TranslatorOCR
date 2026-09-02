"""Entrypoint.

Ordem importa: DPI awareness **antes** do QApplication, e `preload_dlls` do
onnxruntime antes de qualquer sessão de inferência.
"""

from __future__ import annotations

import argparse
import ctypes
import logging
import sys

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

from .config import Config, load_config
from .core.worker import WorkerThread
from .models import Region
from .ui.coords import screen_physical_region
from .ui.hotkey import GlobalHotkeys
from .ui.overlay import OverlayWindow
from .ui.selection import SelectionOverlay

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


def preload_onnx_dlls() -> None:
    """Carrega os DLLs de CUDA/cuDNN dos pacotes pip da NVIDIA.

    Sem esta chamada o ORT não acha `cudnn64_9.dll` e a inferência estoura em
    runtime com NOT_IMPLEMENTED no primeiro Conv — mesmo com o CUDAExecutionProvider
    aparecendo na lista de providers disponíveis.
    """
    try:
        import onnxruntime as ort

        if hasattr(ort, "preload_dlls"):
            ort.preload_dlls()
    except Exception:
        log.exception("Falha ao pré-carregar os DLLs do onnxruntime")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="translatorocr", description=__doc__)
    parser.add_argument("-c", "--config", help="caminho do config.toml")
    parser.add_argument(
        "--debug-dump",
        action="store_true",
        help="salva a captura com os bboxes desenhados, para conferir coordenadas",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
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

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._cfg = config
        self._selected_region: Region | None = None
        self._outline_visible = False
        self._selector: SelectionOverlay | None = None
        self.overlay = OverlayWindow(config.overlay)
        self.overlay.cover_screen()
        self.overlay.set_status("Carregando modelos...")
        self.overlay.show()

        self._current_blocks: list = []

        self.worker = WorkerThread(config)
        self.worker.worker.ready.connect(self._on_ready)
        self.worker.worker.refined.connect(self._on_refined)
        self.worker.worker.failed.connect(self._on_failed)
        self.worker.worker.finished_loading.connect(self._on_loaded)
        # Conexão entre threads: como o receptor (`PipelineWorker`) tem afinidade com
        # a thread do worker, o Qt escolhe QueuedConnection sozinho — mesma razão
        # pela qual `App` precisa ser QObject (ver docstring da classe).
        self.capture_requested.connect(self.worker.worker.capture)
        self.worker.start()

        self.hotkeys = GlobalHotkeys()
        self.hotkeys.install()
        self.hotkeys.register(config.hotkeys.capture, self._on_capture)
        self.hotkeys.register(config.hotkeys.dismiss, self.overlay.clear)
        self.hotkeys.register(config.hotkeys.quit, self.quit)
        self.hotkeys.register(config.hotkeys.select_area, self._on_select_area)
        self.hotkeys.register(config.hotkeys.show_region_outline, self._on_toggle_outline)

    def _on_loaded(self) -> None:
        keys = self._cfg.hotkeys
        log.info(
            "Pronto. %s captura · %s dispensa · %s sai.",
            keys.capture,
            keys.dismiss,
            keys.quit,
        )
        self.overlay.set_status(f"Pronto — {keys.capture} para traduzir")
        QTimer.singleShot(2500, self.overlay.clear)

    def _on_capture(self) -> None:
        self.overlay.clear()
        # O worker vive em outra thread; o sinal despacha a chamada pra lá em vez de
        # rodar a inferência aqui e travar a GUI. `_selected_region` é `None`
        # por padrão — tela cheia — a menos que F11 tenha delimitado uma área.
        self.capture_requested.emit(self._selected_region)

    def _current_screen(self):
        return self.overlay.screen() or QApplication.primaryScreen()

    def _on_select_area(self) -> None:
        selector = SelectionOverlay(self._current_screen(), self._on_area_selected)
        selector.show()
        selector.activateWindow()
        self._selector = selector  # segura a referência viva até o callback fechar

    def _on_area_selected(self, region: Region | None) -> None:
        self._selected_region = region
        self._selector = None
        if self._outline_visible:
            self._show_outline()

    def _region_for_outline(self) -> Region:
        return self._selected_region or screen_physical_region(self._current_screen())

    def _show_outline(self) -> None:
        self.overlay.show_region_outline(self._region_for_outline())

    def _on_toggle_outline(self) -> None:
        self._outline_visible = not self._outline_visible
        if self._outline_visible:
            self._show_outline()
        else:
            self.overlay.hide_region_outline()

    def _on_ready(self, blocks: list) -> None:
        self._current_blocks = blocks
        if not blocks:
            self.overlay.set_status("Nenhum texto encontrado")
            QTimer.singleShot(1500, self.overlay.clear)
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
        log.error("%s", message)
        self.overlay.set_status(f"Erro: {message}")

    def quit(self) -> None:
        self.hotkeys.unregister_all()
        self.worker.stop()
        QApplication.quit()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    enable_dpi_awareness()
    preload_onnx_dlls()

    config = load_config(args.config)
    if args.debug_dump:
        config.debug_dump = True

    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    controller = App(config)
    try:
        return app.exec()
    finally:
        controller.quit()


if __name__ == "__main__":
    raise SystemExit(main())
