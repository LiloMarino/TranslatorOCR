"""Testes do tradutor de nuvem — cache, paralelismo e o guarda contra página de erro.

Sem rede: a chamada ao endpoint é substituída por um dublê.
"""

from __future__ import annotations

import pytest

from translatorocr.backends.cache import TranslationCache, make_key, normalize
from translatorocr.backends.translate_cloud import CloudTranslator, looks_like_error
from translatorocr.config import TranslationConfig


class FakeEndpoint:
    """Imita `GoogleTranslator`: `.translate(text)` devolve o que foi programado.

    Um valor `Exception` no mapa faz a chamada levantar, para exercitar o retry.
    """

    def __init__(
        self,
        responses: dict[str, str | Exception] | None = None,
        default: str | None = None,
    ) -> None:
        self.responses: dict[str, str | Exception] = responses or {}
        self.default = default
        self.calls: list[str] = []

    def __call__(self, source, target):
        return self

    def translate(self, text: str):
        self.calls.append(text)
        if text in self.responses:
            value = self.responses[text]
            if isinstance(value, Exception):
                raise value
            return value
        return self.default if self.default is not None else f"pt({text})"


@pytest.fixture
def cfg() -> TranslationConfig:
    return TranslationConfig(max_retries=2, backoff_base=0.0, max_workers=4)


def make(cfg, endpoint, cache=None) -> CloudTranslator:
    translator = CloudTranslator.__new__(CloudTranslator)
    translator._cfg = cfg
    translator._cache = cache
    translator._make = endpoint
    return translator


# -- guarda contra página de erro -------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        "Error 500 (Server Error)!!1500.That's an error. That's all we know.",
        "<!DOCTYPE html><html><body>nope</body></html>",
    ],
)
def test_pagina_de_erro_e_reconhecida(payload):
    assert looks_like_error("oi", payload)


def test_traducao_legitima_nao_e_confundida_com_erro():
    assert not looks_like_error("Hello, are you alright?", "Olá, você está bem?")
    # EN→PT cresce, mas não 4x.
    assert not looks_like_error("Don't look back.", "Não olhe para trás.")


def test_crescimento_absurdo_e_rejeitado():
    assert looks_like_error("ok", "x" * 200)


def test_bloco_sem_traducao_em_vez_de_pagina_de_erro(cfg):
    endpoint = FakeEndpoint(default="Error 500 (Server Error)!! That's an error.")
    translator = make(cfg, endpoint)
    assert translator.translate(["Hello"], "auto", "pt") == [None]
    # Tentou de novo antes de desistir.
    assert len(endpoint.calls) == cfg.max_retries


# -- cache -------------------------------------------------------------------


def test_cache_evita_segunda_chamada(cfg, tmp_path):
    cache = TranslationCache(tmp_path / "c.sqlite")
    endpoint = FakeEndpoint()
    translator = make(cfg, endpoint, cache)

    first = translator.translate(["Hello"], "auto", "pt")
    second = translator.translate(["Hello"], "auto", "pt")
    assert first == second == ["pt(Hello)"]
    assert endpoint.calls == ["Hello"], "a segunda passagem devia sair do cache"


def test_cache_ignora_diferenca_de_espacamento(tmp_path):
    cache = TranslationCache(tmp_path / "c.sqlite")
    cache.put("Hello   world", "Olá mundo", "auto", "pt", "test")
    assert cache.get("Hello world", "auto", "pt") == "Olá mundo"


def test_chave_depende_do_par_de_idiomas():
    assert make_key("a", "en", "pt") != make_key("a", "en", "es")


def test_normalize_colapsa_espacos():
    assert normalize("  a \n b\t c ") == "a b c"


# -- lote --------------------------------------------------------------------


def test_ordem_preservada_no_lote(cfg):
    translator = make(cfg, FakeEndpoint())
    got = translator.translate(["um", "dois", "tres"], "auto", "pt")
    assert got == ["pt(um)", "pt(dois)", "pt(tres)"]


def test_falha_de_um_bloco_nao_derruba_o_lote(cfg):
    endpoint = FakeEndpoint(responses={"ruim": RuntimeError("boom")})
    translator = make(cfg, endpoint)
    got = translator.translate(["bom", "ruim", "outro"], "auto", "pt")
    assert got == ["pt(bom)", None, "pt(outro)"]


def test_texto_vazio_nao_vai_para_a_rede(cfg):
    endpoint = FakeEndpoint()
    translator = make(cfg, endpoint)
    assert translator.translate(["", "   "], "auto", "pt") == [None, None]
    assert endpoint.calls == []
