"""Tipos que trafegam pelo pipeline.

Convenção de coordenadas, válida para o projeto inteiro: **todo bbox que sai do
pipeline está em pixels físicos do desktop virtual**. A conversão para coordenada
lógica do Qt acontece só na borda da UI, em `ui/overlay.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

BBox = tuple[int, int, int, int]  # x1, y1, x2, y2


@dataclass(frozen=True)
class Region:
    """Retângulo em pixels físicos do desktop virtual."""

    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


@dataclass(frozen=True)
class Capture:
    """Imagem capturada, já com o upscale aplicado.

    `origin` é o canto superior-esquerdo da região em pixels físicos do desktop, e
    `scale` é o fator de upscale — juntos permitem converter um bbox do espaço da
    imagem de volta para o espaço do desktop.
    """

    image: np.ndarray  # BGR
    origin: tuple[int, int]
    scale: float = 1.0

    def to_desktop(self, bbox: BBox) -> BBox:
        """Converte um bbox do espaço da imagem para pixels físicos do desktop."""
        ox, oy = self.origin
        x1, y1, x2, y2 = bbox
        return (
            int(x1 / self.scale) + ox,
            int(y1 / self.scale) + oy,
            int(x2 / self.scale) + ox,
            int(y2 / self.scale) + oy,
        )


@dataclass(frozen=True)
class Detection:
    """Uma região achada pelo detector, no espaço da imagem entregue a ele.

    `kind` vem do `id2label` do modelo: `"bubble"` é o balão desenhado, `"text_bubble"`
    é texto dentro de um balão e `"text_free"` é texto solto na página (onomatopeia,
    narração, legenda).
    """

    bbox: BBox
    kind: str
    score: float


@dataclass(frozen=True)
class TextLine:
    """Uma linha reconhecida, no espaço da imagem entregue ao OCR."""

    bbox: BBox
    text: str
    confidence: float
    # Qual região do detector originou esta linha. Duas linhas de regiões diferentes
    # nunca entram no mesmo bloco — é o que permite ao agrupamento usar a fronteira
    # que o detector achou em vez de inferi-la por proximidade. `None` quando o
    # reconhecedor rodou sobre a imagem inteira, sem detector.
    region_id: int | None = None

    @property
    def height(self) -> int:
        return self.bbox[3] - self.bbox[1]


@dataclass
class TextBlock:
    """Um bloco de texto — tipicamente um balão — em pixels físicos do desktop.

    É a unidade de tradução: cada bloco é traduzido isoladamente, nunca concatenado
    com outro.
    """

    bbox: BBox
    source: str
    confidence: float
    lines: list[TextLine] = field(default_factory=list)
    translated: str | None = None
    # Marcado pelo gate quando o reconhecimento é duvidoso mas não ruim o bastante
    # para descartar. O overlay desenha a caixa com borda distinta, e é este o sinal
    # que o tier de LLM vai consumir para decidir se vale acordá-lo.
    needs_review: bool = False

    @property
    def text(self) -> str:
        """O que deve ser exibido: a tradução se houver, senão o original."""
        return self.translated if self.translated is not None else self.source
