"""Teclas padrão: formato aceito e sem tomar tecla solta do sistema."""

from __future__ import annotations

from dataclasses import astuple

from translatorocr.config import HotkeyConfig
from translatorocr.ui.hotkey import MOD_ALT, parse_hotkey


def test_teclas_padrao_sao_distintas_e_usam_modificador():
    parsed = [parse_hotkey(spec) for spec in astuple(HotkeyConfig())]
    assert len(set(parsed)) == len(parsed)
    assert all(modifiers & MOD_ALT for modifiers, _ in parsed)
