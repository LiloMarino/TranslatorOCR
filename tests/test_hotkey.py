"""Teclas padrão: formato aceito e fora do que o navegador em foco usa."""

from __future__ import annotations

from dataclasses import astuple

from translatorocr.config import HotkeyConfig
from translatorocr.ui.hotkey import MOD_NOREPEAT, parse_hotkey

# Teclas de função com uso no Firefox ou no Chrome: ajuda, busca, recarregar, barra de
# endereço, cursor de texto, menu, tela cheia e DevTools.
BROWSER_KEYS = {parse_hotkey(f"F{n}")[1] for n in (1, 3, 5, 6, 7, 10, 11, 12)}


def test_teclas_padrao_sao_distintas_soltas_e_livres_no_navegador():
    parsed = [parse_hotkey(spec) for spec in astuple(HotkeyConfig())]
    assert len(set(parsed)) == len(parsed)
    # Tecla solta: o Alt soltado sozinho chega ao navegador e abre a barra de menu.
    assert all(modifiers == MOD_NOREPEAT for modifiers, _ in parsed)
    assert not {vk for _, vk in parsed} & BROWSER_KEYS
