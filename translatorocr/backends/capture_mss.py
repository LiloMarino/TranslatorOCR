"""Captura de tela via MSS.

Substitui o `ImageGrab.grab` da versão antiga, que era lento e não tinha consciência
de DPI, capturando a região errada em display escalado. Aqui a região é sempre pedida
em pixels físicos, e o processo é declarado per-monitor DPI aware em `__main__` antes
de qualquer captura.

Cada `MSSCapture` pertence a uma thread só, a que captura, e o objeto `mss` nasce
preguiçosamente nela e vive até o `close()`. Ele segura três objetos GDI (o DC da tela,
o DC de memória e o bitmap), e o Windows corta o processo em 10 mil: o objeto é aberto
uma vez e reaproveitado em toda captura.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Any

import cv2
import mss
import numpy as np

from ..models import Capture, Region


class MSSCapture:
    def __init__(self, monitor: int = 1) -> None:
        self._monitor_index = monitor
        # `mss.MSS()` devolve a implementação da plataforma; o pacote não expõe um tipo
        # público estável para anotar isso.
        self._sct_obj: Any = None

    @property
    def _sct(self) -> Any:
        if self._sct_obj is None:
            self._sct_obj = mss.MSS()
        return self._sct_obj

    def _monitor(self) -> dict:
        monitors = self._sct.monitors
        if self._monitor_index >= len(monitors):
            raise ValueError(
                f"Monitor {self._monitor_index} não existe; disponíveis: 0..{len(monitors) - 1}"
            )
        return monitors[self._monitor_index]

    def monitor_region(self) -> Region:
        m = self._monitor()
        return Region(m["left"], m["top"], m["width"], m["height"])

    def grab(self, region: Region | None = None) -> Capture | None:
        try:
            r = region or self.monitor_region()
            raw = self._sct.grab(
                {"left": r.left, "top": r.top, "width": r.width, "height": r.height}
            )
        except Exception as exc:
            # O DC da tela que o `mss` segura só vale para a área de trabalho em que foi
            # aberto, e o Windows troca de área de trabalho na tela bloqueada, no UAC e no
            # Ctrl+Alt+Del. Cada falha descarta o objeto, e a próxima captura abre outro.
            self.close()
            exc.add_note(f"objetos GDI abertos no processo: {_gdi_objects()}")
            raise

        # mss devolve BGRA; o resto do pipeline trabalha em BGR.
        image = cv2.cvtColor(np.asarray(raw), cv2.COLOR_BGRA2BGR)
        return Capture(image=image, origin=(r.left, r.top), scale=1.0)

    def close(self) -> None:
        sct, self._sct_obj = self._sct_obj, None
        if sct is not None:
            sct.close()


def _gdi_objects() -> int:
    """Quantos objetos GDI o processo tem abertos. O Windows corta em 10 mil, e chegar
    perto disso é o outro jeito de a captura começar a falhar."""
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    user32 = ctypes.WinDLL("user32")
    user32.GetGuiResources.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    return user32.GetGuiResources(kernel32.GetCurrentProcess(), 0)  # GR_GDIOBJECTS
