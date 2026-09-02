"""Captura de tela via MSS.

Substitui o `ImageGrab.grab` da versão antiga, que era lento e não tinha consciência
de DPI, capturando a região errada em display escalado. Aqui a região é sempre pedida
em pixels físicos, e o processo é declarado per-monitor DPI aware em `__main__` antes
de qualquer captura.

O objeto `mss` não é thread-safe e é criado preguiçosamente, dentro da thread que
de fato captura.
"""

from __future__ import annotations

import threading
from typing import Any

import cv2
import mss
import numpy as np

from ..models import Capture, Region


class MSSCapture:
    def __init__(self, monitor: int = 1) -> None:
        self._monitor_index = monitor
        self._local = threading.local()

    @property
    def _sct(self) -> Any:
        # `mss.mss()` é uma factory que devolve a implementação da plataforma; o
        # pacote não expõe um tipo público estável para anotar isso.
        sct = getattr(self._local, "sct", None)
        if sct is None:
            sct = mss.mss()
            self._local.sct = sct
        return sct

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
        r = region or self.monitor_region()
        raw = self._sct.grab({"left": r.left, "top": r.top, "width": r.width, "height": r.height})
        # mss devolve BGRA; o resto do pipeline trabalha em BGR.
        image = cv2.cvtColor(np.asarray(raw), cv2.COLOR_BGRA2BGR)
        return Capture(image=image, origin=(r.left, r.top), scale=1.0)

    def close(self) -> None:
        sct = getattr(self._local, "sct", None)
        if sct is not None:
            sct.close()
            self._local.sct = None
