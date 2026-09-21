"""Overlay click-through: caixas escuras desenhadas na posição de cada bloco.

Exibe os blocos traduzidos sobre a tela, click-through, sem roubar foco e **sem aparecer
na captura**.

Três pontos delicados:

* **Click-through.** Os flags do Qt sozinhos não bastam no Windows. São
  `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE`, aplicados no HWND depois
  do `show()`, que garantem que o overlay nunca intercepte clique nem roube foco do
  jogo ou do navegador.
* **Coordenadas.** Os blocos chegam em pixels físicos do desktop; a geometria de
  widget no Qt é lógica. A divisão pelo `devicePixelRatio` acontece aqui, e só
  aqui — a não ser pela região do Win32, que é pedida em pixel físico e por isso
  desfaz a divisão logo em seguida.
* **Sair da captura.** O app fotografa a tela, e o overlay está na tela. Sem tratar
  isso, o modo de leitura mediria a rolagem com as próprias caixas paradas no quadro e
  o OCR releria a própria tradução em português. Quem resolve é
  `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`: a janela continua visível na tela
  e some de qualquer captura (medido: 15.7% da área virava caixa antes, 0.0% depois).

  **O Windows recusa essa flag em janela com alpha por pixel** — que é o que
  `WA_TranslucentBackground` liga, e era como este overlay funcionava (a chamada volta
  com erro 8). A saída é fazer a mesma coisa pelo Win32: recortar a janela na forma das
  caixas com `SetWindowRgn` e pedir translucidez **constante** com
  `SetLayeredWindowAttributes`. O visual é o mesmo, com um detalhe: o canto arredondado
  agora é cortado pela região, então fica com a borda mais dura em vez de suavizada, e
  a moldura da área de captura é contínua em vez de tracejada.

  Como a translucidez deixou de vir do canal alpha, **a região tem que estar sempre em
  dia**: fora dela a janela é opaca, e uma região grande demais cobriria a tela. Por
  isso todo método que muda o conteúdo chama `_sync_region()` antes do `update()`.
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

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
LWA_ALPHA = 0x00000002
# Windows 10 2004+. A janela some de toda captura de tela, continuando visível no monitor.
WDA_EXCLUDEFROMCAPTURE = 0x00000011
RGN_OR = 2
RGN_DIFF = 4

# Espessura da moldura que marca a área de captura (F7).
_OUTLINE_WIDTH = 3


def _user32() -> ctypes.WinDLL:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
    user32.SetLayeredWindowAttributes.argtypes = [
        wintypes.HWND,
        wintypes.COLORREF,
        ctypes.c_ubyte,
        wintypes.DWORD,
    ]
    user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
    return user32


def _gdi32() -> ctypes.WinDLL:
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    # Sem argtypes o ctypes trunca o HRGN em 32 bits e a chamada estoura.
    gdi32.CreateRectRgn.argtypes = [ctypes.c_int] * 4
    gdi32.CreateRectRgn.restype = wintypes.HRGN
    gdi32.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
    gdi32.CreateRoundRectRgn.restype = wintypes.HRGN
    gdi32.CombineRgn.argtypes = [wintypes.HRGN, wintypes.HRGN, wintypes.HRGN, ctypes.c_int]
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    return gdi32


def _make_click_through(hwnd: int, alpha: int) -> None:
    user32 = _user32()
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
    # Translucidez constante, no lugar do canal alpha por pixel do Qt.
    user32.SetLayeredWindowAttributes(hwnd, 0, alpha, LWA_ALPHA)


def _exclude_from_capture(hwnd: int) -> bool:
    return bool(_user32().SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE))


def _apply_region(hwnd: int, solids: list[QRect], frames: list[QRect], radius: int) -> None:
    """Recorta a janela nos retângulos desenhados, em pixel físico da janela.

    `frames` são molduras vazadas (a borda da área de captura); `solids`, as caixas.
    """
    gdi32 = _gdi32()
    combined = gdi32.CreateRectRgn(0, 0, 0, 0)
    for rect in solids:
        # +1 porque a região do Win32 é exclusiva na borda direita/inferior.
        piece = gdi32.CreateRoundRectRgn(
            rect.left(), rect.top(), rect.right() + 2, rect.bottom() + 2, radius, radius
        )
        gdi32.CombineRgn(combined, combined, piece, RGN_OR)
        gdi32.DeleteObject(piece)
    for rect in frames:
        outer = gdi32.CreateRectRgn(rect.left(), rect.top(), rect.right() + 2, rect.bottom() + 2)
        inner = gdi32.CreateRectRgn(
            rect.left() + _OUTLINE_WIDTH,
            rect.top() + _OUTLINE_WIDTH,
            rect.right() + 2 - _OUTLINE_WIDTH,
            rect.bottom() + 2 - _OUTLINE_WIDTH,
        )
        gdi32.CombineRgn(outer, outer, inner, RGN_DIFF)
        gdi32.CombineRgn(combined, combined, outer, RGN_OR)
        gdi32.DeleteObject(inner)
        gdi32.DeleteObject(outer)
    # O sistema toma posse da região; não se apaga `combined` depois disto.
    _user32().SetWindowRgn(hwnd, combined, True)


class OverlayWindow(QWidget):
    def __init__(self, cfg: OverlayConfig) -> None:
        super().__init__()
        self._cfg = cfg
        self._blocks: list[TextBlock] = []
        self._status: str | None = None
        # Independente de _blocks/_status: liga/desliga com o hotkey de outline, sem ser limpo pelo
        # F9 (dismiss) nem pelo próximo F8. É só um guia visual da área de captura.
        self._outline_region: Region | None = None
        # Falso quando o Windows recusou a exclusão de captura: aí o app volta a apagar o
        # overlay antes de fotografar, e o modo de leitura fica indisponível.
        self.hidden_from_capture = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        # Sem `WA_TranslucentBackground`: é ele que o Windows recusa junto com a exclusão
        # de captura (ver o docstring do módulo). Quem define a forma é a região.
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

    # Os overrides do Qt usam `a0` porque é assim que os stubs do PyQt6 nomeiam o
    # parâmetro; divergir daí quebra a compatibilidade de assinatura.
    def showEvent(self, a0) -> None:  # noqa: N802 — override do Qt
        super().showEvent(a0)
        try:
            hwnd = int(self.winId())
            _make_click_through(hwnd, self._cfg.window_alpha)
            self.hidden_from_capture = _exclude_from_capture(hwnd)
            if not self.hidden_from_capture:
                log.warning(
                    "O Windows recusou tirar o overlay da captura; o app vai apagá-lo "
                    "antes de cada captura e o modo de leitura fica indisponível."
                )
            # Antes de qualquer pintura a região tem que existir, senão a janela opaca
            # cobre a tela inteira por um quadro.
            self._sync_region()
        except Exception:
            log.exception("Não foi possível preparar a janela do overlay")

    def _current_screen(self) -> QScreen | None:
        return self.screen() or QGuiApplication.primaryScreen()

    def cover_screen(self, screen: QScreen | None = None) -> None:
        """Cobre a tela pedida (ou aquela em que a janela está), em coordenadas lógicas."""
        screen = screen or self._current_screen()
        if screen is None:
            log.warning("Nenhuma tela disponível; o overlay fica sem geometria definida.")
            return
        self.setGeometry(screen.geometry())
        self._sync_region()

    # -- conteúdo ---------------------------------------------------------

    def set_blocks(self, blocks: list[TextBlock]) -> None:
        """Idempotente: permite atualizar tradução sem recriar o overlay."""
        self._blocks = blocks
        self._status = None
        self._refresh()

    def set_status(self, message: str | None) -> None:
        self._status = message
        self._blocks = []
        self._refresh()

    def clear(self) -> None:
        self._blocks = []
        self._status = None
        self._refresh()

    def clear_status(self, message: str) -> None:
        """Apaga a mensagem só se ela ainda for a que está na tela.

        Para os timers de "Pronto" e "Nenhum texto encontrado": com `clear()` eles
        apagavam também a tradução que chegasse antes de o timer vencer — F8 logo depois
        do "Pronto" mostrava a tradução por meio segundo e sumia.
        """
        if self._status == message:
            self.clear()

    def show_region_outline(self, region: Region) -> None:
        """Mostra uma borda na área que o F8 capturaria — útil pra conferir a
        seleção de área (F11) antes de rodar o pipeline de verdade."""
        self._outline_region = region
        self._refresh()

    def hide_region_outline(self) -> None:
        self._outline_region = None
        self._refresh()

    def _refresh(self) -> None:
        self._sync_region()
        self.update()

    # -- forma da janela ---------------------------------------------------

    def _block_rects(self) -> list[QRect]:
        pad = self._cfg.padding
        return [
            self._to_logical(block.bbox).adjusted(-pad, -pad, pad, pad)
            for block in self._blocks
            if block.text
        ]

    def _status_rect(self) -> QRect | None:
        if not self._status:
            return None
        metrics = QFontMetrics(QFont(self._cfg.font_family, 12), self)
        rect = metrics.boundingRect(self._status).adjusted(-12, -8, 12, 8)
        rect.moveTo(QPoint(24, 24))
        return rect

    def _outline_rect(self) -> QRect | None:
        if self._outline_region is None:
            return None
        region = self._outline_region
        return self._to_logical((region.left, region.top, region.right, region.bottom))

    def _sync_region(self) -> None:
        """Recorta a janela exatamente no que o `paintEvent` vai desenhar.

        Tem que espelhar o `paintEvent`: o que ficar de fora da região não aparece, e o
        que entrar sem ser pintado vira um retângulo opaco na tela.
        """
        if not self.isVisible():
            return
        ratio = self.devicePixelRatioF()

        def physical(rect: QRect) -> QRect:
            return QRect(
                int(rect.left() * ratio),
                int(rect.top() * ratio),
                int(rect.width() * ratio),
                int(rect.height() * ratio),
            )

        solids = [physical(r) for r in self._block_rects()]
        status = self._status_rect()
        if status is not None:
            solids.append(physical(status))
        outline = self._outline_rect()
        frames = [physical(outline)] if outline is not None else []
        try:
            _apply_region(int(self.winId()), solids, frames, self._cfg.corner_radius)
        except Exception:
            log.exception("Não foi possível recortar a janela do overlay")

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
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # Sem suavizar as formas: quem define a borda é a região, e uma borda suavizada
        # aqui só produziria um halo contra o que estiver fora dela.
        outline = self._outline_rect()
        if outline is not None:
            painter.fillRect(outline, QColor(*self._cfg.outline_color))

        if self._status:
            self._paint_status(painter)
            return

        paint_blocks(painter, self._blocks, self._cfg, self._to_logical, self._fit_font)

    def _paint_status(self, painter: QPainter) -> None:
        rect = self._status_rect()
        if rect is None:
            return
        painter.setFont(QFont(self._cfg.font_family, 12))
        painter.fillRect(rect, QColor(*self._cfg.box_color))
        painter.setPen(QPen(QColor(*self._cfg.text_color)))
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), self._status or "")


def paint_blocks(painter, blocks, cfg: OverlayConfig, to_logical, fit_font) -> None:
    """Desenha as caixas traduzidas.

    Fora da classe porque o visualizador de imagem (`ui/viewer.py`) desenha as mesmas
    caixas no próprio widget, e o que se vê testando tem que ser o que o app mostra.
    """
    box = QColor(*cfg.box_color)
    review = QColor(*cfg.review_color)
    text_color = QColor(*cfg.text_color)
    pad = cfg.padding
    flags = int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignCenter)

    for block in blocks:
        content = block.text
        if not content:
            continue
        rect = to_logical(block.bbox).adjusted(-pad, -pad, pad, pad)
        painter.fillRect(rect, box)
        if block.needs_review:
            # O gate marcou o reconhecimento como duvidoso. A borda é o aviso: ler
            # uma tradução incerta sabendo que ela é incerta é muito melhor que
            # lê-la com a mesma aparência confiante de um acerto.
            painter.setPen(QPen(review, 2))
            painter.drawRect(rect.adjusted(1, 1, -1, -1))

        inner = rect.adjusted(pad, pad, -pad, -pad)
        painter.setFont(fit_font(painter, inner, content))
        painter.setPen(QPen(text_color))
        painter.drawText(inner, flags, content)
