"""Registro de balões: casamento por posição, reancoragem, contexto e reinícios.

Lógica pura sobre blocos sintéticos, sem OCR nem tela. O que importa aqui é quando uma
tradução guardada vale para uma leitura nova e quando ela tem que ceder.
"""

from __future__ import annotations

import numpy as np
import pytest

from translatorocr.config import Config, LedgerConfig, ScrollConfig
from translatorocr.core.ledger import BlockLedger
from translatorocr.core.pipeline import Pipeline
from translatorocr.models import Capture, Region, TextBlock, TextLine

LONG = "Where are you going so late?"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def ledger(clock: Clock) -> BlockLedger:
    return BlockLedger(LedgerConfig(), ScrollConfig(), clock)


def block(
    top: int,
    text: str = LONG,
    *,
    partial: bool = False,
    review: bool = False,
    translated: str | None = None,
) -> TextBlock:
    bbox = (100, top, 400, top + 60)
    line = TextLine(bbox=bbox, text=text, confidence=0.9, partial=partial)
    return TextBlock(
        bbox=bbox,
        source=text,
        confidence=0.9,
        lines=[line],
        translated=translated,
        needs_review=review,
    )


def read(ledger: BlockLedger, blocks: list[TextBlock]) -> list[TextBlock]:
    """Uma rodada completa: o que o tradutor recebe, traduzido e registrado."""
    reading = ledger.begin()
    pending = ledger.reconcile(reading, blocks)
    for item in pending:
        item.translated = f"pt:{item.source}"
    ledger.record(reading, pending)
    return pending


# -- casamento por posição ----------------------------------------------------


def test_balao_conhecido_nao_e_retraduzido(ledger: BlockLedger):
    assert len(read(ledger, [block(300)])) == 1

    again = block(300)
    assert read(ledger, [again]) == []
    assert again.translated == f"pt:{LONG}"


def test_posicao_acompanha_a_rolagem(ledger: BlockLedger):
    read(ledger, [block(300)])

    ledger.scrolled(-120)
    moved = block(180)
    assert read(ledger, [moved]) == []
    assert moved.translated == f"pt:{LONG}"


def test_primeira_leitura_inteira_fica_mesmo_que_o_ocr_leia_diferente(ledger: BlockLedger):
    read(ledger, [block(300)])

    misread = block(300, "Where are you going so Iate?")
    assert read(ledger, [misread]) == []
    assert misread.source == LONG
    assert misread.translated == f"pt:{LONG}"


def test_leitura_cortada_nao_apaga_a_inteira(ledger: BlockLedger):
    read(ledger, [block(300)])

    cut = block(300, "Where are you", partial=True)
    assert read(ledger, [cut]) == []
    assert cut.source == LONG


def test_entrada_cortada_cede_a_leitura_inteira(ledger: BlockLedger):
    read(ledger, [block(300, "Where are you", partial=True)])

    whole = block(300)
    assert read(ledger, [whole]) == [whole]
    # Substitui no lugar: a entrada não se duplica.
    again = block(300)
    assert read(ledger, [again]) == []
    assert again.source == LONG


def test_entrada_cortada_com_o_mesmo_texto_e_reaproveitada(ledger: BlockLedger):
    read(ledger, [block(300, partial=True)])

    whole = block(300)
    assert read(ledger, [whole]) == []
    assert whole.translated == f"pt:{LONG}"


def test_entrada_duvidosa_cede_a_leitura_limpa(ledger: BlockLedger):
    read(ledger, [block(300, "Where are y0u going", review=True)])

    clean = block(300)
    assert read(ledger, [clean]) == [clean]


def test_balao_em_outra_posicao_e_novo(ledger: BlockLedger):
    read(ledger, [block(300)])

    other = block(900, "Another line entirely.")
    assert read(ledger, [other]) == [other]


# -- trechos e reancoragem -----------------------------------------------------


def test_trecho_perdido_reancora_pelo_texto(ledger: BlockLedger):
    read(ledger, [block(300), block(500, "I will follow you anywhere.")])

    ledger.lost()
    ledger.scrolled(-700)
    # Dois textos iguais ao mesmo deslocamento reancoram o trecho antigo.
    first, second = block(100), block(300, "I will follow you anywhere.")
    assert read(ledger, [first, second]) == []
    assert first.translated == f"pt:{LONG}"

    # E a posição passa a valer de novo dentro dele.
    ledger.scrolled(-50)
    assert read(ledger, [block(50)]) == []


def test_texto_curto_sozinho_nao_reancora(ledger: BlockLedger):
    read(ledger, [block(300, "Yes.")])

    ledger.lost()
    short = block(700, "Yes.")
    assert read(ledger, [short]) == [short]


def test_texto_longo_sozinho_reancora(ledger: BlockLedger):
    read(ledger, [block(300)])

    ledger.lost()
    again = block(700)
    assert read(ledger, [again]) == []


def test_sem_correspondencia_abre_trecho_novo(ledger: BlockLedger):
    read(ledger, [block(300)])

    ledger.lost()
    fresh = block(300, "Nothing in common here at all.")
    assert read(ledger, [fresh]) == [fresh]
    # O trecho antigo continua lá, reancorável depois.
    ledger.lost()
    back = block(120)
    assert read(ledger, [back]) == []


def test_leitura_que_atravessa_um_lost_nao_e_registrada(ledger: BlockLedger):
    reading = ledger.begin()
    ledger.lost()

    blocks = [block(300)]
    assert ledger.reconcile(reading, blocks) == blocks
    ledger.record(reading, blocks)

    again = block(300)
    assert read(ledger, [again]) == [again]


# -- contexto -----------------------------------------------------------------


def context_texts(ledger: BlockLedger, target: TextBlock, limit: int | None = None) -> list[str]:
    reading = ledger.begin()
    ledger.reconcile(reading, [target])
    return [e.source for e in ledger.context(reading, target, limit)]


def test_contexto_vem_em_ordem_de_leitura(ledger: BlockLedger):
    read(ledger, [block(700, "third"), block(100, "first"), block(400, "second")])

    assert context_texts(ledger, block(1000, "fourth")) == ["first", "second", "third"]


def test_contexto_so_tem_o_que_esta_acima_do_bloco(ledger: BlockLedger):
    read(ledger, [block(100, "first"), block(400, "second"), block(700, "third")])

    assert context_texts(ledger, block(400, "second")) == ["first"]


def test_contexto_respeita_o_limite(ledger: BlockLedger):
    read(ledger, [block(100 * i, f"line {i}") for i in range(1, 9)])

    assert context_texts(ledger, block(2000, "last"), limit=3) == ["line 6", "line 7", "line 8"]


def test_contexto_atravessa_o_lost_com_o_mais_antigo_primeiro(ledger: BlockLedger):
    read(ledger, [block(100, "old one"), block(300, "old two")])
    ledger.lost()
    read(ledger, [block(100, "new one")])

    assert context_texts(ledger, block(500, "new two")) == ["old one", "old two", "new one"]


# -- reinícios ----------------------------------------------------------------


def test_titulo_novo_zera_o_registro(ledger: BlockLedger):
    ledger.observe_title("Capítulo 1 — Leitor")
    read(ledger, [block(300)])

    ledger.observe_title("Capítulo 2 — Leitor")
    again = block(300)
    assert read(ledger, [again]) == [again]
    assert context_texts(ledger, block(900, "next")) == [LONG]


def test_mesmo_titulo_ou_titulo_vazio_nao_zera(ledger: BlockLedger):
    ledger.observe_title("Capítulo 1 — Leitor")
    read(ledger, [block(300)])

    ledger.observe_title("Capítulo 1 — Leitor")
    ledger.observe_title("")
    assert read(ledger, [block(300)]) == []


def test_tempo_sem_leitura_zera_o_registro(ledger: BlockLedger, clock: Clock):
    read(ledger, [block(300)])

    clock.now += LedgerConfig().idle_seconds - 1
    assert read(ledger, [block(300)]) == []

    clock.now += LedgerConfig().idle_seconds + 1
    again = block(300)
    assert read(ledger, [again]) == [again]


# -- redesenho ao rolar de volta ----------------------------------------------

VIEWPORT = Region(0, 0, 800, 800)


def test_rolar_de_volta_redesenha_do_registro(ledger: BlockLedger):
    read(ledger, [block(300)])

    ledger.scrolled(-600)
    assert ledger.restore(VIEWPORT, []) == []

    ledger.scrolled(+600)
    restored = ledger.restore(VIEWPORT, [])
    assert [b.bbox for b in restored] == [(100, 300, 400, 360)]
    assert restored[0].translated == f"pt:{LONG}"


def test_redesenho_nao_duplica_o_que_ja_esta_na_tela(ledger: BlockLedger):
    read(ledger, [block(300)])

    assert ledger.restore(VIEWPORT, [block(305)]) == []


def test_redesenho_pula_entrada_cortada(ledger: BlockLedger):
    read(ledger, [block(300, partial=True)])

    assert ledger.restore(VIEWPORT, []) == []


def test_redesenho_depois_do_lost_nao_inventa_posicao(ledger: BlockLedger):
    read(ledger, [block(300)])
    ledger.lost()

    assert ledger.restore(VIEWPORT, []) == []


# -- pipeline -----------------------------------------------------------------


class FakeCapture:
    def grab(self, region: Region | None = None) -> Capture:
        return Capture(image=np.zeros((10, 10, 3), dtype=np.uint8), origin=(0, 0))


class FakeOCR:
    def __init__(self) -> None:
        self.top = 100

    def read(self, image: np.ndarray) -> list[TextLine]:
        return [
            TextLine(
                bbox=(100, self.top, 500, self.top + 30),
                text="Hello there my friend.",
                confidence=0.95,
            ),
            TextLine(bbox=(100, self.top + 400, 500, self.top + 430), text=LONG, confidence=0.95),
        ]


class CountingTranslator:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def translate(self, texts: list[str], source: str, target: str) -> list[str | None]:
        self.calls.append(list(texts))
        return [f"pt:{t}" for t in texts]


def test_pipeline_so_traduz_o_que_o_registro_nao_conhece(ledger: BlockLedger):
    ocr, translator = FakeOCR(), CountingTranslator()
    pipeline = Pipeline(Config(), FakeCapture(), ocr, translator, ledger=ledger)  # type: ignore[arg-type]

    first = pipeline.run()
    assert [b.translated for b in first] == ["pt:Hello there my friend.", f"pt:{LONG}"]
    assert len(translator.calls) == 1

    # Parou de novo no mesmo lugar: nada novo para traduzir, e o texto não muda.
    again = pipeline.run()
    assert len(translator.calls) == 1
    assert [b.translated for b in again] == [b.translated for b in first]

    # Rolou 50 px: as mesmas duas falas, em outra posição de tela.
    ledger.scrolled(-50)
    ocr.top = 50
    pipeline.run()
    assert len(translator.calls) == 1
