"""Captura por Desktop Duplication (DXcam).

Existe por um motivo que vale já no modo freeze: **o BitBlt do MSS devolve tela preta
em jogo D3D em fullscreen exclusivo**. Como jogo é o caso de uso secundário declarado
do projeto, sem isto metade do escopo declarado não funciona.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import numpy as np

from ..models import Capture, Region

log = logging.getLogger(__name__)


class DXCamCapture:
    def __init__(self, monitor: int = 1) -> None:
        # A config usa a convenção do mss (0 = desktop virtual, 1 = primário) e o DXcam
        # indexa saídas a partir de 0. Converter aqui, e não no chamador, é o que impede
        # que trocar de backend mova a captura de monitor em silêncio.
        #
        # O DXcam não tem equivalente ao "desktop virtual inteiro" do mss: ele captura
        # uma saída por vez. `monitor=0` cai no primário, com aviso.
        if monitor == 0:
            log.warning(
                "DXcam não captura o desktop virtual inteiro; usando o monitor primário. "
                "Para multi-monitor numa tacada só, use capture.backend = 'mss'."
            )
        self._output_idx = max(0, monitor - 1)
        self._local = threading.local()
        # O DXcam devolve None quando o frame não mudou desde a última chamada. No modo
        # freeze isso seria um bug visível: dois F8 seguidos numa tela parada fariam o
        # segundo dizer "nenhum texto encontrado". Guardamos o último frame para reusar.
        self._last: np.ndarray | None = None

    @property
    def _camera(self) -> Any:
        camera = getattr(self._local, "camera", None)
        if camera is None:
            import dxcam

            camera = dxcam.create(output_idx=self._output_idx, output_color="BGR")
            if camera is None:
                raise RuntimeError(
                    f"dxcam.create(output_idx={self._output_idx}) falhou. A saída pode não "
                    "existir, ou a sessão não tem D3D (RDP, serviço). "
                    "Use capture.backend = 'mss'."
                )
            self._local.camera = camera
        return camera

    def monitor_region(self) -> Region:
        left, top, right, bottom = self._camera.region
        return Region(left=left, top=top, width=right - left, height=bottom - top)

    def grab(self, region: Region | None = None) -> Capture | None:
        target = region or self.monitor_region()
        frame = self._camera.grab(region=(target.left, target.top, target.right, target.bottom))

        if frame is None:
            # Sem frame novo. Reusar o último é o comportamento certo aqui: o usuário
            # apertou a hotkey, então quer o conteúdo da tela, não um "nada mudou".
            if self._last is None:
                return None
            frame = self._last
        else:
            self._last = frame

        return Capture(image=np.ascontiguousarray(frame), origin=(target.left, target.top))

    def close(self) -> None:
        camera = getattr(self._local, "camera", None)
        if camera is not None:
            camera.release()
            self._local.camera = None
        self._last = None
