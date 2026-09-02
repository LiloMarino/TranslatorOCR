"""Overlay click-through: caixas escuras desenhadas na posição de cada bloco.

Exibe os blocos traduzidos sobre a tela, click-through e sem roubar foco.

Dois pontos delicados:

* **Click-through.** Os flags do Qt sozinhos não bastam no Windows. São
  `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE`, aplicados no HWND depois
  do `show()`, que garantem que o overlay nunca intercepte clique nem roube foco do
  jogo ou do navegador.
* **Coordenadas.** Os blocos chegam em pixels físicos do desktop; a geometria de
  widget no Qt é lógica. A divisão pelo `devicePixelRatio` acontece aqui, e só
  aqui.
"""

from __future__ import annotations

import ctypes
import logging

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QPainter,
    QPen,
    QScreen,
)
from PyQt6.QtWidgets import QWidget

from ..config import OverlayConfig
from ..models import Region, TextBlock
from .coords import physical_to_logical

log = logging.getLogger(__name__)

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080


def _make_click_through(hwnd: int) -> None:
    user32 = ctypes.windll.user32
    get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
    get_long.restype = ctypes.c_longlong
    set_long.restype = ctypes.c_longlong
    set_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_longlong]

    current = get_long(ctypes.c_void_p(hwnd), GWL_EXSTYLE)
    set_long(
        ctypes.c_void_p(hwnd),
        GWL_EXSTYLE,
        current | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
    )


class OverlayWindow(QWidget):
    def __init__(self, cfg: OverlayConfig) -> None:
        super().__init__()
        self._cfg = cfg
        self._blocks: list[TextBlock] = []
        self._status: str | None = None
        # Independente de _blocks/_status: liga/desliga com o hotkey de outline, sem ser limpo pelo
        # F9 (dismiss) nem pelo próximo F8. É só um guia visual da área de captura.
        self._outline_region: Region | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

    # Os overrides do Qt usam `a0` porque é assim que os stubs do PyQt6 nomeiam o
    # parâmetro; divergir daí quebra a compatibilidade de assinatura.
    def showEvent(self, a0) -> None:  # noqa: N802 — override do Qt
        super().showEvent(a0)
        try:
            _make_click_through(int(self.winId()))
        except Exception:
            log.exception("Não foi possível aplicar os flags de click-through")

    def _current_screen(self) -> QScreen | None:
        return self.screen() or QGuiApplication.primaryScreen()

    def cover_screen(self) -> None:
        """Cobre a tela em que a janela está, em coordenadas lógicas."""
        screen = self._current_screen()
        if screen is None:
            log.warning("Nenhuma tela disponível; o overlay fica sem geometria definida.")
            return
        self.setGeometry(screen.geometry())

    # -- conteúdo ---------------------------------------------------------

    def set_blocks(self, blocks: list[TextBlock]) -> None:
        """Idempotente: permite atualizar tradução sem recriar o overlay."""
        self._blocks = blocks
        self._status = None
        self.update()

    def set_status(self, message: str | None) -> None:
        self._status = message
        self._blocks = []
        self.update()

    def clear(self) -> None:
        self._blocks = []
        self._status = None
        self.update()

    def show_region_outline(self, region: Region) -> None:
        """Mostra uma borda na área que o F8 capturaria — útil pra conferir a
        seleção de área (F11) antes de rodar o pipeline de verdade."""
        self._outline_region = region
        self.update()

    def hide_region_outline(self) -> None:
        self._outline_region = None
        self.update()

    # -- desenho ----------------------------------------------------------

    def _to_logical(self, bbox) -> QRect:
        """Pixel físico do desktop → retângulo lógico local do widget."""
        return physical_to_logical(bbox, self._current_screen())

    def _fit_font(self, painter: QPainter, rect: QRect, text: str) -> QFont:
        """Busca binária no tamanho da fonte até o texto caber na caixa."""
        font = QFont(self._cfg.font_family)
        low, high, best = self._cfg.min_font_pt, self._cfg.max_font_pt, self._cfg.min_font_pt
        flags = int(Qt.TextFlag.TextWordWrap)
        while low <= high:
            mid = (low + high) // 2
            font.setPointSize(mid)
            bounds = QFontMetrics(font, painter.device()).boundingRect(rect, flags, text)
            if bounds.height() <= rect.height() and bounds.width() <= rect.width():
                best, low = mid, mid + 1
            else:
                high = mid - 1
        font.setPointSize(best)
        return font

    def paintEvent(self, a0) -> None:  # noqa: N802 — override do Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        if self._outline_region is not None:
            self._paint_region_outline(painter, self._outline_region)

        if self._status:
            self._paint_status(painter)
            return

        box = QColor(*self._cfg.box_color)
        text_color = QColor(*self._cfg.text_color)
        pad = self._cfg.padding
        flags = int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignCenter)

        for block in self._blocks:
            content = block.text
            if not content:
                continue
            rect = self._to_logical(block.bbox).adjusted(-pad, -pad, pad, pad)

            painter.setBrush(box)
            if block.needs_review:
                # O gate marcou o reconhecimento como duvidoso. A borda é o aviso: ler
                # uma tradução incerta sabendo que ela é incerta é muito melhor que
                # lê-la com a mesma aparência confiante de um acerto.
                painter.setPen(QPen(QColor(*self._cfg.review_color), 2))
            else:
                painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, self._cfg.corner_radius, self._cfg.corner_radius)

            inner = rect.adjusted(pad, pad, -pad, -pad)
            painter.setFont(self._fit_font(painter, inner, content))
            painter.setPen(QPen(text_color))
            painter.drawText(inner, flags, content)

    def _paint_region_outline(self, painter: QPainter, region: Region) -> None:
        bbox = (region.left, region.top, region.right, region.bottom)
        rect = self._to_logical(bbox)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(*self._cfg.outline_color), 3, Qt.PenStyle.DashLine))
        painter.drawRect(rect)

    def _paint_status(self, painter: QPainter) -> None:
        font = QFont(self._cfg.font_family, 12)
        painter.setFont(font)
        metrics = QFontMetrics(font, painter.device())
        rect = metrics.boundingRect(self._status).adjusted(-12, -8, 12, 8)
        rect.moveTo(QPoint(24, 24))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(*self._cfg.box_color))
        painter.drawRoundedRect(rect, 6, 6)
        painter.setPen(QPen(QColor(*self._cfg.text_color)))
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), self._status)
