"""Tokenização do NMT — os três detalhes que degradam a saída sem levantar erro.

Sem carregar o modelo de 450 MB: `sp` e `Translator` são dublês.
"""

from __future__ import annotations

import pytest

from translatorocr.backends.translate_nmt import NMTTranslator
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


def test_token_de_idioma_configuravel():
    tr = make(nmt_lang_token=">>por<<")
    tr.translate(["hello"], "en", "pt")
    assert tr._translator.batches[0][0][0] == ">>por<<"


def test_sem_token_configurado_nao_prepende_nada():
    tr = make(nmt_lang_token="")
    tr.translate(["hello"], "en", "pt")
    assert tr._translator.batches[0][0][0] == "▁hello"


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
