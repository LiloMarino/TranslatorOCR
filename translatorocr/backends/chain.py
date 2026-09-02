"""Encadeia tiers de tradução.

Cada tier recebe **apenas** o que o anterior não conseguiu traduzir. Isso não precisa
de nenhuma interface nova: o `TranslatorBackend` já contratualiza que uma entrada que
falhou volta como `None`, então "o que falta" é exatamente "onde veio None".

Encadeia backends de tradução — NMT local rápido e offline na frente, nuvem atrás
para o que ele não cobrir (par de idioma fora do modelo, lote que estourou).
"""

from __future__ import annotations

import logging

from .base import TranslatorBackend

log = logging.getLogger(__name__)


class ChainTranslator:
    def __init__(self, tiers: list[TranslatorBackend]) -> None:
        if not tiers:
            raise ValueError("ChainTranslator precisa de pelo menos um tier")
        self._tiers = tiers

    def translate(self, texts: list[str], source: str, target: str) -> list[str | None]:
        results: list[str | None] = [None] * len(texts)
        pending = [i for i, text in enumerate(texts) if text.strip()]

        for tier in self._tiers:
            if not pending:
                break
            translated = tier.translate([texts[i] for i in pending], source, target)
            if len(translated) != len(pending):
                raise ValueError(
                    f"{type(tier).__name__} devolveu {len(translated)} traduções "
                    f"para {len(pending)} textos"
                )

            still_pending: list[int] = []
            for index, value in zip(pending, translated, strict=True):
                if value:
                    results[index] = value
                else:
                    still_pending.append(index)

            if still_pending:
                log.info(
                    "%s resolveu %d/%d; %d seguem para o próximo tier",
                    type(tier).__name__,
                    len(pending) - len(still_pending),
                    len(pending),
                    len(still_pending),
                )
            pending = still_pending

        return results
