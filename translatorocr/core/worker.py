"""Worker thread do pipeline.

Executa OCR e tradução fora da GUI thread, mantendo a janela responsiva. Os
backends são criados uma única vez na inicialização, reutilizados em cada captura.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

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
    finished_loading = pyqtSignal()

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._cfg = config
        self._pipeline = None

    @pyqtSlot()
    def initialize(self) -> None:
        """Carrega os modelos. Roda uma vez, já dentro da thread do worker."""
        from ..registry import build_pipeline

        self.started_loading.emit()
        try:
            self._pipeline = build_pipeline(self._cfg)
        except Exception as exc:
            log.exception("Falha ao inicializar o pipeline")
            self.failed.emit(str(exc))
            return
        self.finished_loading.emit()

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

    def __init__(self, config: Config) -> None:
        self.thread = QThread()
        self.worker = PipelineWorker(config)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.initialize)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.thread.quit()
        self.thread.wait(5000)
