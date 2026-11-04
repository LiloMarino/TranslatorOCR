"""Worker thread do pipeline.

Executa OCR e tradução fora da GUI thread, mantendo a janela responsiva. Os
backends são criados uma única vez na inicialização, reutilizados em cada captura.
"""

from __future__ import annotations

import logging
import time

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal, pyqtSlot

from .. import assets
from ..config import Config
from ..models import Region
from .ledger import BlockLedger

log = logging.getLogger(__name__)


class PipelineWorker(QObject):
    # Os blocos e o deslocamento da rolagem em que a leitura começou.
    ready = pyqtSignal(list, int)  # list[TextBlock], int
    # A segunda passada trocou a tradução de um balão no registro.
    refined = pyqtSignal()
    failed = pyqtSignal(str)
    started_loading = pyqtSignal()
    # Texto curto do que está acontecendo durante a carga ("Baixando tradutor offline
    # (445 MB)... 42%"), para o console e o overlay.
    loading_progress = pyqtSignal(str)
    finished_loading = pyqtSignal(float)  # segundos desde o início da carga

    def __init__(
        self,
        config: Config,
        warmup_region: Region | None = None,
        capture=None,
        ledger: BlockLedger | None = None,
    ) -> None:
        super().__init__()
        self._cfg = config
        # A mesma região que a captura vai usar: o aquecimento só vale para o formato
        # de entrada que ele viu (ver `Pipeline.warmup`).
        self._warmup_region = warmup_region
        # Backend de captura pronto, quando não é a tela (modo `--image`).
        self._capture = capture
        # O registro é do `App`, que o alimenta com a rolagem; o pipeline o consulta.
        self._ledger = ledger
        self._pipeline = None
        self._refine_scheduled = False

    @pyqtSlot()
    def initialize(self) -> None:
        """Baixa o que faltar, carrega os modelos e aquece a GPU. Roda uma vez, já
        dentro da thread do worker."""
        from ..registry import build_pipeline

        started = time.perf_counter()
        self.started_loading.emit()
        self._download_missing()
        self.loading_progress.emit("Carregando modelos...")
        try:
            self._pipeline = build_pipeline(self._cfg, self._capture, self._ledger)
            self._pipeline.warmup(self._warmup_region)
        except Exception as exc:
            log.exception("Falha ao inicializar o pipeline")
            self.failed.emit(str(exc))
            return
        self.finished_loading.emit(time.perf_counter() - started)

    def _download_missing(self) -> None:
        """Primeira execução: baixa o detector, o NMT e o TranslateGemma."""
        groups = ["detector", "nmt"] + (["translategemma"] if self._cfg.refine.enabled else [])
        if not assets.missing(groups):
            return

        current = ""
        last_emit = 0.0

        def on_start(group: str, asset: assets.Asset) -> None:
            nonlocal current
            current = f"Baixando {assets.LABELS[group]} ({assets.human(asset.size)})"
            self.loading_progress.emit(f"{current}...")

        def on_progress(done: int, total: int, _rate: float) -> None:
            nonlocal last_emit
            now = time.perf_counter()
            # Um sinal por pedaço de 1 MB inundaria a fila do Qt à toa.
            if now - last_emit >= 0.25 or done >= total:
                last_emit = now
                self.loading_progress.emit(f"{current}... {done / max(1, total):.0%}")

        failed = assets.ensure(groups, on_start, on_progress)
        if failed:
            # Sem rede: o registry segue sem o detector e sem a segunda passada, e avisa
            # no log. Sem o tradutor ele levanta, e a falha chega ao usuário pelo `failed`.
            names = ", ".join(assets.LABELS[g] for g in failed)
            self.loading_progress.emit(f"Não foi possível baixar: {names}. Seguindo sem.")

    @pyqtSlot(object)
    def capture(self, region: Region | None = None) -> None:
        """Slot registrado — conectado por sinal a partir da GUI thread.

        `@pyqtSlot(object)` (em vez de `@pyqtSlot(Region)`) porque `Region` não é um
        tipo Qt registrado; o Qt só usa isso pra decidir despachar entre threads via
        fila, e aceita qualquer objeto Python nesse papel — a anotação Python do
        parâmetro continua `Region | None` normalmente.
        """
        if self._pipeline is None:
            self.failed.emit("Pipeline ainda não inicializado.")
            return
        offset = self._ledger.offset if self._ledger else 0
        try:
            blocks = self._pipeline.run(region)
        except Exception as exc:
            log.exception("Falha durante a captura")
            self.failed.emit(str(exc))
            return
        self.ready.emit(blocks, offset)
        self._schedule_refine()

    def _schedule_refine(self) -> None:
        """Agenda o próximo balão da segunda passada para a volta seguinte do loop.

        Um balão por volta: o pedido de captura que chegar enquanto a Gemma traduz entra
        na fila do Qt antes do próximo balão, e espera no máximo um. OCR e Gemma nunca
        disputam a GPU, porque os dois rodam nesta thread.
        """
        if self._refine_scheduled or self._pipeline is None or not self._pipeline.refining:
            return
        self._refine_scheduled = True
        QTimer.singleShot(0, self._refine_step)

    def _refine_step(self) -> None:
        self._refine_scheduled = False
        if self._pipeline is None:
            return
        try:
            changed = self._pipeline.refine_next()
        except Exception:
            log.exception("Falha na segunda passada")
            changed = False
        if changed:
            self.refined.emit()
        self._schedule_refine()


class WorkerThread:
    """Dono do par QThread + PipelineWorker, com desligamento ordenado."""

    def __init__(
        self,
        config: Config,
        warmup_region: Region | None = None,
        capture=None,
        ledger: BlockLedger | None = None,
    ) -> None:
        self.thread = QThread()
        self.worker = PipelineWorker(config, warmup_region, capture, ledger)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.initialize)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.thread.quit()
        self.thread.wait(5000)
