"""Ícone na bandeja do Windows, perto do relógio.

Dá para usar o app sem decorar tecla: o menu tem os mesmos comandos das hotkeys, mais
as duas escolhas que dependem da máquina — em qual monitor capturar, e se o console
mostra os detalhes internos. Não há arquivo de configuração; o que se escolhe aqui vale
até fechar o app.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPixmap,
    QPolygonF,
    QScreen,
)
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .commands import Command


def _icon() -> QIcon:
    """Um balão de fala âmbar com um "A" — desenhado aqui para não precisar de asset."""
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(230, 160, 30))
    painter.drawEllipse(4, 4, 56, 44)
    painter.drawPolygon(QPolygonF([QPointF(16, 40), QPointF(12, 60), QPointF(30, 44)]))
    painter.setPen(QColor(30, 30, 30))
    painter.setFont(QFont("Segoe UI", 26, QFont.Weight.Bold))
    painter.drawText(4, 4, 56, 44, int(Qt.AlignmentFlag.AlignCenter), "A")
    painter.end()
    return QIcon(pixmap)


def _menu_text(command: Command) -> str:
    return f"{command.label}\t{command.key}" if command.key else command.label


class TrayIcon(QSystemTrayIcon):
    def __init__(
        self,
        commands: list[Command],
        quit_command: Command,
        current_screen: Callable[[], QScreen | None],
        on_screen: Callable[[QScreen], None],
        on_verbose: Callable[[bool], None],
        verbose: bool,
    ) -> None:
        super().__init__(_icon())
        self._current_screen = current_screen
        self._on_screen = on_screen
        self._toggles: dict[str, QAction] = {}

        menu = QMenu()
        for command in commands:
            action = menu.addAction(_menu_text(command))
            assert action is not None
            action.setCheckable(command.toggle)
            action.triggered.connect(lambda _checked=False, c=command: c.run())
            if command.toggle and command.key:
                self._toggles[command.key] = action
        menu.addSeparator()

        self._monitors = menu.addMenu("Monitor")
        assert self._monitors is not None
        # Montado ao abrir: monitor pode ser conectado ou removido com o app aberto.
        self._monitors.aboutToShow.connect(self._fill_monitors)

        details = menu.addAction("Detalhes no console")
        assert details is not None
        details.setCheckable(True)
        details.setChecked(verbose)
        details.toggled.connect(on_verbose)
        menu.addSeparator()

        quit_action = menu.addAction(_menu_text(quit_command))
        assert quit_action is not None
        quit_action.triggered.connect(lambda _checked=False: quit_command.run())

        # O menu precisa de referência viva: `setContextMenu` não toma posse dele.
        self._menu = menu
        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)
        self._primary = commands[0].run if commands else None
        self.set_state("Carregando...")

    def set_state(self, text: str) -> None:
        self.setToolTip(f"TranslatorOCR — {text}")

    def set_checked(self, key: str, checked: bool) -> None:
        """Mantém o check do menu em dia quando o toggle vem pela hotkey."""
        action = self._toggles.get(key)
        if action is not None:
            action.setChecked(checked)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # Clique simples no ícone roda o primeiro comando da lista, o mais usado.
        if reason == QSystemTrayIcon.ActivationReason.Trigger and self._primary is not None:
            self._primary()

    def _fill_monitors(self) -> None:
        assert self._monitors is not None
        self._monitors.clear()
        group = QActionGroup(self._monitors)
        current = self._current_screen()
        primary = QApplication.primaryScreen()
        for index, screen in enumerate(QApplication.screens(), 1):
            geo = screen.size()
            ratio = screen.devicePixelRatio()
            name = f"{index}: {int(geo.width() * ratio)}x{int(geo.height() * ratio)}"
            if screen is primary:
                name += " (principal)"
            action = self._monitors.addAction(name)
            assert action is not None
            action.setCheckable(True)
            action.setChecked(screen is current)
            action.setActionGroup(group)
            action.triggered.connect(lambda _checked=False, s=screen: self._on_screen(s))
