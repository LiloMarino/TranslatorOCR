"""Baixa os pesos que não vêm por pip.

    uv run scripts/fetch_models.py             # baixa o que estiver faltando
    uv run scripts/fetch_models.py detector    # só um grupo
    uv run scripts/fetch_models.py --force     # rebaixa mesmo se já existe

Os modelos do RapidOCR não estão aqui — o próprio pacote os busca no primeiro uso.
Estes dois não têm esse mecanismo, então o download é explícito.

Idempotente: um arquivo já presente com o tamanho esperado é pulado. Só stdlib —
não adiciona dependência ao projeto.
"""

from __future__ import annotations

import argparse
import shutil
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"

GREEN = "\033[32m"
RED = "\033[31m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

HF = "https://huggingface.co/{repo}/resolve/main/{path}"


@dataclass(frozen=True)
class Asset:
    repo: str
    remote: str
    local: str
    size: int  # bytes exatos, conferidos contra a API do HF

    @property
    def url(self) -> str:
        return HF.format(repo=self.repo, path=self.remote)

    @property
    def path(self) -> Path:
        return MODELS / self.local


# Detector de balão. Apache-2.0. RT-DETR-v2 com o pós-processamento embutido no
# grafo: as saídas já saem em coordenada da imagem original.
#
# Escolhido no lugar do comic-text-detector, que é GPL-3.0, tem entrada de shape fixo
# e cujas 3 classes são idioma (eng/ja/unknown), não balão. Este devolve
# bubble/text_bubble/text_free, que é o que o agrupamento precisa.
#
# Se a VRAM apertar com as duas sessões ONNX abertas, o mesmo repo tem
# `detector_int8.onnx` (43.838.857 B) e `detector-v4-s_int8.onnx` (11.120.765 B).
DETECTOR = [
    Asset(
        repo="ogkalu/comic-text-and-bubble-detector",
        remote="detector.onnx",
        local="comic-bubble-detector.onnx",
        size=168_481_531,
    ),
]

# NMT local en→pt (tier 1). Modelo já convertido para CTranslate2 — não há passo de
# conversão, e `compute_type="int8"` requantiza no load.
#
# O modelo upstream é Helsinki-NLP/opus-mt-tc-big-en-pt, CC-BY-4.0. O repo do mirror
# está tagueado apache-2.0, o que contradiz o upstream; vale a licença do upstream.
NMT = [
    Asset("ooeoeo/opus-mt-tc-big-en-pt-ct2-float16", f, f"opus-mt-en-pt-ct2/{f}", size)
    for f, size in [
        ("model.bin", 467_111_989),
        ("source.spm", 802_741),
        ("target.spm", 824_855),
        ("shared_vocabulary.json", 1_008_431),
        ("config.json", 223),
    ]
]

# Tier de LLM local. Qwen3-4B em Q4_K_M cabe com folga nos 6GB da VRAM ao lado
# de OCR+detector e é mais rápido por bloco que alternativas maiores. Requer
# `uv sync --group llm` (ver pyproject.toml) antes de rodar o app com o tier
# habilitado.
LLM = [
    Asset(
        repo="Qwen/Qwen3-4B-GGUF",
        remote="Qwen3-4B-Q4_K_M.gguf",
        local="Qwen3-4B-Q4_K_M.gguf",
        size=2_497_280_256,
    ),
]

GROUPS = {"detector": DETECTOR, "nmt": NMT, "llm": LLM}


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def _progress(done: int, total: int, started: float) -> None:
    elapsed = time.perf_counter() - started
    rate = done / elapsed if elapsed > 0 else 0
    pct = f"{done / total * 100:5.1f}%" if total else "  ?  "
    line = f"    {pct}  {_human(done)}/{_human(total)}  {_human(rate)}/s"
    print(f"\r{DIM}{line}{RESET}", end="", flush=True)


def download(asset: Asset, force: bool) -> bool:
    target = asset.path
    if not force and target.is_file() and target.stat().st_size == asset.size:
        print(f"  {DIM}já presente{RESET}  {asset.local}")
        return True

    print(f"  {BOLD}baixando{RESET}     {asset.local}  {DIM}({_human(asset.size)}){RESET}")
    target.parent.mkdir(parents=True, exist_ok=True)
    # Escreve em .part e só renomeia no fim: um download interrompido não deixa para
    # trás um arquivo truncado que a checagem de tamanho depois trataria como válido.
    partial = target.with_suffix(target.suffix + ".part")
    started = time.perf_counter()
    try:
        request = urllib.request.Request(asset.url, headers={"User-Agent": "translatorocr"})
        with urllib.request.urlopen(request) as response, partial.open("wb") as fh:
            total = int(response.headers.get("Content-Length") or asset.size)
            done = 0
            while chunk := response.read(1 << 20):
                fh.write(chunk)
                done += len(chunk)
                _progress(done, total, started)
        print()
    except (urllib.error.URLError, OSError) as exc:
        partial.unlink(missing_ok=True)
        print(f"\n  {RED}falhou{RESET}       {asset.local}: {exc}")
        return False

    actual = partial.stat().st_size
    if actual != asset.size:
        partial.unlink(missing_ok=True)
        print(
            f"  {RED}tamanho inesperado{RESET} em {asset.local}: "
            f"{actual} bytes, esperava {asset.size}. O modelo pode ter sido republicado."
        )
        return False

    partial.replace(target)
    return True


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
    free = shutil.disk_usage(ROOT).free
    if free < total_bytes * 1.2:
        print(f"{RED}Espaço em disco insuficiente:{RESET} precisa de ~{_human(total_bytes)}.")
        return 1

    ok = True
    for name in wanted:
        print(f"\n{BOLD}=== {name} ==={RESET}")
        for asset in GROUPS[name]:
            ok &= download(asset, args.force)

    if not ok:
        print(f"\n{RED}{BOLD}Algum download falhou.{RESET} Rode de novo — o que já veio é pulado.")
        return 1
    print(f"\n{GREEN}{BOLD}Modelos prontos em {MODELS}.{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
