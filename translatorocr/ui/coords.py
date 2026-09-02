"""Conversão física <-> lógica compartilhada entre overlay e seleção de área.

Pixel físico do desktop é a convenção do pipeline inteiro (`models.py`); geometria de
widget no Qt é lógica. A divisão/multiplicação pelo `devicePixelRatio` só deveria
existir num lugar -- antes vivia só dentro de `OverlayWindow._to_logical`, e a seleção
de área precisa exatamente da conversão inversa.
"""

from __future__ import annotations

from PyQt6.QtCore import QRect
from PyQt6.QtGui import QScreen

from ..models import BBox, Region


def physical_to_logical(bbox: BBox, screen: QScreen | None) -> QRect:
    """Pixel físico do desktop -> retângulo lógico local de um widget nessa tela."""
    ratio = screen.devicePixelRatio() if screen else 1.0
    origin = screen.geometry() if screen is not None else None
    x1, y1, x2, y2 = (int(v / ratio) for v in bbox)
    ox, oy = (origin.left(), origin.top()) if origin is not None else (0, 0)
    return QRect(x1 - ox, y1 - oy, max(1, x2 - x1), max(1, y2 - y1))


def logical_rect_to_physical(rect: QRect, screen: QScreen | None) -> Region:
    """Inverso de `physical_to_logical`: retângulo lógico local -> `Region` física."""
    ratio = screen.devicePixelRatio() if screen else 1.0
    origin = screen.geometry() if screen is not None else None
    ox, oy = (origin.left(), origin.top()) if origin is not None else (0, 0)
    left = int((rect.left() + ox) * ratio)
    top = int((rect.top() + oy) * ratio)
    width = int(rect.width() * ratio)
    height = int(rect.height() * ratio)
    return Region(left=left, top=top, width=width, height=height)


def screen_physical_region(screen: QScreen | None) -> Region:
    """A região inteira de uma tela, em pixels físicos do desktop."""
    if screen is None:
        return Region(0, 0, 0, 0)
    ratio = screen.devicePixelRatio()
    geo = screen.geometry()
    return Region(
        left=int(geo.left() * ratio),
        top=int(geo.top() * ratio),
        width=int(geo.width() * ratio),
        height=int(geo.height() * ratio),
    )
