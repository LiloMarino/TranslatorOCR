"""Memória de tradução em SQLite.

Consultado antes de qualquer chamada de rede. Garante que fala repetida sai
instantânea e que o mesmo texto sempre traduz igual.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import time
from collections.abc import Callable, Sequence
from pathlib import Path

_WHITESPACE = re.compile(r"\s+")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS translations (
    key         TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    translated  TEXT NOT NULL,
    source_lang TEXT NOT NULL,
    target_lang TEXT NOT NULL,
    backend     TEXT NOT NULL,
    created_at  REAL NOT NULL
);
"""


def normalize(text: str) -> str:
    """Normaliza para chave de cache: espaços colapsados, bordas aparadas."""
    return _WHITESPACE.sub(" ", text).strip()


def make_key(text: str, source: str, target: str) -> str:
    payload = f"{source}\x1f{target}\x1f{normalize(text)}".encode()
    return hashlib.sha1(payload).hexdigest()


class TranslationCache:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False porque o worker é uma thread e a conexão é usada
        # só de lá; o sqlite serializa os acessos por conta própria.
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def get(self, text: str, source: str, target: str) -> str | None:
        row = self._conn.execute(
            "SELECT translated FROM translations WHERE key = ?",
            (make_key(text, source, target),),
        ).fetchone()
        return row[0] if row else None

    def put(self, text: str, translated: str, source: str, target: str, backend: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO translations "
            "(key, source, translated, source_lang, target_lang, backend, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                make_key(text, source, target),
                normalize(text),
                translated,
                source,
                target,
                backend,
                time.time(),
            ),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def resolve_with_cache(
    texts: list[str],
    source: str,
    target: str,
    cache: TranslationCache | None,
    backend: str,
    translate_pending: Callable[[list[int]], Sequence[str | None]],
) -> list[str | None]:
    """Consulta o cache, delega só o que sobrou, grava o que deu certo.

    Todo tier acima dele reusa esta função em vez de reimplementar o passo — o
    `translate_pending` recebe os índices que faltam e devolve uma tradução por índice,
    na mesma ordem. Texto vazio nunca chega ao backend: não há o que traduzir e a
    chamada seria desperdiçada.
    """
    results: list[str | None] = [None] * len(texts)
    pending: list[int] = []

    for i, text in enumerate(texts):
        if not text.strip():
            continue
        if cache is not None:
            hit = cache.get(text, source, target)
            if hit is not None:
                results[i] = hit
                continue
        pending.append(i)

    if not pending:
        return results

    translated = translate_pending(pending)
    if len(translated) != len(pending):
        raise ValueError(
            f"{backend} devolveu {len(translated)} traduções para {len(pending)} pendentes"
        )
    for index, value in zip(pending, translated, strict=True):
        results[index] = value

    # Fora de qualquer pool: a conexão sqlite é de uma thread só.
    if cache is not None:
        for index in pending:
            value = results[index]
            if value:
                cache.put(texts[index], value, source, target, backend)
    return results
