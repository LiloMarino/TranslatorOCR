"""Mede o pipeline em páginas reais de mangá, sem captura de tela.

    uv run scripts/eval_pages.py            # todas as páginas de eval/pages
    uv run scripts/eval_pages.py page02     # só as que contêm isto no nome
    uv run scripts/eval_pages.py -v         # mostra cada bloco lido em cada vista

Cada página é uma imagem (`.webp`/`.png`/`.jpg`) com um `.json` de mesmo nome ao lado,
listando o texto de cada balão: `{"bubbles": ["HELLO THERE...", ...]}`. Para
acrescentar uma página, basta o screenshot e o JSON. A pasta é local e fica fora do
versionamento: são páginas de mangá de terceiros.

Por que não o `dataset/`: são recortes de 160x200 com rótulo ruidoso, e passar nele não
previu o resultado numa página de verdade. Aqui a página roda inteira e também como ela
aparece na tela — reduzida e dentro de um desktop 1920x1080, em duas posições de scroll.

Na página inteira todo balão tem que ser achado; nas vistas de tela, parte dos balões
fica fora da viewport, então ali o que se conta é o que apareceu errado: bloco que não
bate com nenhum balão (lixo) e balão lido duas vezes. Tradução só roda local (NMT, sem
cache): o número não depende de rede nem de execução anterior.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from translatorocr.backends._ort import preload_cuda_dlls
from translatorocr.config import Config
from translatorocr.core.pipeline import Pipeline
from translatorocr.models import Capture, TextBlock

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "eval" / "pages"

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

# Um bloco "é" o balão se a distância de edição normalizada ficar abaixo disto: uma
# letra trocada numa fala longa passa; "OO" no lugar de "ODD" não.
MATCH_CER = 0.05
SCREEN = (1080, 1920)
# Escala da página na tela e fração do scroll (0 = topo).
VIEWS = [(s, top) for s in (1.0, 0.8, 0.65, 0.5) for top in (0.0, 0.55)]


def normalize(text: str) -> str:
    """Só letras, dígitos e espaço: o que se mede é a leitura das palavras, e ".."
    contra "..." ou apóstrofo reto contra curvo não mudam a tradução."""
    kept = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text.upper())
    return " ".join(kept.split())


def cer(a: str, b: str) -> float:
    """Distância de edição de caracteres, normalizada pelo tamanho da referência."""
    a, b = normalize(a), normalize(b)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] / max(1, len(b))


def screen_view(page: np.ndarray, scale: float, top_frac: float) -> np.ndarray:
    """A página como aparece num navegador: reduzida, centralizada, rolada."""
    scaled = cv2.resize(page, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    height, width = SCREEN
    canvas = np.full((height, width, 3), 40, dtype=np.uint8)
    top = int(scaled.shape[0] * top_frac)
    visible = scaled[top : top + height - 100, :width]
    x0 = (width - visible.shape[1]) // 2
    canvas[100 : 100 + visible.shape[0], x0 : x0 + visible.shape[1]] = visible
    return canvas


class StillCapture:
    def __init__(self) -> None:
        self.image = np.zeros((1, 1, 3), dtype=np.uint8)

    def grab(self, region):
        return Capture(image=self.image, origin=(0, 0))


class TimedOCR:
    def __init__(self, inner) -> None:
        self._inner = inner
        self.seconds = 0.0

    def read(self, image):
        started = time.perf_counter()
        try:
            return self._inner.read(image)
        finally:
            self.seconds = time.perf_counter() - started


# Bloco que não bate com nenhum balão: lixo, ou balão cortado pela borda da captura.
MISS, CUT = -1, -2


@dataclass
class Score:
    found: list[int]  # índice do balão achado por cada bloco, ou MISS/CUT
    duplicates: int
    spurious: int


def score(blocks: list[TextBlock], bubbles: list[str]) -> Score:
    found = []
    for block in blocks:
        distances = [cer(block.source, bubble) for bubble in bubbles]
        best = int(np.argmin(distances))
        if distances[best] <= MATCH_CER:
            found.append(best)
        else:
            # Balão cortado pela viewport sai pela metade, e o app já o marca. Não é
            # erro de leitura: é o que o modo scroll vai resolver.
            found.append(CUT if any(ln.partial for ln in block.lines) else MISS)
    hits = [f for f in found if f >= 0]
    return Score(found, duplicates=len(hits) - len(set(hits)), spurious=found.count(MISS))


def load_page(path: Path) -> np.ndarray:
    return cv2.cvtColor(np.array(Image.open(path).convert("RGB")), cv2.COLOR_RGB2BGR)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval_pages", description=__doc__)
    parser.add_argument("filter", nargs="?", default="", help="só páginas com isto no nome")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)

    pages = sorted(
        p
        for p in PAGES.iterdir()
        if p.suffix.lower() in {".webp", ".png", ".jpg", ".jpeg"} and args.filter in p.name
    )
    if not pages:
        print(f"{RED}Nenhuma página em {PAGES}{RESET}")
        return 1

    preload_cuda_dlls()
    from translatorocr.backends.translate_nmt import NMTTranslator
    from translatorocr.registry import build_ocr

    cfg = Config()
    capture = StillCapture()
    ocr = TimedOCR(build_ocr(cfg))
    pipeline = Pipeline(cfg, capture, ocr, NMTTranslator(cfg.translation, cache=None))

    # Aquecimento: a primeira inferência paga o autotune do cuDNN (~4 s) e distorceria
    # o tempo da primeira vista.
    capture.image = load_page(pages[0])
    pipeline.run()

    failed = False
    for path in pages:
        bubbles = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))["bubbles"]
        page = load_page(path)
        print(f"\n{BOLD}{path.name}{RESET}  {DIM}{len(bubbles)} balões{RESET}")

        views = [("página inteira", page)] + [
            (f"tela {scale:.2f} {'topo' if top == 0 else 'meio'}", screen_view(page, scale, top))
            for scale, top in VIEWS
        ]
        for name, image in views:
            capture.image = image
            blocks = pipeline.run()
            result = score(blocks, bubbles)
            is_full = name == "página inteira"
            recall = len({f for f in result.found if f >= 0})
            bad = result.spurious or result.duplicates or (is_full and recall < len(bubbles))
            failed |= bool(bad)
            color = RED if bad else GREEN
            print(
                f"  {color}{name:18s}{RESET} {recall}/{len(bubbles)}  "
                f"ocr {ocr.seconds * 1000:4.0f}ms  "
                f"{'lixo ' + str(result.spurious) + '  ' if result.spurious else ''}"
                f"{'duplicados ' + str(result.duplicates) if result.duplicates else ''}"
            )

            show_all = args.verbose or is_full
            for block, match in zip(blocks, result.found, strict=True):
                if not (show_all or match == MISS):
                    continue
                flag = f"{YELLOW}?{RESET}" if block.needs_review else " "
                mark = {MISS: f"{RED}✘{RESET}", CUT: f"{YELLOW}✂{RESET}"}.get(match, " ")
                print(f"    {mark}{flag} {block.source}")
                if is_full:
                    print(f"       {DIM}→ {block.translated}{RESET}")
            if is_full:
                seen = set(result.found)
                for i, bubble in enumerate(bubbles):
                    if i not in seen:
                        print(f"    {RED}faltou{RESET}  {bubble}")

    print()
    if failed:
        print(f"{RED}{BOLD}Há balão faltando, lixo ou duplicado (em vermelho acima).{RESET}")
        return 1
    print(f"{GREEN}{BOLD}Todas as páginas limpas.{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
