"""TranslateGemma — o formato do prompt, o cache e a falha por fala.

Sem carregar o modelo: `_llm` é um dublê de `create_completion`.
"""

from __future__ import annotations

import pytest

from translatorocr.backends.cache import TranslationCache
from translatorocr.backends.translate_gemma import GEMMA_INSTRUCTION, GemmaTranslator
from translatorocr.config import RefineConfig


class FakeLlm:
    def __init__(self, outputs: list[str] | None = None, raises: bool = False) -> None:
        self.prompts: list[str] = []
        self.kwargs: list[dict] = []
        self._outputs = outputs or []
        self._raises = raises

    def create_completion(self, prompt: str, **kwargs):
        self.prompts.append(prompt)
        self.kwargs.append(kwargs)
        if self._raises:
            raise RuntimeError("boom")
        text = self._outputs.pop(0) if self._outputs else " Olá "
        return {"choices": [{"text": text}]}


def make(cache: TranslationCache | None = None, **llm) -> GemmaTranslator:
    tr = GemmaTranslator.__new__(GemmaTranslator)
    tr._cfg = RefineConfig()
    tr._cache = cache
    tr._llm = FakeLlm(**llm)
    return tr


def user(text: str) -> str:
    return f"<start_of_turn>user\n{GEMMA_INSTRUCTION}{text}<end_of_turn>\n"


def test_sem_historico_e_um_turno_so():
    tr = make()
    assert tr.translate("Hello.", []) == "Olá"
    assert tr._llm.prompts == [f"{user('Hello.')}<start_of_turn>model\n"]


def test_historico_vira_turnos_ja_respondidos_em_ordem():
    tr = make()
    tr.translate("Third.", [("First.", "Primeiro."), ("Second.", "Segundo.")])
    assert tr._llm.prompts[0] == (
        f"{user('First.')}<start_of_turn>model\nPrimeiro.<end_of_turn>\n"
        f"{user('Second.')}<start_of_turn>model\nSegundo.<end_of_turn>\n"
        f"{user('Third.')}<start_of_turn>model\n"
    )


def test_geracao_para_no_fim_do_turno_e_sem_amostragem():
    tr = make()
    tr.translate("Hello.", [])
    assert tr._llm.kwargs[0]["stop"] == ["<end_of_turn>"]
    assert tr._llm.kwargs[0]["temperature"] == 0


@pytest.mark.parametrize("llm", [{"raises": True}, {"outputs": ["   "]}])
def test_falha_ou_saida_vazia_mantem_a_traducao_que_o_balao_tem(llm):
    assert make(**llm).translate("Hello.", []) is None


def test_cache_responde_a_fala_repetida_sem_chamar_o_modelo(tmp_path):
    tr = make(TranslationCache(tmp_path / "c.sqlite"))
    assert tr.translate("Hello.", [("Hi.", "Oi.")]) == "Olá"
    assert tr.translate("Hello.", []) == "Olá"
    assert len(tr._llm.prompts) == 1


def test_cache_da_gemma_e_separado_do_opus_mt(tmp_path):
    cache = TranslationCache(tmp_path / "c.sqlite")
    cache.put("Hello.", "Alô.", "en", "pt", "nmt")
    assert make(cache).translate("Hello.", []) == "Olá"
