"""Hotkeys globais via `RegisterHotKey` do Win32.

API nativa do Windows para hotkey global, em vez de um hook de baixo nível — não
exige rodar como administrador.

O `WM_HOTKEY` é entregue à thread que registrou; como o Qt é dono do message loop,
ele é interceptado por um `QAbstractNativeEventFilter`.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
from collections.abc import Callable

from PyQt6 import sip
from PyQt6.QtCore import QAbstractNativeEventFilter, QByteArray, QCoreApplication

log = logging.getLogger(__name__)

WM_HOTKEY = 0x0312

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_MODIFIERS = {
    "ALT": MOD_ALT,
    "CTRL": MOD_CONTROL,
    "CONTROL": MOD_CONTROL,
    "SHIFT": MOD_SHIFT,
    "WIN": MOD_WIN,
}

# Virtual-key codes. F1..F24 são contíguos a partir de 0x70.
_VK = {f"F{i}": 0x6F + i for i in range(1, 25)}
_VK.update(
    {
        "ESC": 0x1B,
        "ESCAPE": 0x1B,
        "SPACE": 0x20,
        "INSERT": 0x2D,
        "DELETE": 0x2E,
        "HOME": 0x24,
        "END": 0x23,
        "PAGEUP": 0x21,
        "PAGEDOWN": 0x22,
        "PRINTSCREEN": 0x2C,
    }
)
_VK.update({chr(c): c for c in range(ord("A"), ord("Z") + 1)})
_VK.update({str(d): ord(str(d)) for d in range(10)})


def parse_hotkey(spec: str) -> tuple[int, int]:
    """`"ctrl+shift+F8"` → `(modificadores, virtual-key)`."""
    parts = [p.strip().upper() for p in spec.split("+") if p.strip()]
    if not parts:
        raise ValueError(f"Hotkey vazia: {spec!r}")

    modifiers = MOD_NOREPEAT
    for part in parts[:-1]:
        if part not in _MODIFIERS:
            raise ValueError(f"Modificador desconhecido em {spec!r}: {part}")
        modifiers |= _MODIFIERS[part]

    key = parts[-1]
    if key not in _VK:
        raise ValueError(f"Tecla desconhecida em {spec!r}: {key}")
    return modifiers, _VK[key]


class GlobalHotkeys(QAbstractNativeEventFilter):
    def __init__(self) -> None:
        super().__init__()
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._next_id = 1
        self._user32 = ctypes.windll.user32

    def register(self, spec: str, callback: Callable[[], None]) -> bool:
        modifiers, vk = parse_hotkey(spec)
        hotkey_id = self._next_id
        if not self._user32.RegisterHotKey(None, hotkey_id, modifiers, vk):
            log.error(
                "Não foi possível registrar a hotkey %s (erro %d) — "
                "provavelmente já está em uso por outro programa.",
                spec,
                ctypes.GetLastError(),
            )
            return False
        self._callbacks[hotkey_id] = callback
        self._next_id += 1
        log.info("Hotkey registrada: %s", spec)
        return True

    def install(self) -> None:
        app = QCoreApplication.instance()
        if app is None:
            raise RuntimeError("QApplication precisa existir antes de instalar as hotkeys.")
        app.installNativeEventFilter(self)

    def unregister_all(self) -> None:
        for hotkey_id in list(self._callbacks):
            self._user32.UnregisterHotKey(None, hotkey_id)
        self._callbacks.clear()

    # A assinatura acompanha os stubs do PyQt6: parâmetro `eventType` e retorno
    # `(bool, sip.voidptr)`. O segundo elemento é um out-param que só importa em
    # plataformas que devolvem um resultado ao sistema; aqui é sempre nulo.
    def nativeEventFilter(  # noqa: N802 — override do Qt
        self,
        eventType: QByteArray | bytes | bytearray | memoryview,  # noqa: N803 — nome do stub
        message: sip.voidptr,
    ) -> tuple[bool, sip.voidptr]:
        handled = (False, sip.voidptr(0))
        # Na prática o Qt entrega `bytes` aqui, mas a assinatura admite QByteArray,
        # que não é conversível por `bytes()`.
        kind = eventType.data() if isinstance(eventType, QByteArray) else bytes(eventType)
        if kind != b"windows_generic_MSG":
            return handled
        msg = ctypes.wintypes.MSG.from_address(int(message))
        if msg.message == WM_HOTKEY:
            callback = self._callbacks.get(int(msg.wParam))
            if callback is not None:
                callback()
                return True, sip.voidptr(0)
        return handled
