"""Comparação de leituras de OCR, comum aos scripts de avaliação."""

from __future__ import annotations


def normalize(text: str) -> str:
    """Só letras, dígitos e espaço: o que se mede é a leitura das palavras, e ".."
    contra "..." ou apóstrofo reto contra curvo não mudam a tradução."""
    kept = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text.upper())
    return " ".join(kept.split())


def cer(a: str, b: str) -> float:
    """Distância de edição de caracteres, normalizada pelo tamanho da referência."""
    a, b = normalize(a), normalize(b)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] / max(1, len(b))
