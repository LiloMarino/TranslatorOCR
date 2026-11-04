"""TranslateGemma 4B: a segunda passada da tradução, com as falas anteriores como contexto.

O opus-mt desenha a tradução na hora; este modelo retraduz cada balão em seguida, e a
tradução dele substitui a primeira. As falas anteriores entram como turnos da conversa,
cada uma já respondida com a melhor tradução que o registro tem dela — é o formato que o
template do modelo aceita, e foi o que a comparação às cegas de
`scripts/eval_translation.py` mediu.

O prompt é montado cru no formato do template e vai pelo `create_completion`: o
`create_chat_completion` do llama-cpp-python não sabe montar o `content` em lista com
códigos de idioma que o template exige.

O cache guarda a primeira tradução de cada fala, então uma fala relida volta igual,
mesmo que o contexto em volta tenha mudado.
"""

from __future__ import annotations

import logging
from typing import Any

from ..assets import TRANSLATEGEMMA_PATH
from ..config import RefineConfig
from .cache import TranslationCache, resolve_with_cache

log = logging.getLogger(__name__)

# Texto do template embutido no GGUF, copiado sem mudar uma letra: o modelo foi treinado
# com ele, inclusive o par de idiomas.
GEMMA_INSTRUCTION = (
    "You are a professional English (en) to Portuguese (pt-BR) translator. Your goal is "
    "to accurately convey the meaning and nuances of the original English text while "
    "adhering to Portuguese grammar, vocabulary, and cultural sensitivities.\n"
    "Produce only the Portuguese translation, without any additional explanations or "
    "commentary. Please translate the following English text into Portuguese:\n\n\n"
)
SOURCE_LANG = "en"
TARGET_LANG = "pt"


def gemma_turn(text: str) -> str:
    return f"<start_of_turn>user\n{GEMMA_INSTRUCTION}{text.strip()}<end_of_turn>\n"


def gemma_prompt(text: str, history: list[tuple[str, str]]) -> str:
    """Prompt cru no formato do template; o BOS entra pela tokenização."""
    turns = "".join(
        f"{gemma_turn(src)}<start_of_turn>model\n{dst.strip()}<end_of_turn>\n"
        for src, dst in history
    )
    return f"{turns}{gemma_turn(text)}<start_of_turn>model\n"


class GemmaTranslator:
    def __init__(self, cfg: RefineConfig, cache: TranslationCache | None) -> None:
        import llama_cpp

        if not TRANSLATEGEMMA_PATH.is_file():
            raise FileNotFoundError(
                f"TranslateGemma não encontrado em {TRANSLATEGEMMA_PATH.resolve()}. "
                "Rode `uv run scripts/fetch_models.py translategemma`."
            )
        self._cfg = cfg
        self._cache = cache
        # Any: o llama-cpp-python mora num grupo opcional, e o pyright precisa passar sem ele.
        self._llm: Any = llama_cpp.Llama(
            str(TRANSLATEGEMMA_PATH),
            n_ctx=cfg.n_ctx,
            n_gpu_layers=cfg.n_gpu_layers,
            verbose=False,
        )
        # A primeira geração paga a subida dos kernels da GPU; aqui ela cai na carga.
        self._complete("Hello there.", [])
        log.info("TranslateGemma carregado de %s", TRANSLATEGEMMA_PATH)

    def _complete(self, text: str, history: list[tuple[str, str]]) -> str:
        result = self._llm.create_completion(
            gemma_prompt(text, history),
            max_tokens=self._cfg.max_tokens,
            temperature=0,
            stop=["<end_of_turn>"],
        )
        return result["choices"][0]["text"].strip()

    def translate(self, text: str, history: list[tuple[str, str]]) -> str | None:
        def run(_pending: list[int]) -> list[str | None]:
            try:
                return [self._complete(text, history) or None]
            except Exception:
                log.exception("TranslateGemma falhou em %r", text[:60])
                return [None]

        return resolve_with_cache([text], SOURCE_LANG, TARGET_LANG, self._cache, "gemma", run)[0]
