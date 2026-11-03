"""O helper de cache que todo tradutor usa.

O tradutor é um dublê: uma função que devolve o que o teste programou.
"""

from __future__ import annotations

import pytest

from translatorocr.backends.cache import TranslationCache, resolve_with_cache


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
