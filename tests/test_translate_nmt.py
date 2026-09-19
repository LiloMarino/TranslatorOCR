"""Tokenização do NMT — os três detalhes que degradam a saída sem levantar erro.

Sem carregar o modelo de 450 MB: `sp` e `Translator` são dublês.
"""

from __future__ import annotations

import pytest

from translatorocr.backends.translate_nmt import NMTTranslator, sentence_case, split_sentences
from translatorocr.config import TranslationConfig


class FakeSP:
    def Encode(self, text, out_type=str):  # noqa: N802 — API do sentencepiece
        return [f"▁{w}" for w in text.split()]

    def Decode(self, pieces):  # noqa: N802 — API do sentencepiece
        return " ".join(p.lstrip("▁") for p in pieces)


class FakeResult:
    def __init__(self, hypotheses):
        self.hypotheses = hypotheses


class FakeTranslator:
    def __init__(self, outputs=None, raises=False):
        self.batches: list[list[list[str]]] = []
        self.kwargs: list[dict] = []
        self._outputs = outputs
        self._raises = raises

    def translate_batch(self, batch, **kwargs):
        self.batches.append([list(b) for b in batch])
        self.kwargs.append(kwargs)
        if self._raises:
            raise RuntimeError("boom")
        outputs = self._outputs or [["▁ok"] for _ in batch]
        return [FakeResult([o]) for o in outputs]


def make(add_eos=True, **kw) -> NMTTranslator:
    tr = NMTTranslator.__new__(NMTTranslator)
    tr._cfg = TranslationConfig(**kw)
    tr._cache = None
    tr._translator = FakeTranslator()
    tr._sp_source = FakeSP()
    tr._sp_target = FakeSP()
    tr._add_eos = add_eos
    return tr


# -- token de idioma -------------------------------------------------------


def test_token_de_idioma_entra_cru_antes_das_pecas():
    """Passar '>>pob<< texto' pro sp.encode fatiaria o próprio marcador."""
    tr = make()
    tr.translate(["hello world"], "en", "pt")
    assert tr._translator.batches[0][0][0] == ">>pob<<"
    assert "▁hello" in tr._translator.batches[0][0]


# -- eos -------------------------------------------------------------------


def test_eos_anexado_quando_o_modelo_nao_anexa():
    tr = make(add_eos=True)
    tr.translate(["hello"], "en", "pt")
    assert tr._translator.batches[0][0][-1] == "</s>"


def test_eos_nao_anexado_quando_o_modelo_ja_anexa():
    """Modelo convertido pelo caminho Marian traz add_source_eos=True; duplicar degrada."""
    tr = make(add_eos=False)
    tr.translate(["hello"], "en", "pt")
    assert tr._translator.batches[0][0][-1] != "</s>"


# -- par de idiomas --------------------------------------------------------


@pytest.mark.parametrize("source,target", [("en", "pt"), ("auto", "pt"), ("EN", "PT-BR")])
def test_pares_suportados(source, target):
    tr = make()
    assert tr.translate(["hello"], source, target) == ["ok"]


@pytest.mark.parametrize("source,target", [("ja", "pt"), ("en", "es"), ("fr", "de")])
def test_par_nao_suportado_devolve_none_sem_chamar_o_modelo(source, target):
    """Devolver None é o que faz a cadeia cair para a nuvem em vez de traduzir errado."""
    tr = make()
    assert tr.translate(["hello", "world"], source, target) == [None, None]
    assert tr._translator.batches == []


# -- lote ------------------------------------------------------------------


def test_lote_inteiro_vai_numa_chamada_so():
    tr = make()
    tr._translator._outputs = [["▁a"], ["▁b"], ["▁c"]]
    assert tr.translate(["x", "y", "z"], "en", "pt") == ["a", "b", "c"]
    assert len(tr._translator.batches) == 1


def test_beam_size_e_repassado():
    tr = make(nmt_beam_size=4)
    tr.translate(["hello"], "en", "pt")
    assert tr._translator.kwargs[0]["beam_size"] == 4


def test_texto_vazio_nao_chega_ao_modelo():
    tr = make()
    assert tr.translate(["", "  "], "en", "pt") == [None, None]
    assert tr._translator.batches == []


def test_falha_do_modelo_nao_derruba_o_lote():
    tr = make()
    tr._translator = FakeTranslator(raises=True)
    assert tr.translate(["a", "b"], "en", "pt") == [None, None]


def test_hipotese_vazia_vira_none():
    tr = make()
    tr._translator._outputs = [[]]
    assert tr.translate(["hello"], "en", "pt") == [None]


# -- caixa de frase ----------------------------------------------------------
# Letreiro de mangá é todo em CAIXA ALTA, e nela o modelo troca palavras comuns por
# outras. Os casos cobrem reticências iniciais, pronome I e contrações com apóstrofo curvo.

# O apóstrofo curvo é o que o letreiro de mangá usa, e o que o OCR devolve.
APOS = "\N{RIGHT SINGLE QUOTATION MARK}"


@pytest.mark.parametrize(
    "text,expected",
    [
        (f"IT{APOS}S A TRAP.", f"It{APOS}s a trap."),
        (f"THAT{APOS}S ODD~", f"That{APOS}s odd~"),
        ("...WHERE ARE WE GOING?", "...Where are we going?"),
        (f"I{APOS}M NOT SURE ABOUT THIS...", f"I{APOS}m not sure about this..."),
        ("OK. WHY DON'T WE WAIT?", "Ok. Why don't we wait?"),
        ("HEY, JEAN-LUC... I THINK SO", "Hey, jean-luc... I think so"),
    ],
)
def test_sentence_case_em_caixa_alta(text, expected):
    assert sentence_case(text) == expected


@pytest.mark.parametrize("text", ["Hello there, NASA.", "I saw it.", "", "80", "..."])
def test_sentence_case_nao_mexe_em_texto_que_nao_e_caixa_alta(text):
    assert sentence_case(text) == text


# -- por frase ---------------------------------------------------------------


def test_split_sentences():
    assert split_sentences("Yeah. Why don't you? Ok!  Fine~ end") == [
        "Yeah.",
        "Why don't you?",
        "Ok!",
        "Fine~",
        "end",
    ]
    assert split_sentences("...Can I ask") == ["...Can I ask"]


def test_balao_com_dois_periodos_vira_duas_frases_no_mesmo_lote():
    """Com os dois períodos juntos o modelo engolia o primeiro."""
    tr = make()
    tr._translator._outputs = [["▁Sim."], ["▁Por", "▁quê?"], ["▁Ei."]]
    out = tr.translate(["OK. WHY?", "HEY."], "en", "pt")
    assert out == ["Sim. Por quê?", "Ei."]
    assert len(tr._translator.batches) == 1
    sources = [[p for p in b if p.startswith("▁")] for b in tr._translator.batches[0]]
    assert sources == [["▁Ok."], ["▁Why?"], ["▁Hey."]]


def test_frase_sem_traducao_invalida_o_balao_inteiro():
    """Meia tradução com cara de completa é pior que deixar a nuvem tentar."""
    tr = make()
    tr._translator._outputs = [["▁Sim."], [], ["▁Ei."]]
    assert tr.translate(["OK. WHY?", "HEY."], "en", "pt") == [None, "Ei."]
