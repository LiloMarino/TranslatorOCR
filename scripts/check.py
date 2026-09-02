"""Roda todas as verificações do projeto de uma vez.

    uv run scripts/check.py            # verifica, não altera nada
    uv run scripts/check.py --fix      # formata e aplica os fixes seguros do ruff antes
    uv run scripts/check.py --no-tests # só o lint e o type check
    uv run scripts/check.py -k grupo   # argumentos extras vão para o pytest

Exit code é 0 só se tudo passou, o que torna o script utilizável em hook ou CI.
Só stdlib — não adiciona dependência ao projeto.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Faixa da largura do terminal, limitada para não ficar absurda em tela larga.
WIDTH = min(shutil.get_terminal_size((80, 20)).columns, 78)

GREEN = "\033[32m"
RED = "\033[31m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _supports_unicode() -> bool:
    """O console do Windows costuma abrir em cp1252, que não tem ✔/✘/─."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        return True
    except Exception:  # noqa: BLE001 — stdout pode ser qualquer coisa; seguimos pro fallback
        pass
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        "✔✘─".encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


if _supports_unicode():
    PASS, FAIL, RULE = "✔", "✘", "─"
else:
    PASS, FAIL, RULE = "+", "x", "-"


def header(title: str) -> None:
    print(f"\n{BOLD}=== {title} ==={RESET}", flush=True)


def run(title: str, command: list[str]) -> tuple[str, bool, float]:
    header(title)
    started = time.perf_counter()
    result = subprocess.run(command, cwd=ROOT)
    elapsed = time.perf_counter() - started
    return title, result.returncode == 0, elapsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="check", description=__doc__)
    parser.add_argument(
        "--fix",
        action="store_true",
        help="formata e aplica os fixes seguros do ruff antes de verificar",
    )
    parser.add_argument(
        "--no-tests", action="store_true", help="pula o pytest (útil para iterar rápido no lint)"
    )
    args, pytest_extra = parser.parse_known_args(argv)

    if args.fix:
        header("RUFF --fix")
        subprocess.run([sys.executable, "-m", "ruff", "format", "."], cwd=ROOT)
        subprocess.run([sys.executable, "-m", "ruff", "check", ".", "--fix"], cwd=ROOT)

    steps: list[tuple[str, list[str]]] = [
        ("RUFF FORMAT", [sys.executable, "-m", "ruff", "format", "--check", "."]),
        ("RUFF LINT", [sys.executable, "-m", "ruff", "check", ".", "--output-format", "concise"]),
        ("PYRIGHT", [sys.executable, "-m", "pyright"]),
    ]
    if not args.no_tests:
        steps.append(("PYTEST", [sys.executable, "-m", "pytest", "-q", *pytest_extra]))

    results = [run(title, command) for title, command in steps]

    print(f"\n{BOLD}{RULE * WIDTH}{RESET}")
    failed = [title for title, ok, _ in results if not ok]
    for title, ok, elapsed in results:
        mark = f"{GREEN}{PASS}{RESET}" if ok else f"{RED}{FAIL}{RESET}"
        print(f"  {mark} {title:<14} {DIM}{elapsed:5.1f}s{RESET}")

    if failed:
        print(f"\n{RED}{BOLD}FALHOU:{RESET} {', '.join(failed)}")
        if not args.fix and any(f.startswith("RUFF") for f in failed):
            print(f"{DIM}Boa parte disso sai com `uv run scripts/check.py --fix`.{RESET}")
        return 1

    print(f"\n{GREEN}{BOLD}Tudo passou.{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
