"""Tradução por endpoint web gratuito, com cache e backoff.

É o fallback de tradução e o único tier implementado inicialmente. É o mesmo tipo de
endpoint que Translumo e os plugins do Textractor usam na prática, e o rate limit a
ritmo humano é tolerável.

Essencial para confiabilidade: consulta ao cache antes da rede, backoff exponencial
com jitter, e falha **por bloco** — uma linha que não traduziu não pode derrubar a
captura inteira.
"""

from __future__ import annotations

import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor

from ..config import TranslationConfig
from .cache import TranslationCache, resolve_with_cache

log = logging.getLogger(__name__)

NAME = "cloud"

# Sob rate limit o endpoint devolve a página de erro do Google, e o deep-translator
# a entrega como se fosse texto traduzido. Sem esta checagem o overlay desenha
# "Error 500 (Server Error)!!1500.That's an error..." em cima do balão.
_ERROR_MARKERS = (
    "that's an error",
    "server error",
    "that's all we know",
    "<!doctype",
    "<html",
)

# Uma tradução legítima não estoura muito o tamanho do original. O múltiplo é
# generoso de propósito (EN→PT costuma crescer ~30%); o que ele pega é resposta de
# erro colada num bloco curto.
_MAX_GROWTH = 4.0
_GROWTH_SLACK = 40


def looks_like_error(source: str, translated: str) -> bool:
    lowered = translated.lower()
    if any(marker in lowered for marker in _ERROR_MARKERS):
        return True
    return len(translated) > len(source) * _MAX_GROWTH + _GROWTH_SLACK


class CloudTranslator:
    def __init__(self, cfg: TranslationConfig, cache: TranslationCache | None = None) -> None:
        from deep_translator import GoogleTranslator

        self._cfg = cfg
        self._cache = cache
        self._make = lambda src, tgt: GoogleTranslator(source=src, target=tgt)

    def _translate_one(self, text: str, source: str, target: str) -> str | None:
        delay = self._cfg.backoff_base
        for attempt in range(1, self._cfg.max_retries + 1):
            try:
                result = self._make(source, target).translate(text)
                if not result:
                    return None
                result = result.strip()
                if looks_like_error(text, result):
                    # Não é exceção — o endpoint respondeu 200 com lixo. Tratar como
                    # falha para que o retry aconteça e, se insistir, o bloco fique
                    # sem tradução em vez de exibir a página de erro.
                    raise RuntimeError("resposta do endpoint parece página de erro")
                return result
            except Exception as exc:  # noqa: BLE001 — a lib levanta tipos variados
                if attempt == self._cfg.max_retries:
                    log.warning("Tradução falhou após %d tentativas: %s", attempt, exc)
                    return None
                time.sleep(delay + random.uniform(0, delay))
                delay *= 2
        return None

    def translate(self, texts: list[str], source: str, target: str) -> list[str | None]:
        def run(pending: list[int]) -> list[str | None]:
            # I/O de rede, então o ganho é quase linear no número de workers — em série,
            # uma página com dezenas de blocos levava mais de um minuto.
            workers = min(self._cfg.max_workers, len(pending))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [
                    pool.submit(self._translate_one, texts[i], source, target) for i in pending
                ]
                return [future.result() for future in futures]

        return resolve_with_cache(texts, source, target, self._cache, NAME, run)
