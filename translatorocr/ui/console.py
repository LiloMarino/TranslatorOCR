"""O que aparece no console para quem usa o app.

Não é log. O `logging` é diagnóstico e fica em WARNING, a menos que se peça `-v` ou se
ligue "Detalhes no console" na bandeja. Isto aqui é a interface: o que está carregando,
quais teclas existem, quanto cada tradução levou.
"""

from __future__ import annotations

import ctypes
import sys

from .commands import Command

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"
_CLEAR_LINE = "\r\033[2K"

# Uma linha de progresso está aberta (sem \n) e a próxima saída precisa fechá-la.
_open_line = False
# Com os detalhes ligados, o log escreve entre uma atualização e outra, e uma linha que
# se reescreve no lugar acabaria emendada com ele.
inline_progress = True


def setup() -> None:
    """Liga as cores ANSI no console do Windows e evita que um caractere fora do código
    de página derrube o app quando a saída é redirecionada."""
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # VIRTUAL_TERMINAL_PROCESSING
    except (AttributeError, OSError):
        pass
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(errors="replace")


def _print(text: str) -> None:
    global _open_line
    if _open_line:
        print()
        _open_line = False
    print(text, flush=True)


def header() -> None:
    _print(f"\n{BOLD}TranslatorOCR{RESET} {DIM}— tradutor de mangá, inglês → português{RESET}")


def progress(message: str) -> None:
    """Linha que se reescreve no lugar (download, carga)."""
    global _open_line
    if not inline_progress:
        _print(f"  {DIM}{message}{RESET}")
        return
    print(f"{_CLEAR_LINE}  {DIM}{message}{RESET}", end="", flush=True)
    _open_line = True


def ready(seconds: float, commands: list[Command]) -> None:
    global _open_line
    print(f"{_CLEAR_LINE}  {GREEN}Pronto{RESET} {DIM}em {seconds:.1f}s · tradução offline{RESET}\n")
    _open_line = False
    width = max(len(c.key) for c in commands)
    for command in commands:
        _print(f"  {BOLD}{command.key:<{width}}{RESET}  {command.help}")
    _print(f"\n  {DIM}Também pelo ícone perto do relógio.{RESET}\n")


def translated(blocks: int, review: int, seconds: float) -> None:
    if not blocks:
        _print(f"  {DIM}nenhum texto encontrado · {seconds:.1f}s{RESET}")
        return
    doubt = f" · {YELLOW}{review} duvidoso{'s' if review > 1 else ''}{RESET}" if review else ""
    plural = "balões" if blocks > 1 else "balão"
    _print(f"  {blocks} {plural}{doubt} {DIM}· {seconds:.1f}s{RESET}")


def info(message: str) -> None:
    _print(f"  {DIM}{message}{RESET}")


def error(message: str) -> None:
    _print(f"  {RED}Erro:{RESET} {message}")
