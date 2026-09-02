"""Encadeamento de tiers e o helper de cache compartilhado.

Sem rede: os tiers são dublês.
"""

from __future__ import annotations

import pytest

from translatorocr.backends.cache import TranslationCache, resolve_with_cache
from translatorocr.backends.chain import ChainTranslator


class FakeTier:
    """Traduz só o que estiver no mapa; o resto volta None, como o contrato manda."""

    def __init__(self, mapping: dict[str, str]) -> None:
        self.mapping = mapping
        self.seen: list[list[str]] = []

    def translate(self, texts: list[str], source: str, target: str) -> list[str | None]:
        self.seen.append(list(texts))
        return [self.mapping.get(t) for t in texts]


def test_segundo_tier_recebe_so_o_que_o_primeiro_nao_traduziu():
    first = FakeTier({"a": "A"})
    second = FakeTier({"b": "B", "c": "C"})
    chain = ChainTranslator([first, second])

    assert chain.translate(["a", "b", "c"], "en", "pt") == ["A", "B", "C"]
    assert first.seen == [["a", "b", "c"]]
    assert second.seen == [["b", "c"]]


def test_ordem_preservada_com_falha_no_meio():
    chain = ChainTranslator([FakeTier({"a": "A", "c": "C"})])
    assert chain.translate(["a", "b", "c"], "en", "pt") == ["A", None, "C"]


def test_tier_seguinte_nao_e_chamado_quando_nao_sobra_nada():
    first = FakeTier({"a": "A"})
    second = FakeTier({"a": "OUTRO"})
    ChainTranslator([first, second]).translate(["a"], "en", "pt")
    assert second.seen == []


def test_texto_vazio_nunca_chega_a_nenhum_tier():
    tier = FakeTier({})
    assert ChainTranslator([tier]).translate(["", "   "], "en", "pt") == [None, None]
    assert tier.seen == []


def test_cadeia_vazia_e_erro():
    with pytest.raises(ValueError):
        ChainTranslator([])


def test_tier_que_quebra_o_contrato_de_tamanho_estoura():
    class Broken:
        def translate(self, texts: list[str], source: str, target: str) -> list[str | None]:
            return ["só um"]

    with pytest.raises(ValueError, match="1 traduções"):
        ChainTranslator([Broken()]).translate(["a", "b"], "en", "pt")


# -- resolve_with_cache ----------------------------------------------------


@pytest.fixture
def cache(tmp_path) -> TranslationCache:
    return TranslationCache(tmp_path / "c.sqlite")


def test_cache_evita_a_segunda_chamada(cache):
    calls: list[list[int]] = []

    def run(pending: list[int]) -> list[str | None]:
        calls.append(list(pending))
        return ["Olá"]

    for _ in range(2):
        assert resolve_with_cache(["Hello"], "en", "pt", cache, "fake", run) == ["Olá"]
    assert calls == [[0]], "a segunda passada deveria ter saído do cache"


def test_falha_nao_e_gravada_no_cache(cache):
    calls = []

    def run(pending):
        calls.append(list(pending))
        return [None]

    for _ in range(2):
        resolve_with_cache(["Hello"], "en", "pt", cache, "fake", run)
    assert len(calls) == 2, "um None não pode virar entrada de cache"


def test_indices_pendentes_sao_remapeados_corretamente(cache):
    cache.put("Hello", "Olá", "en", "pt", "fake")

    def run(pending):
        assert pending == [1], "só o não-cacheado deveria ir ao backend"
        return ["Tchau"]

    assert resolve_with_cache(["Hello", "Bye"], "en", "pt", cache, "fake", run) == ["Olá", "Tchau"]


def test_backend_que_devolve_tamanho_errado_estoura(cache):
    with pytest.raises(ValueError, match="0 traduções"):
        resolve_with_cache(["a"], "en", "pt", cache, "fake", lambda pending: [])
