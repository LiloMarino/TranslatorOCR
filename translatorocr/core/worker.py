"""Worker thread do pipeline.

Executa OCR e tradução fora da GUI thread, mantendo a janela responsiva. Os
backends são criados uma única vez na inicialização, reutilizados em cada captura.
"""

from __future__ import annotations

import logging
import time

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from .. import assets
from ..config import Config
from ..models import Region

log = logging.getLogger(__name__)


class PipelineWorker(QObject):
    ready = pyqtSignal(list)  # list[TextBlock]
    # Emitido depois de `ready`, só quando há bloco `needs_review` e LLM está
    # configurado — carrega só os blocos que o refino de fato mudou, para o overlay
    # atualizar in-place sem recriar o resto (ver ui/overlay.py:set_blocks).
    refined = pyqtSignal(list)  # list[TextBlock]
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
    ) -> None:
        super().__init__()
        self._cfg = config
        # A mesma região que a captura vai usar: o aquecimento só vale para o formato
        # de entrada que ele viu (ver `Pipeline.warmup`).
        self._warmup_region = warmup_region
        # Backend de captura pronto, quando não é a tela (modo `--image`).
        self._capture = capture
        self._pipeline = None

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
            self._pipeline = build_pipeline(self._cfg, self._capture)
            self._pipeline.warmup(self._warmup_region)
        except Exception as exc:
            log.exception("Falha ao inicializar o pipeline")
            self.failed.emit(str(exc))
            return
        self.finished_loading.emit(time.perf_counter() - started)

    def _download_missing(self) -> None:
        """Primeira execução: baixa o detector e o NMT. O LLM fica de fora — está
        desligado por padrão e são 2.5 GB."""
        groups = ["detector", "nmt"] + (["llm"] if self._cfg.llm.enabled else [])
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
            # Sem rede: o registry segue sem o que faltou (sem detector, ou tradução
            # pela nuvem) e avisa no log — não é motivo para não abrir.
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
        try:
            blocks = self._pipeline.run(region)
            self.ready.emit(blocks)
        except Exception as exc:
            log.exception("Falha durante a captura")
            self.failed.emit(str(exc))
            return

        # Roda depois do ready.emit, na mesma thread: o LLM é lento, então fica
        # fora do caminho crítico de latência. Só existe trabalho aqui quando há
        # bloco needs_review e LLM está configurado — Pipeline.refine() já devolve
        # lista vazia nos outros casos.
        try:
            changed = self._pipeline.refine(blocks)
        except Exception:
            log.exception("Falha durante o refino por LLM")
            return
        if changed:
            self.refined.emit(changed)


class WorkerThread:
    """Dono do par QThread + PipelineWorker, com desligamento ordenado."""

    def __init__(self, config: Config, warmup_region: Region | None = None, capture=None) -> None:
        self.thread = QThread()
        self.worker = PipelineWorker(config, warmup_region, capture)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.initialize)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.thread.quit()
        self.thread.wait(5000)
