"""O laço do modo de leitura: captura contínua, mede a rolagem, avisa quando parou.

Vive numa thread só dele. A conta em si está em `core/tracker.py`, que é puro; aqui fica
o que é Qt e o que é estado do laço.

Por que uma thread separada da do pipeline: o pipeline leva ~0.5 s por rodada, e o laço
precisa de um quadro a cada 60 ms. Compartilhando a thread, as caixas congelariam por
meio segundo toda vez que a leitura rodasse — justamente quando o usuário acabou de
parar de rolar e está olhando. O `MSSCapture` guarda o objeto `mss` em `threading.local`,
então duas threads capturando ao mesmo tempo é seguro.

Três situações que o laço precisa distinguir, e que não são a mesma coisa:

* **Nada mudou** — tela parada. Conta para o "parou de rolar", e não gera nada.
* **Mudou e é rolagem** — translada as caixas.
* **Mudou e não é rolagem** — zoom, troca de página, conteúdo carregando. Aqui não há o
  que transladar, e insistir poria caixa em cima da arte errada: melhor limpar.

A diferença entre a primeira e a terceira não sai da confiança do deslocamento — uma
tela parada e lisa também reprova. Sai de olhar se os dois quadros são parecidos.
"""

from __future__ import annotations

import logging

import numpy as np
from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal, pyqtSlot

from ..config import Config
from ..models import Region
from .tracker import estimate_shift, prepare

log = logging.getLogger(__name__)


class ScrollTracker(QObject):
    """Acompanha a rolagem da região de captura."""

    # Deslocamento do conteúdo na tela, em pixels (negativo = subiu).
    moved = pyqtSignal(int)
    # A rolagem parou e há conteúdo novo para ler.
    settled = pyqtSignal()
    # O que aconteceu não é translação: o que está desenhado não vale mais.
    lost = pyqtSignal()

    def __init__(self, config: Config, capture=None) -> None:
        super().__init__()
        self._cfg = config
        self._scroll = config.scroll
        # Backend pronto, quando não é a tela (modo `--image`). O `StillCapture` só lê
        # a imagem e o deslocamento, então compartilhá-lo com a GUI thread é seguro.
        self._given_capture = capture
        self._capture = None
        self._timer: QTimer | None = None
        self._region: Region | None = None
        self._previous: np.ndarray | None = None
        self._still = 0
        # Houve movimento desde a última vez que o pipeline rodou. Sem isto, uma tela
        # parada dispararia leitura sem parar.
        self._dirty = True
        # Parte fracionária do deslocamento acumulada entre quadros: rolagem lenta
        # avança menos de 1 px por quadro, e truncar a cada quadro perderia tudo.
        self._residual = 0.0

    @pyqtSlot(object)
    def set_region(self, region: Region | None) -> None:
        """A região mudou (outro monitor, outra seleção): o quadro anterior não serve
        mais de comparação."""
        self._region = region
        self._previous = None

    @pyqtSlot()
    def start(self) -> None:
        if self._timer is not None:
            return
        if self._given_capture is not None:
            self._capture = self._given_capture
        else:
            from ..backends.capture_mss import MSSCapture

            self._capture = MSSCapture(monitor=self._cfg.capture.monitor)
        self._previous = None
        self._still = 0
        self._residual = 0.0
        # Já começa sujo para a primeira parada disparar uma leitura: ligar o modo tem
        # que traduzir o que está na tela, sem esperar o usuário rolar.
        self._dirty = True

        timer = QTimer(self)
        timer.setInterval(self._scroll.interval_ms)
        timer.timeout.connect(self._tick)
        timer.start()
        self._timer = timer
        log.debug("rastreio de rolagem iniciado (%d ms)", self._scroll.interval_ms)

    @pyqtSlot()
    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None
        if self._capture is not None and self._capture is not self._given_capture:
            self._capture.close()
        self._capture = None
        self._previous = None

    @pyqtSlot()
    def mark_read(self) -> None:
        """O pipeline terminou: só volta a disparar depois de novo movimento."""
        self._dirty = False

    def _tick(self) -> None:
        if self._capture is None:
            return
        try:
            shot = self._capture.grab(self._region)
        except Exception:
            log.exception("Falha ao capturar durante o rastreio")
            return
        if shot is None:
            return

        frame = prepare(shot.image, self._scroll.downscale)
        previous, self._previous = self._previous, frame
        if previous is None or previous.shape != frame.shape:
            return

        # Quadros praticamente iguais: a tela está parada. Vem antes da confiança do
        # deslocamento de propósito — parado e liso reprova na confiança, e tratar isso
        # como "perdi o rastro" apagaria a tela toda a 16 vezes por segundo.
        if float(np.abs(frame - previous).mean()) < self._scroll.min_change:
            self._count_still()
            return

        shift = estimate_shift(previous, frame, self._scroll)
        if not shift.trustworthy(self._scroll):
            log.debug(
                "rastreio perdido: dy=%.1f dx=%.1f resp=%.2f textura=%.1f",
                shift.dy,
                shift.dx,
                shift.response,
                shift.texture,
            )
            self._still = 0
            self._dirty = True
            self._residual = 0.0
            self.lost.emit()
            return

        # Rolagem lenta anda menos de 1 px por quadro; o resto fica acumulado para não
        # se perder no arredondamento. Enquanto não fecha um pixel inteiro, o quadro
        # conta como parado — 0.5 px por quadro é 8 px por segundo, que é estar parado.
        total = shift.dy + self._residual
        whole = round(total)
        self._residual = total - whole
        if not whole:
            self._count_still()
            return

        self._still = 0
        self._dirty = True
        self.moved.emit(whole)

    def _count_still(self) -> None:
        self._still += 1
        if self._still == self._scroll.settle_frames and self._dirty:
            self.settled.emit()


class ScrollThread:
    """Dono do par QThread + ScrollTracker, no mesmo molde de `WorkerThread`.

    A thread sobe junto com o app e fica ociosa; quem liga e desliga o laço é o timer,
    pelos slots `start`/`stop` do tracker. Subir e derrubar thread a cada F6 só traria
    corrida de desligamento sem ganho nenhum.
    """

    def __init__(self, config: Config, capture=None) -> None:
        self.thread = QThread()
        self.tracker = ScrollTracker(config, capture)
        self.tracker.moveToThread(self.thread)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.tracker.stop()
        self.thread.quit()
        self.thread.wait(2000)
