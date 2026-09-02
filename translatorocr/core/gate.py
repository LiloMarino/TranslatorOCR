"""O portão entre "li o texto" e "traduzi o texto".

Duas saídas, não uma. Lixo evidente é **descartado** — não paga tradução e não polui a
tela. Bloco apenas duvidoso **segue**, marcado com `needs_review`, para o overlay
desenhar diferente: é melhor o usuário ver que a leitura é incerta do que ler uma
tradução errada sem nenhum aviso. `needs_review` é também o sinal que o tier de LLM
consome depois para decidir se vale acordá-lo.

Funções puras, sem GPU e sem Qt: testáveis com listas sintéticas.

Não há gate de estabilidade (exigir N leituras idênticas antes de promover um bloco).
Ele só faz sentido no modo contínuo, onde existe um frame anterior para comparar; no
freeze por hotkey não há.
"""

from __future__ import annotations

import logging
import re
import unicodedata

from ..config import GateConfig
from ..models import TextBlock

log = logging.getLogger(__name__)

# Latin-1 mais a pontuação tipográfica que o OCR devolve legitimamente em texto inglês
# (aspas curvas, travessão, reticências). Qualquer coisa fora disso, com o reconhecedor
# em modo "en", é alucinação de glifo.
# O supressão de RUF001 abaixo é deliberada: estes caracteres ambíguos são
# exatamente o assunto da constante. Trocá-los pelos ASCII que o ruff sugere
# quebraria a verificação que ela existe para fazer.
_LATIN_EXTRA = set("‘’“”–—…€\u00a0")  # noqa: RUF001

_VOWELS = set("aeiouyAEIOUY")
_ALNUM = re.compile(r"[^\W_]", re.UNICODE)
_CONSONANT_RUN = re.compile(r"[bcdfghjklmnpqrstvwxzBCDFGHJKLMNPQRSTVWXZ]{5,}")


def charset_violation(text: str, lang: str) -> bool:
    """O texto tem caractere impossível para o idioma configurado?

    Hoje isto é quase sempre falso de graça: o reconhecedor `en` do PP-OCRv5 tem
    charset ASCII, o que já torna ideograma irrepresentável na saída. Mas isso é
    propriedade acidental da escolha de modelo, não garantia do código — por isso a
    verificação continua explícita em vez de confiar só nisso.
    """
    if not lang.lower().startswith("en"):
        return False
    return any(ord(ch) > 0xFF and ch not in _LATIN_EXTRA for ch in text)


def symbol_ratio(text: str) -> float:
    """Fração de caracteres não-alfanuméricos e não-espaço."""
    meaningful = [ch for ch in text if not ch.isspace()]
    if not meaningful:
        return 1.0
    symbols = sum(1 for ch in meaningful if not _ALNUM.match(ch))
    return symbols / len(meaningful)


def looks_like_garbage(text: str, cfg: GateConfig) -> bool:
    """Heurísticas de forma que pegam ruído de UI e borda de imagem lida como letra.

    Sem consulta a léxico de propósito: um dicionário embarcado seria peso e manutenção
    para cobrir pouco além do que a forma já denuncia. A função fica isolada para que um
    wordlist entre depois sem tocar em mais nada.
    """
    stripped = text.strip()
    if len(stripped) < cfg.min_chars:
        return True
    if symbol_ratio(stripped) > cfg.max_symbol_ratio:
        return True
    # Palavra longa sem nenhuma vogal, ou corrida de 5+ consoantes: não é inglês, é o
    # reconhecedor tentando ler uma borda, um ícone ou uma textura.
    for word in stripped.split():
        letters = [ch for ch in word if ch.isalpha()]
        if len(letters) >= 4 and not any(ch in _VOWELS for ch in letters):
            return True
    return bool(_CONSONANT_RUN.search(stripped))


def normalize_text(text: str) -> str:
    """Normaliza a forma Unicode e colapsa espaços.

    NFKC resolve a ligadura e a largura dupla que o OCR às vezes devolve (`ﬁ` → `fi`,
    `Ａ` → `A`), que de outra forma viram violação de charset falsa e furam o cache.
    """  # noqa: RUF002 — os caracteres ambíguos do exemplo são o ponto do docstring
    return " ".join(unicodedata.normalize("NFKC", text).split())


def apply_gate(blocks: list[TextBlock], cfg: GateConfig, lang: str) -> list[TextBlock]:
    """Descarta o lixo, marca o duvidoso, devolve o que vale traduzir."""
    if not cfg.enabled:
        return blocks

    kept: list[TextBlock] = []
    dropped = 0
    for block in blocks:
        block.source = normalize_text(block.source)

        if (
            not block.source
            or block.confidence < cfg.drop_below
            or charset_violation(block.source, lang)
            or looks_like_garbage(block.source, cfg)
        ):
            dropped += 1
            log.debug("gate descartou (conf=%.2f): %r", block.confidence, block.source[:60])
            continue

        block.needs_review = block.confidence < cfg.min_confidence
        kept.append(block)

    if dropped:
        log.info("gate: %d de %d blocos descartados", dropped, len(blocks))
    return kept
