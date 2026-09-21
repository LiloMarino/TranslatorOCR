"""Captura que serve uma imagem de arquivo no lugar da tela.

Existe para tirar a tela do caminho ao testar. Com `MSSCapture` é preciso deixar a
página aberta e não encostar na máquina: qualquer janela que passe na frente entra na
foto e estraga a medição. Aqui a imagem entra direto no pipeline, e o resultado não
depende do que está acontecendo na tela.

Usada pelo `--image` do app e pelo `scripts/eval_pages.py`.

A imagem é tratada como uma página alta, rolada por `offset` — é isso que permite
simular o scroll de um webtoon, alimentando o rastreio com quadros sucessivos de
verdade em vez de uma tela estática.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ..models import Capture, Region

# Fundo fora da página, quando a viewport é mais alta ou mais larga que a imagem. Cinza
# escuro imita a moldura do navegador; branco viraria "papel" e confundiria a leitura.
_BACKDROP = 40


class StillCapture:
    """`CaptureBackend` sobre uma imagem fixa.

    `origin` é sempre (0, 0): os bboxes que saem do pipeline ficam em coordenada da
    viewport, que é exatamente o que o visualizador desenha e o que o rastreio translada
    quando a página rola.
    """

    def __init__(self, image: np.ndarray | None = None) -> None:
        self._image = image if image is not None else np.zeros((1, 1, 3), dtype=np.uint8)
        self.offset = 0

    @property
    def image(self) -> np.ndarray:
        return self._image

    @image.setter
    def image(self, value: np.ndarray) -> None:
        self._image = value
        self.offset = min(self.offset, self.max_offset)

    def load(self, path: str | Path) -> None:
        """Lê pelo PIL e converte para BGR — o `cv2.imread` não abre `.webp` em toda
        instalação, e é justamente o formato em que os screenshots chegam."""
        from PIL import Image

        with Image.open(path) as handle:
            rgb = np.array(handle.convert("RGB"))
        self.image = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    @property
    def max_offset(self) -> int:
        return max(0, self._image.shape[0] - 1)

    def scroll_to(self, offset: int) -> int:
        """Posiciona a rolagem, limitada à página. Devolve quanto de fato andou."""
        target = max(0, min(int(offset), self.max_offset))
        moved = target - self.offset
        self.offset = target
        return moved

    def grab(self, region: Region | None = None) -> Capture | None:
        """A faixa visível da página. Sem `region`, devolve a imagem inteira — é assim
        que o eval mede a página completa."""
        if region is None:
            return Capture(image=self._image, origin=(0, 0), scale=1.0)

        view = np.full((region.height, region.width, 3), _BACKDROP, dtype=self._image.dtype)
        visible = self._image[self.offset : self.offset + region.height, : region.width]
        if visible.size:
            # Centralizado na horizontal, como um webtoon numa tela larga.
            x0 = max(0, (region.width - visible.shape[1]) // 2)
            view[: visible.shape[0], x0 : x0 + visible.shape[1]] = visible
        return Capture(image=view, origin=(0, 0), scale=1.0)

    def close(self) -> None:
        """Nada a liberar; existe para casar com `MSSCapture`."""
