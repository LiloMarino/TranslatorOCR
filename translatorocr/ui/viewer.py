"""Janela que mostra uma imagem de arquivo e desenha as traduções nela mesma.

É o `--image`: rodar o app contra uma página salva, **sem a tela participar**. Com
captura de tela de verdade é preciso deixar a página aberta e não encostar na máquina —
qualquer janela que passe na frente entra na foto e estraga o resultado. Aqui a imagem
vai direto para o pipeline (`backends/capture_still.py`) e nada do que estiver
acontecendo na tela interfere.

A roda do mouse rola a página, o que alimenta o rastreio com quadros sucessivos de
verdade: é assim que o modo de leitura fica testável sem abrir mangá nenhum.

Do ponto de vista do `App` esta janela é o overlay: expõe os mesmos métodos. O que ela
**não** exercita é a captura de tela, o DPI e os flags Win32 do overlay — para esses,
vale subir o app normalmente (e o `--debug-dump` mostra o que a captura enxergou).
"""

from __future__ import annotations

import logging

import numpy as np
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QWidget

from ..backends.capture_still import StillCapture
from ..config import OverlayConfig
from ..models import Region, TextBlock
from .overlay import paint_blocks

log = logging.getLogger(__name__)

# Quanto uma "paradinha" da roda rola, em pixels da imagem.
_WHEEL_STEP = 120


class ImageViewer(QWidget):
    """Visualizador da página, com as caixas desenhadas por cima."""

    # A imagem nunca passa pela tela, então não há nada de que se esconder. Existe para
    # o `App` poder tratar esta janela e o overlay do mesmo jeito.
    hidden_from_capture = True

    def __init__(self, cfg: OverlayConfig, capture: StillCapture, title: str) -> None:
        super().__init__()
        self._cfg = cfg
        self._capture = capture
        self._blocks: list[TextBlock] = []
        self._status: str | None = None
        self._outline: Region | None = None
        self.setWindowTitle(f"TranslatorOCR — {title}")
        self.resize(900, 820)

    # -- o que o App chama, igual ao overlay -------------------------------

    def cover_screen(self, screen=None) -> None:
        """No overlay isto cobre o monitor. Aqui a janela tem tamanho próprio."""

    def set_blocks(self, blocks: list[TextBlock]) -> None:
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

    def clear_status(self, message: str) -> None:
        if self._status == message:
            self.clear()

    def show_region_outline(self, region: Region) -> None:
        self._outline = region
        self.update()

    def hide_region_outline(self) -> None:
        self._outline = None
        self.update()

    # -- a viewport --------------------------------------------------------

    def capture_region(self) -> Region:
        """A área da página que o pipeline vai ler: o tamanho desta janela, em pixel
        físico, que é a unidade em que o `StillCapture` recorta."""
        ratio = self.devicePixelRatioF()
        return Region(
            left=0,
            top=0,
            width=max(1, int(self.width() * ratio)),
            height=max(1, int(self.height() * ratio)),
        )

    def wheelEvent(self, a0) -> None:  # noqa: N802 — override do Qt
        if a0 is None:
            return
        steps = a0.angleDelta().y() / 120.0
        self._capture.scroll_to(self._capture.offset - int(steps * _WHEEL_STEP))
        a0.accept()
        # Só a imagem se move agora; as caixas seguem no lugar até o rastreio medir o
        # deslocamento no próximo quadro. É o mesmo atraso de um quadro que existe
        # rolando um navegador de verdade.
        self.update()

    # -- desenho -----------------------------------------------------------

    def _to_logical(self, bbox) -> QRect:
        """Pixel da viewport → retângulo lógico do widget.

        Os bboxes chegam em coordenada da captura, e o `StillCapture` usa origem (0, 0),
        então aqui só falta desfazer o fator de escala do monitor.
        """
        ratio = self.devicePixelRatioF()
        x1, y1, x2, y2 = (int(v / ratio) for v in bbox)
        return QRect(x1, y1, max(1, x2 - x1), max(1, y2 - y1))

    def _fit_font(self, painter: QPainter, rect: QRect, text: str) -> QFont:
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
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self._paint_page(painter)

        if self._outline is not None:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(*self._cfg.outline_color), 3, Qt.PenStyle.DashLine))
            bbox = (
                self._outline.left,
                self._outline.top,
                self._outline.right,
                self._outline.bottom,
            )
            painter.drawRect(self._to_logical(bbox))

        if self._status:
            self._paint_status(painter)
            return

        painter.setOpacity(self._cfg.window_alpha / 255)
        paint_blocks(painter, self._blocks, self._cfg, self._to_logical, self._fit_font)

    def _paint_page(self, painter: QPainter) -> None:
        shot = self._capture.grab(self.capture_region())
        if shot is None:
            return
        # BGR (convenção do pipeline) → RGB, que é o que o QImage espera. `tobytes()`
        # em vez do buffer do numpy porque o QImage não copia: com o buffer, a imagem
        # apontaria para memória que o numpy pode liberar antes do `fromImage`.
        rgb = np.ascontiguousarray(shot.image[:, :, ::-1])
        height, width = rgb.shape[:2]
        image = QImage(rgb.tobytes(), width, height, 3 * width, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(self.devicePixelRatioF())
        painter.drawPixmap(0, 0, pixmap)

    def _paint_status(self, painter: QPainter) -> None:
        font = QFont(self._cfg.font_family, 12)
        painter.setFont(font)
        metrics = QFontMetrics(font, painter.device())
        rect = metrics.boundingRect(self._status or "").adjusted(-12, -8, 12, 8)
        rect.moveTo(24, 24)
        painter.setOpacity(self._cfg.window_alpha / 255)
        painter.fillRect(rect, QColor(*self._cfg.box_color))
        painter.setOpacity(1.0)
        painter.setPen(QPen(QColor(*self._cfg.text_color)))
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), self._status or "")
