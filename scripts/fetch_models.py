"""Baixa os pesos que não vêm por pip.

    uv run scripts/fetch_models.py             # baixa o que estiver faltando
    uv run scripts/fetch_models.py detector    # só um grupo
    uv run scripts/fetch_models.py --force     # rebaixa mesmo se já existe

O app já baixa sozinho o detector e o NMT na primeira execução; este script serve para
baixar antes, forçar um re-download, ou buscar o LLM (fora do download automático).
A lista de modelos e o download moram em `translatorocr/assets.py`.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from translatorocr.assets import GROUPS, MODELS_DIR, ROOT, download, human

GREEN = "\033[32m"
RED = "\033[31m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _progress(done: int, total: int, rate: float) -> None:
    pct = f"{done / total * 100:5.1f}%" if total else "  ?  "
    line = f"    {pct}  {human(done)}/{human(total)}  {human(rate)}/s"
    print(f"\r{DIM}{line}{RESET}", end="", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fetch_models", description=__doc__)
    parser.add_argument(
        "groups",
        nargs="*",
        choices=[*GROUPS, []],
        help=f"grupos a baixar (default: todos). Opções: {', '.join(GROUPS)}",
    )
    parser.add_argument("--force", action="store_true", help="rebaixa mesmo se já existe")
    args = parser.parse_args(argv)

    wanted = args.groups or list(GROUPS)
    total_bytes = sum(a.size for g in wanted for a in GROUPS[g])
    if shutil.disk_usage(ROOT).free < total_bytes * 1.2:
        print(f"{RED}Espaço em disco insuficiente:{RESET} precisa de ~{human(total_bytes)}.")
        return 1

    ok = True
    for name in wanted:
        print(f"\n{BOLD}=== {name} ==={RESET}")
        for asset in GROUPS[name]:
            if not args.force and asset.present():
                print(f"  {DIM}já presente{RESET}  {asset.local}")
                continue
            print(f"  {BOLD}baixando{RESET}     {asset.local}  {DIM}({human(asset.size)}){RESET}")
            started = time.perf_counter()
            try:
                download(asset, _progress)
                print(f"  {DIM}({time.perf_counter() - started:.0f}s){RESET}")
            except (urllib.error.URLError, OSError) as exc:
                print(f"\n  {RED}falhou{RESET}       {asset.local}: {exc}")
                ok = False

    if not ok:
        print(f"\n{RED}{BOLD}Algum download falhou.{RESET} Rode de novo — o que já veio é pulado.")
        return 1
    print(f"\n{GREEN}{BOLD}Modelos prontos em {MODELS_DIR}.{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
