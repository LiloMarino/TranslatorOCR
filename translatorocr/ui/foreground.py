"""Título da janela em primeiro plano."""

from __future__ import annotations

import ctypes
import ctypes.wintypes


def foreground_title() -> str:
    """Título da janela que está na frente, ou vazio se não houver uma.

    O navegador põe o capítulo no título da aba, então a mudança dele é o sinal mais
    barato de que a leitura trocou de assunto.
    """
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.wintypes.HWND
    user32.GetWindowTextLengthW.argtypes = [ctypes.wintypes.HWND]
    user32.GetWindowTextW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.LPWSTR, ctypes.c_int]

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value
