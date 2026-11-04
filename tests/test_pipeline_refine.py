"""Segunda passada: a fila de balões, o contexto que cada um recebe e o caminho até a tela.

Pipeline e registro de verdade, com OCR, tradutor e refinador dublês. O que importa aqui
é qual balão vai para a segunda passada, com qual histórico, e que a tradução nova chega
ao bloco desenhado mesmo depois de outra leitura ter trocado os objetos.
"""

from __future__ import annotations

import numpy as np
import pytest

from translatorocr.config import Config
from translatorocr.core.ledger import BlockLedger
from translatorocr.core.pipeline import Pipeline
from translatorocr.models import Capture, Region, TextLine

FIRST = "Where are you going so late?"
SECOND = "Home, I guess."
ONE_WORD = "BANG"


class FakeCapture:
    def grab(self, region: Region | None = None) -> Capture:
        return Capture(image=np.zeros((10, 10, 3), dtype=np.uint8), origin=(0, 0))


class FakeOCR:
    """Uma linha por balão, 300 px entre eles, para o agrupamento não juntar dois."""

    def __init__(self, texts: list[str]) -> None:
        self.texts = texts

    def read(self, image: np.ndarray) -> list[TextLine]:
        return [
            TextLine(bbox=(100, 100 + 300 * i, 500, 130 + 300 * i), text=text, confidence=0.95)
            for i, text in enumerate(self.texts)
        ]


class EchoTranslator:
    def translate(self, texts: list[str], source: str, target: str) -> list[str | None]:
        return [f"nmt:{t}" for t in texts]


class FakeRefiner:
    def __init__(self, answer: str | None = "gemma") -> None:
        self.answer = answer
        self.calls: list[tuple[str, list[tuple[str, str]]]] = []

    def translate(self, text: str, history: list[tuple[str, str]]) -> str | None:
        self.calls.append((text, list(history)))
        return None if self.answer is None else f"{self.answer}:{text}"


@pytest.fixture
def ledger() -> BlockLedger:
    config = Config()
    return BlockLedger(config.ledger, config.scroll)


def make(ledger: BlockLedger, texts: list[str], refiner: FakeRefiner | None) -> Pipeline:
    return Pipeline(
        Config(),
        FakeCapture(),  # type: ignore[arg-type]
        FakeOCR(texts),
        EchoTranslator(),
        refiner=refiner,
        ledger=ledger,
    )


def drain(pipeline: Pipeline) -> list[bool]:
    results = []
    while pipeline.refining:
        results.append(pipeline.refine_next())
    return results


def test_traducao_da_segunda_passada_chega_ao_bloco_desenhado(ledger):
    pipeline = make(ledger, [FIRST], FakeRefiner())
    shown = pipeline.run()
    assert shown[0].translated == f"nmt:{FIRST}"

    assert drain(pipeline) == [True]
    assert ledger.refresh(shown)
    assert shown[0].translated == f"gemma:{FIRST}"


def test_cada_balao_recebe_os_anteriores_ja_com_a_traducao_da_segunda_passada(ledger):
    refiner = FakeRefiner()
    pipeline = make(ledger, [FIRST, SECOND], refiner)
    pipeline.run()
    drain(pipeline)

    assert refiner.calls == [
        (FIRST, []),
        (SECOND, [(FIRST, f"gemma:{FIRST}")]),
    ]


def test_balao_de_uma_palavra_fica_com_o_opus_mt(ledger):
    refiner = FakeRefiner()
    pipeline = make(ledger, [ONE_WORD], refiner)
    pipeline.run()

    assert not pipeline.refining
    assert refiner.calls == []


def test_balao_relido_nao_volta_para_a_fila(ledger):
    refiner = FakeRefiner()
    pipeline = make(ledger, [FIRST], refiner)
    pipeline.run()
    drain(pipeline)

    pipeline.run()
    assert not pipeline.refining
    assert len(refiner.calls) == 1


def test_leitura_no_meio_da_fila_nao_perde_a_traducao_nova(ledger):
    """A captura que entra entre dois balões troca os blocos desenhados por outros."""
    pipeline = make(ledger, [FIRST, SECOND], FakeRefiner())
    pipeline.run()
    assert pipeline.refine_next()

    shown = pipeline.run()
    assert [b.translated for b in shown] == [f"gemma:{FIRST}", f"nmt:{SECOND}"]

    assert pipeline.refine_next()
    assert ledger.refresh(shown)
    assert [b.translated for b in shown] == [f"gemma:{FIRST}", f"gemma:{SECOND}"]


def test_sem_resposta_da_gemma_fica_a_traducao_do_opus_mt(ledger):
    pipeline = make(ledger, [FIRST], FakeRefiner(answer=None))
    shown = pipeline.run()

    assert drain(pipeline) == [False]
    assert not ledger.refresh(shown)
    assert shown[0].translated == f"nmt:{FIRST}"


def test_balao_que_saiu_do_registro_e_pulado(ledger):
    """Outro capítulo recomeça o registro: o que estava na fila não é mais desta leitura."""
    refiner = FakeRefiner()
    pipeline = make(ledger, [FIRST], refiner)
    ledger.observe_title("capítulo 1")
    pipeline.run()
    ledger.observe_title("capítulo 2")

    assert drain(pipeline) == [False]
    assert refiner.calls == []


def test_sem_refinador_nao_ha_fila(ledger):
    pipeline = make(ledger, [FIRST], None)
    pipeline.run()
    assert not pipeline.refining
    assert not pipeline.refine_next()
