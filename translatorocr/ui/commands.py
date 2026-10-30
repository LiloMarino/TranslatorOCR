"""Os comandos do app, numa lista só.

A mesma lista registra as hotkeys, monta o menu do ícone da bandeja e imprime a ajuda do
console. Comando sem tecla vive só na bandeja.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    key: str | None  # hotkey, no formato de `ui/hotkey.parse_hotkey`
    label: str  # item do menu da bandeja
    help: str  # linha da ajuda no console
    run: Callable[[], None]
    # Liga/desliga (mostra um check no menu) em vez de ação única.
    toggle: bool = False
