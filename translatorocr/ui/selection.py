"""Seleção de área de captura por clique-e-arrastar (F11).

Ao contrário do `OverlayWindow`, esta janela **não** é click-through — ela existe
justamente para receber o mouse. Cobre a tela do monitor configurado e desenha um
retângulo semi-transparente enquanto o usuário arrasta; no soltar do botão, converte
o retângulo lógico do Qt para uma `Region` em pixels físicos do desktop (mesma
convenção do resto do pipeline) e entrega ao callback.

Um arraste com área desprezível (clique sem mover o mouse) é tratado como pedido de
reset para tela cheia — devolve `None` ao callback. `Esc` cancela sem chamar o
callback, mantendo a seleção anterior como estava.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPen, QScreen
from PyQt6.QtWidgets import QWidget

from ..models import Region
from .coords import logical_rect_to_physical

# Abaixo disto (em pixels lógicos, em qualquer dimensão) o arraste é tratado como
# "sem intenção real de selecionar" — reseta para tela cheia em vez de criar uma
# região de 1x1.
MIN_DRAG_PX = 8


class SelectionOverlay(QWidget):
    def __init__(
        self, screen: QScreen | None, on_selected: Callable[[Region | None], None]
    ) -> None:
        super().__init__()
        self._screen = screen or QGuiApplication.primaryScreen()
        self._on_selected = on_selected
        self._origin: QPoint | None = None
        self._current: QPoint | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        if self._screen is not None:
            self.setGeometry(self._screen.geometry())

    # Sem anotação de tipo em `a0`, igual overlay.py: os stubs do PyQt6 tipam o
    # parâmetro como opcional, e o Qt nunca de fato entrega `None` aqui — o guard
    # `is None` abaixo é só pra satisfazer o pyright, não uma condição real.
    def mousePressEvent(self, a0) -> None:  # noqa: N802 — override do Qt
        if a0 is None:
            return
        self._origin = a0.position().toPoint()
        self._current = self._origin
        self.update()

    def mouseMoveEvent(self, a0) -> None:  # noqa: N802 — override do Qt
        if a0 is None or self._origin is None:
            return
        self._current = a0.position().toPoint()
        self.update()

    def mouseReleaseEvent(self, a0) -> None:  # noqa: N802 — override do Qt
        if a0 is None or self._origin is None:
            return
        rect = QRect(self._origin, a0.position().toPoint()).normalized()
        self._origin = None
        self._current = None

        if rect.width() < MIN_DRAG_PX and rect.height() < MIN_DRAG_PX:
            self._finish(None)
            return
        self._finish(logical_rect_to_physical(rect, self._screen))

    def keyPressEvent(self, a0) -> None:  # noqa: N802 — override do Qt
        if a0 is not None and a0.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(a0)

    def _finish(self, region: Region | None) -> None:
        self.close()
        self._on_selected(region)

    def paintEvent(self, a0) -> None:  # noqa: N802 — override do Qt
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 60))
        if self._origin is not None and self._current is not None:
            rect = QRect(self._origin, self._current).normalized()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor(80, 170, 255, 230), 2))
            painter.drawRect(rect)
