"""Refino por LLM local — contexto rolante, glossário e fail-safe.

Sem carregar modelo de verdade: `_llm` é um dublê de `create_chat_completion`
(chat completion, não completion cru — ver docstring de translate_llm.py sobre
por que o completion cru não funcionava com o Qwen3).
"""

from __future__ import annotations

from translatorocr.backends.translate_llm import LLMTranslator
from translatorocr.config import LLMConfig
from translatorocr.models import TextBlock


def _user_content(prompts: list[dict], call: int = -1) -> str:
    return prompts[call][1]["content"]


class FakeLlm:
    def __init__(self, outputs=None, raises=False):
        self.calls: list[list[dict]] = []
        self._outputs = outputs
        self._raises = raises

    def create_chat_completion(self, messages, **kwargs):
        self.calls.append(messages)
        if self._raises:
            raise RuntimeError("boom")
        text = self._outputs.pop(0) if self._outputs else "Olá"
        return {"choices": [{"message": {"content": text}}]}


def make(context_window=6, glossary=None) -> LLMTranslator:
    tr = LLMTranslator.__new__(LLMTranslator)
    tr._cfg = LLMConfig(context_window=context_window)
    tr._llm = FakeLlm()
    from collections import deque

    tr._context = deque(maxlen=context_window)
    tr._glossary = glossary or {}
    return tr


def block(text: str, needs_review: bool = True) -> TextBlock:
    return TextBlock(bbox=(0, 0, 10, 10), source=text, confidence=0.5, needs_review=needs_review)


# -- fail-safe ---------------------------------------------------------------


def test_saida_vazia_vira_none():
    tr = make()
    tr._llm = FakeLlm(outputs=[""])
    assert tr.refine([block("hello")]) == [None]


def test_excecao_no_bloco_vira_none_sem_derrubar_o_lote():
    tr = make()
    calls = {"n": 0}

    def flaky(messages, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return {"choices": [{"message": {"content": "traduzido"}}]}

    tr._llm = type("Flaky", (), {"create_chat_completion": staticmethod(flaky)})()
    result = tr.refine([block("a"), block("b")])
    assert result == [None, "traduzido"]


def test_bloco_de_pensamento_nao_fechado_vira_none():
    """max_tokens cortou no meio do raciocínio -- não é tradução, é lixo truncado."""
    tr = make()
    tr._llm = FakeLlm(outputs=["<think>\n\nainda pensando sobre isso"])
    assert tr.refine([block("hello")]) == [None]


def test_bloco_de_pensamento_vazio_e_removido():
    tr = make()
    tr._llm = FakeLlm(outputs=["<think>\n\n</think>\n\nOlá mundo"])
    assert tr.refine([block("hello")]) == ["Olá mundo"]


# -- contexto rolante ---------------------------------------------------------


def test_contexto_vazio_na_primeira_chamada():
    tr = make()
    tr.refine([block("hello")])
    assert "Contexto" not in _user_content(tr._llm.calls)


def test_traducao_anterior_entra_como_contexto_na_proxima():
    tr = make()
    tr._llm = FakeLlm(outputs=["primeira traducao", "segunda traducao"])
    tr.refine([block("a")])
    tr.refine([block("b")])
    assert "primeira traducao" in _user_content(tr._llm.calls, 1)


def test_contexto_respeita_o_tamanho_configurado():
    tr = make(context_window=2)
    tr._llm = FakeLlm(outputs=["um", "dois", "tres", "quatro"])
    for text in ["a", "b", "c"]:
        tr.refine([block(text)])
    assert len(tr._context) == 2
    assert list(tr._context) == ["dois", "tres"]


def test_saida_vazia_nao_entra_no_contexto():
    tr = make()
    tr._llm = FakeLlm(outputs=[""])
    tr.refine([block("a")])
    assert len(tr._context) == 0


# -- glossário -----------------------------------------------------------------


def test_glossario_entra_no_prompt_quando_configurado():
    tr = make(glossary={"Naruto": "Naruto (não traduzir)"})
    tr.refine([block("hello")])
    assert "Naruto" in _user_content(tr._llm.calls)


def test_sem_glossario_nao_aparece_no_prompt():
    tr = make(glossary={})
    tr.refine([block("hello")])
    assert "Glossário" not in _user_content(tr._llm.calls)


# -- ordem ----------------------------------------------------------------------


def test_ordem_preservada():
    tr = make()
    tr._llm = FakeLlm(outputs=["A", "B", "C"])
    result = tr.refine([block("a"), block("b"), block("c")])
    assert result == ["A", "B", "C"]
