"""O laço do rastreio: quando ele pede leitura.

Os quadros vêm de uma captura falsa sobre a página sintética de `test_tracker`, e o laço
é acionado quadro a quadro, sem timer nem event loop.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QCoreApplication
from test_tracker import textured, viewport

from translatorocr.config import Config
from translatorocr.core.scroll import ScrollTracker
from translatorocr.models import Capture


class FakeCapture:
    def __init__(self) -> None:
        self.page = textured(3000)
        self.top = 100

    def grab(self, region=None) -> Capture:
        return Capture(image=viewport(self.page, self.top).copy(), origin=(0, 0), scale=1.0)


@pytest.fixture
def tracker():
    _app = QCoreApplication.instance() or QCoreApplication([])
    capture = FakeCapture()
    tracker = ScrollTracker(Config(), capture)
    tracker.start()
    settled: list[int] = []
    tracker.settled.connect(lambda: settled.append(capture.top))
    yield tracker, capture, settled
    tracker.stop()


def run(tracker: ScrollTracker, capture: FakeCapture, frames: int, step: int = 0) -> None:
    for _ in range(frames):
        capture.top += step
        tracker._tick()


def test_tela_parada_pede_uma_leitura_so(tracker):
    tracker, capture, settled = tracker
    run(tracker, capture, 30)
    assert settled == [100]


def test_rolagem_durante_a_leitura_pede_outra_na_parada_seguinte(tracker):
    """A leitura pedida na primeira parada ainda corre enquanto a página rola, e termina
    antes da segunda parada. É essa segunda parada que traduz o que entrou na tela."""
    tracker, capture, settled = tracker
    run(tracker, capture, 6)
    run(tracker, capture, 5, step=20)
    run(tracker, capture, 6)
    assert settled == [100, 200]
