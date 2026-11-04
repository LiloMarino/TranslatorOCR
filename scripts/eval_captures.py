"""Mede a leitura do app contra o gabarito das capturas reais.

    uv run scripts/eval_captures.py                         # todas as pastas com gabarito
    uv run scripts/eval_captures.py --save base             # grava o resultado como "base"
    uv run scripts/eval_captures.py --against base          # compara com "base"
    uv run scripts/eval_captures.py --set ocr.model_type=server --against base
    uv run scripts/eval_captures.py -v                      # lista cada região que falhou

Cada tela de `eval/captures/<data>/` passa pelo mesmo caminho do app (OCR, agrupamento e
portão), e os blocos que sobram são casados com as regiões do `labels.json` pela
sobreposição: um bloco pertence à região que cobre a maior parte dele. Só entram na
conta as regiões com texto no gabarito (`agreed` e `reviewed`). Região cortada pela
borda (`partial`) não conta para nenhum lado.

Três números por região, e um por tela:
- achado: algum bloco caiu na região;
- exato: o texto do app, normalizado, é igual ao do gabarito;
- CER: distância de edição em caracteres sobre o tamanho do gabarito; região não achada
  conta 1.0;
- lixo: bloco que não caiu em região com texto nem em região cortada.

O mesmo balão aparece em várias telas seguidas da rolagem, então o relatório mostra
também quantos textos distintos há por trás das regiões.

`--save` grava em `eval/results/<nome>.json`, local como as capturas, e `--against`
diz quais regiões mudaram de estado: um total igual pode esconder uma troca.

Sem cobertura de teste: ferramenta de medida, não pipeline de produção.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval_pages import load_page
from label_captures import AGREED, CAPTURES, PARTIAL, REVIEWED, load_labels
from textmatch import cer, normalize

from translatorocr.config import Config
from translatorocr.models import BBox, TextBlock

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "eval" / "results"
WITH_TEXT = {AGREED, REVIEWED}

# Fração do bloco que precisa cair dentro da região para ele pertencer a ela.
MIN_COVER = 0.5

GREEN = "\033[32m"
RED = "\033[31m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


@dataclass
class RegionResult:
    key: str
    kind: str
    gold: str
    read: str
    found: bool
    exact: bool
    cer: float


@dataclass
class Run:
    regions: list[RegionResult] = field(default_factory=list)
    spurious: int = 0
    screens: int = 0
    ocr_ms: list[float] = field(default_factory=list)


def apply_overrides(cfg: Config, overrides: list[str]) -> None:
    """`secao.campo=valor`, convertido para o tipo do valor atual do campo."""
    for item in overrides:
        name, _, raw = item.partition("=")
        section_name, _, field_name = name.partition(".")
        section = getattr(cfg, section_name)
        current = getattr(section, field_name)
        if isinstance(current, bool):
            value: Any = raw.lower() in {"1", "true", "sim"}
        else:
            value = type(current)(raw)
        setattr(cfg, section_name, dataclasses.replace(section, **{field_name: value}))


def cover(block: BBox, region: list[int]) -> float:
    bx1, by1, bx2, by2 = block
    rx1, ry1, rx2, ry2 = region
    w = max(0, min(bx2, rx2) - max(bx1, rx1))
    h = max(0, min(by2, ry2) - max(by1, ry1))
    area = max(1, (bx2 - bx1) * (by2 - by1))
    return w * h / area


def score_screen(key: str, blocks: list[TextBlock], records: list[dict]) -> tuple[list, int]:
    # Cada bloco vai para a região que mais o cobre; o texto de uma região é o dos
    # seus blocos de cima para baixo.
    owned: dict[int, list[TextBlock]] = {}
    spurious = 0
    for block in blocks:
        covers = [cover(block.bbox, r["bbox"]) for r in records]
        best = max(range(len(records)), key=covers.__getitem__, default=-1)
        if best < 0 or covers[best] < MIN_COVER:
            spurious += 1
            continue
        status = records[best]["status"]
        if status == PARTIAL:
            continue
        if status not in WITH_TEXT:
            spurious += 1
            continue
        owned.setdefault(best, []).append(block)

    results = []
    for i, record in enumerate(records):
        if record["status"] not in WITH_TEXT:
            continue
        mine = sorted(owned.get(i, []), key=lambda b: b.bbox[1])
        read = " ".join(b.source for b in mine)
        gold = record["text"]
        results.append(
            RegionResult(
                key=f"{key}#{i}",
                kind=record["kind"],
                gold=gold,
                read=read,
                found=bool(mine),
                exact=bool(mine) and normalize(read) == normalize(gold),
                cer=cer(read, gold) if mine else 1.0,
            )
        )
    return results, spurious


def measure(cfg: Config, folders: list[Path]) -> Run:
    from translatorocr.core.gate import apply_gate
    from translatorocr.core.grouping import group
    from translatorocr.registry import build_ocr

    ocr = build_ocr(cfg)
    run = Run()
    warmed = False
    for folder in folders:
        labels = load_labels(folder)
        for stem, records in sorted(labels["images"].items()):
            image = load_page(folder / f"{stem}.webp")
            if not warmed:
                ocr.read(image)
                warmed = True
            started = time.perf_counter()
            lines = ocr.read(image)
            run.ocr_ms.append((time.perf_counter() - started) * 1000)
            # A captura do app tem origem (0, 0) e escala 1 aqui: o bbox fica em
            # pixels da imagem, o mesmo espaço do gabarito.
            blocks = apply_gate(group(lines, cfg.grouping), cfg.gate, cfg.ocr.lang)
            results, spurious = score_screen(f"{folder.name}/{stem}", blocks, records)
            run.regions.extend(results)
            run.spurious += spurious
            run.screens += 1
    return run


def pct(part: int, total: int) -> str:
    return f"{part}/{total} ({100 * part / max(1, total):.1f}%)"


def summarize(label: str, regions: list[RegionResult]) -> None:
    total = len(regions)
    distinct = len({normalize(r.gold) for r in regions})
    found = sum(r.found for r in regions)
    exact = sum(r.exact for r in regions)
    cers = [r.cer for r in regions]
    print(f"\n{BOLD}{label}: {total} regiões com texto ({distinct} textos distintos){RESET}")
    print(f"  achado   {pct(found, total)}")
    print(f"  exato    {pct(exact, total)}")
    mean, median = statistics.fmean(cers), statistics.median(cers)
    print(f"  CER      média {mean:.3f}  ·  mediana {median:.3f}")


def report(run: Run, verbose: bool) -> None:
    print(f"\n{BOLD}{run.screens} telas{RESET}")
    print(f"  lixo     {run.spurious} blocos fora de região com texto")
    print(f"  OCR      {statistics.median(run.ocr_ms):.0f} ms por tela (mediana)")
    summarize("todas", run.regions)
    # Balão de fala é o que se lê; texto solto é quase sempre onomatopeia.
    for kind in sorted({r.kind for r in run.regions}):
        summarize(kind, [r for r in run.regions if r.kind == kind])

    if verbose:
        for r in run.regions:
            if r.exact:
                continue
            mark = f"{RED}faltou{RESET}" if not r.found else f"CER {r.cer:.2f}"
            print(f"\n  {DIM}{r.key}{RESET} {mark}")
            print(f"    gabarito: {r.gold}")
            print(f"    app:      {r.read}")


def save(run: Run, name: str, overrides: list[str]) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{name}.json"
    data = {
        "overrides": overrides,
        "spurious": run.spurious,
        "regions": {r.key: dataclasses.asdict(r) for r in run.regions},
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def compare(run: Run, name: str, verbose: bool) -> None:
    before = json.loads((RESULTS / f"{name}.json").read_text(encoding="utf-8"))["regions"]
    now = {r.key: r for r in run.regions}
    shared = sorted(set(before) & set(now))

    print(f"\n{BOLD}contra {name!r} ({len(shared)} regiões em comum){RESET}")
    for label, attr in (("exato", "exact"), ("achado", "found")):
        gained = [k for k in shared if getattr(now[k], attr) and not before[k][attr]]
        lost = [k for k in shared if before[k][attr] and not getattr(now[k], attr)]
        print(f"  {label:7s} {GREEN}+{len(gained)}{RESET}  {RED}-{len(lost)}{RESET}")
        if verbose:
            for k in lost:
                print(f"    {RED}-{RESET} {k}  antes: {before[k]['read']}  agora: {now[k].read}")
            for k in gained:
                print(f"    {GREEN}+{RESET} {k}  antes: {before[k]['read']}  agora: {now[k].read}")
    old_cer = statistics.fmean(before[k]["cer"] for k in shared)
    new_cer = statistics.fmean(now[k].cer for k in shared)
    print(f"  CER     {old_cer:.3f} -> {new_cer:.3f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval_captures", description=__doc__)
    parser.add_argument("folders", nargs="*", help="pastas de eval/captures (padrão: todas)")
    parser.add_argument("--set", dest="overrides", action="append", default=[])
    parser.add_argument("--save", metavar="NOME")
    parser.add_argument("--against", metavar="NOME")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")

    names = args.folders or sorted(p.name for p in CAPTURES.iterdir() if p.is_dir())
    folders = [CAPTURES / n for n in names if (CAPTURES / n / "labels.json").is_file()]
    if not folders:
        raise SystemExit(f"Nenhum labels.json em {CAPTURES}")

    cfg = Config()
    apply_overrides(cfg, args.overrides)
    run = measure(cfg, folders)
    report(run, args.verbose)
    if args.against:
        compare(run, args.against, args.verbose)
    if args.save:
        print(f"\n{DIM}gravado em {save(run, args.save, args.overrides)}{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
