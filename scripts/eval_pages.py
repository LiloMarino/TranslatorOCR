"""Mede o pipeline em páginas reais de mangá, sem captura de tela.

    uv run scripts/eval_pages.py            # todas as páginas de eval/pages
    uv run scripts/eval_pages.py page02     # só as que contêm isto no nome
    uv run scripts/eval_pages.py -v         # mostra cada bloco lido em cada vista
    uv run scripts/eval_pages.py --fit-boxes  # (re)grava a posição dos balões no JSON

Cada página é uma imagem (`.webp`/`.png`/`.jpg`) com um `.json` de mesmo nome ao lado,
listando o texto de cada balão: `{"bubbles": ["HELLO THERE...", ...]}`. Para
acrescentar uma página, basta o screenshot e o JSON, e depois um `--fit-boxes` para
gravar onde cada balão está. A pasta é local e fica fora do versionamento: são páginas
de mangá de terceiros.

Por que não o `dataset/`: são recortes de 160x200 com rótulo ruidoso, e passar nele não
previu o resultado numa página de verdade. Aqui a página roda inteira e também como ela
aparece na tela — reduzida ou ampliada, dentro de um desktop 1920x1080, em duas posições
de scroll.

**Recall é cobrado em toda vista**, e não só na página inteira. Para isso o JSON guarda a
posição de cada balão (`boxes`), o que permite saber quais deles cabem inteiros na vista
— sem isso não dava para distinguir "o OCR perdeu o balão" de "o balão está fora da
viewport", e uma regressão de leitura em escala de tela passava despercebida. Balão
cortado pela borda não conta: é o que o modo de leitura resolve rolando.

Tradução só roda local (NMT, sem cache): o número não depende de rede nem de execução
anterior.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from translatorocr.backends._ort import preload_cuda_dlls
from translatorocr.backends.capture_still import StillCapture
from translatorocr.config import Config
from translatorocr.core.pipeline import Pipeline
from translatorocr.models import BBox, TextBlock
from translatorocr.ui import console

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
# Um bloco que erra mais que MATCH_CER mas fica abaixo disto do balão mais próximo é a
# leitura de um pedaço dele, não lixo — o caso do balão cortado pela borda da viewport.
CUT_CER = 0.6
SCREEN = (1080, 1920)
# Faixa de cromo do navegador acima do conteúdo.
TOP_BAR = 100
# Escala da página na tela e fração do scroll (0 = topo). A de 1.3 existe porque
# navegador ampliando é caso real: a página tem 870 px de largura e uma coluna larga
# a estica.
VIEWS = [(s, top) for s in (1.3, 1.0, 0.8, 0.65, 0.5) for top in (0.0, 0.55)]


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


WHOLE, CLIPPED, OFFSCREEN = "inteiro", "cortado", "fora"


@dataclass(frozen=True)
class View:
    """Uma página como ela aparece na tela, e como voltar da página para a tela."""

    name: str
    image: np.ndarray
    scale: float
    dx: int
    dy: int
    # Retângulo do conteúdo dentro da tela: fora dele é moldura, não página.
    content: BBox

    def project(self, box: BBox) -> BBox:
        x1, y1, x2, y2 = box
        return (
            int(x1 * self.scale) + self.dx,
            int(y1 * self.scale) + self.dy,
            int(x2 * self.scale) + self.dx,
            int(y2 * self.scale) + self.dy,
        )

    def visibility(self, box: BBox) -> str:
        x1, y1, x2, y2 = self.project(box)
        cx1, cy1, cx2, cy2 = self.content
        if x1 >= cx1 and y1 >= cy1 and x2 <= cx2 and y2 <= cy2:
            return WHOLE
        if x2 <= cx1 or x1 >= cx2 or y2 <= cy1 or y1 >= cy2:
            return OFFSCREEN
        return CLIPPED


def full_view(page: np.ndarray) -> View:
    height, width = page.shape[:2]
    return View("página inteira", page, 1.0, 0, 0, (0, 0, width, height))


def screen_view(page: np.ndarray, scale: float, top_frac: float) -> View:
    """A página como aparece num navegador: redimensionada, centralizada, rolada."""
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
    scaled = cv2.resize(page, None, fx=scale, fy=scale, interpolation=interpolation)
    height, width = SCREEN
    canvas = np.full((height, width, 3), 40, dtype=np.uint8)
    top = int(scaled.shape[0] * top_frac)
    visible = scaled[top : top + height - TOP_BAR, :width]
    x0 = (width - visible.shape[1]) // 2
    canvas[TOP_BAR : TOP_BAR + visible.shape[0], x0 : x0 + visible.shape[1]] = visible
    name = f"tela {scale:.2f} {'topo' if top_frac == 0 else 'meio'}"
    return View(
        name=name,
        image=canvas,
        scale=scale,
        dx=x0,
        dy=TOP_BAR - top,
        content=(x0, TOP_BAR, x0 + visible.shape[1], TOP_BAR + visible.shape[0]),
    )


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
    # Balões que cabiam inteiros na vista e não foram lidos.
    missing: list[int] = field(default_factory=list)
    expected: int = 0

    @property
    def bad(self) -> bool:
        return bool(self.spurious or self.duplicates or self.missing)


def score(blocks: list[TextBlock], bubbles: list[str], view: View, boxes: list[BBox]) -> Score:
    clipped = {i for i, box in enumerate(boxes) if view.visibility(box) == CLIPPED}

    found = []
    for block in blocks:
        distances = [cer(block.source, bubble) for bubble in bubbles]
        best = int(np.argmin(distances))
        if distances[best] <= MATCH_CER:
            found.append(best)
            continue
        # Balão cortado pela viewport sai pela metade. Não é erro de leitura: é o que o
        # modo de leitura resolve rolando. Vale tanto a marca do app quanto a posição
        # gravada — na vista simulada o conteúdo começa abaixo da barra do navegador,
        # então o balão é cortado pelo conteúdo sem encostar na borda da imagem, e só a
        # posição sabe disso.
        partial = any(ln.partial for ln in block.lines)
        cut = best in clipped and distances[best] <= CUT_CER
        found.append(CUT if (partial or cut) else MISS)
    hits = [f for f in found if f >= 0]

    # Sem as posições gravadas não dá para saber o que estava visível; aí só a página
    # inteira cobra recall, que é o comportamento antigo.
    if boxes:
        expected = [i for i, box in enumerate(boxes) if view.visibility(box) == WHOLE]
    else:
        expected = list(range(len(bubbles))) if view.scale == 1.0 and view.dy == 0 else []

    return Score(
        found=found,
        duplicates=len(hits) - len(set(hits)),
        spurious=found.count(MISS),
        missing=[i for i in expected if i not in set(hits)],
        expected=len(expected),
    )


def load_page(path: Path) -> np.ndarray:
    return cv2.cvtColor(np.array(Image.open(path).convert("RGB")), cv2.COLOR_RGB2BGR)


def page_paths(filter_: str) -> list[Path]:
    return sorted(
        p
        for p in PAGES.iterdir()
        if p.suffix.lower() in {".webp", ".png", ".jpg", ".jpeg"} and filter_ in p.name
    )


def read_truth(path: Path) -> tuple[list[str], list[BBox]]:
    data = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    boxes = [tuple(b) for b in data.get("boxes", [])]
    if len(boxes) != len(data["bubbles"]):
        boxes = []
    return data["bubbles"], boxes  # type: ignore[return-value]


def fit_boxes(pipeline: Pipeline, capture: StillCapture, paths: list[Path]) -> int:
    """Grava no JSON onde cada balão está, rodando o pipeline na página inteira.

    É o que permite cobrar recall nas vistas de tela. Roda à parte porque só precisa
    acontecer quando uma página entra na pasta.
    """
    for path in paths:
        bubbles, _ = read_truth(path)
        capture.image = load_page(path)
        blocks = pipeline.run()
        boxes: list[list[int]] = []
        for bubble in bubbles:
            best = min(blocks, key=lambda b: cer(b.source, bubble), default=None)
            if best is None or cer(best.source, bubble) > 0.25:
                console.error(f"{path.name}: não achei na página o balão {bubble[:30]!r}")
                return 1
            boxes.append([int(v) for v in best.bbox])
        target = path.with_suffix(".json")
        data = json.loads(target.read_text(encoding="utf-8"))
        data["boxes"] = boxes
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  {GREEN}{path.name}{RESET}: {len(boxes)} posições gravadas")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval_pages", description=__doc__)
    parser.add_argument("filter", nargs="?", default="", help="só páginas com isto no nome")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "--fit-boxes",
        action="store_true",
        help="grava no JSON a posição de cada balão, medida na página inteira",
    )
    args = parser.parse_args(argv)
    # O mesmo tratamento do app: sem isto a saída redirecionada estoura em
    # UnicodeEncodeError no cp1252 ao imprimir a seta e os acentos.
    console.setup()
    logging.basicConfig(level=logging.WARNING)

    pages = page_paths(args.filter)
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

    if args.fit_boxes:
        return fit_boxes(pipeline, capture, pages)

    failed = False
    for path in pages:
        bubbles, boxes = read_truth(path)
        page = load_page(path)
        note = "" if boxes else f"  {YELLOW}(sem posições: rode --fit-boxes){RESET}"
        print(f"\n{BOLD}{path.name}{RESET}  {DIM}{len(bubbles)} balões{RESET}{note}")

        for view in [full_view(page), *(screen_view(page, s, t) for s, t in VIEWS)]:
            capture.image = view.image
            blocks = pipeline.run()
            result = score(blocks, bubbles, view, boxes)
            failed |= result.bad
            color = RED if result.bad else GREEN
            recall = len({f for f in result.found if f >= 0})
            print(
                f"  {color}{view.name:18s}{RESET} {recall}/{result.expected} visíveis  "
                f"ocr {ocr.seconds * 1000:4.0f}ms  "
                f"{'lixo ' + str(result.spurious) + '  ' if result.spurious else ''}"
                f"{'duplicados ' + str(result.duplicates) if result.duplicates else ''}"
            )

            is_full = view.name == "página inteira"
            show_all = args.verbose or is_full
            for block, match in zip(blocks, result.found, strict=True):
                if not (show_all or match == MISS):
                    continue
                flag = f"{YELLOW}?{RESET}" if block.needs_review else " "
                mark = {MISS: f"{RED}X{RESET}", CUT: f"{YELLOW}~{RESET}"}.get(match, " ")
                print(f"    {mark}{flag} {block.source}")
                if is_full:
                    print(f"       {DIM}-> {block.translated}{RESET}")
            for index in result.missing:
                print(f"    {RED}faltou{RESET}  {bubbles[index]}")

    print()
    if failed:
        print(f"{RED}{BOLD}Há balão faltando, lixo ou duplicado (em vermelho acima).{RESET}")
        return 1
    print(f"{GREEN}{BOLD}Todas as páginas limpas.{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
