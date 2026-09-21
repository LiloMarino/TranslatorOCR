"""Geometria de `BBox`, compartilhada.

Módulo folha, sem Qt e sem GPU: só depende do tipo `BBox` de `models.py`. Existe porque
duas coisas distantes precisam da mesma pergunta — o detector, para decidir se duas
regiões são o mesmo balão, e o rastreio da rolagem, para decidir se uma leitura nova e
uma antiga são o mesmo balão.
"""

from __future__ import annotations

from .models import BBox


def area(box: BBox) -> int:
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def intersection_area(a: BBox, b: BBox) -> int:
    width = min(a[2], b[2]) - max(a[0], b[0])
    height = min(a[3], b[3]) - max(a[1], b[1])
    return width * height if width > 0 and height > 0 else 0


def overlap_fraction(a: BBox, b: BBox) -> float:
    """Sobreposição como fração da **menor** das duas caixas.

    Fração da menor, e não IoU, porque o caso que interessa é uma caixa pequena contida
    numa grande — que o IoU faria parecer distante.
    """
    smaller = max(1, min(area(a), area(b)))
    return intersection_area(a, b) / smaller
