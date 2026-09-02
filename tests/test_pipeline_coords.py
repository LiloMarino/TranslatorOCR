"""Integração do pipeline com OCR real, captura e tradução dubladas.

Este teste protege a conversão de coordenadas: um bbox que sai do OCR no espaço da
imagem tem que chegar ao overlay em pixel físico do desktop, somando a origem da
região e desfazendo o upscale. Errar isso desenha a caixa no lugar errado, um bug
invisível sem uma verificação como esta.

Requer GPU/modelos; pulado se o RapidOCR não inicializar.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from translatorocr.config import Config
from translatorocr.core.pipeline import Pipeline
from translatorocr.models import Capture, Region

ORIGIN = (1920, 300)  # canto de um segundo monitor à direita do primário
TEXT = "Hello, are you alright?"


class FakeCapture:
    """Devolve sempre a mesma imagem, com uma origem não-trivial."""

    def __init__(self, image: np.ndarray) -> None:
        self._image = image

    def grab(self, region: Region | None = None) -> Capture | None:
        return Capture(image=self._image, origin=ORIGIN, scale=1.0)

    def monitor_region(self) -> Region:
        h, w = self._image.shape[:2]
        return Region(ORIGIN[0], ORIGIN[1], w, h)

    def close(self) -> None: ...


class EchoTranslator:
    """Marca o texto para provar que a tradução foi aplicada por bloco."""

    def translate(self, texts: list[str], source: str, target: str) -> list[str | None]:
        return [f"[{t}]" for t in texts]


@pytest.fixture(scope="module")
def ocr():
    from translatorocr.backends.ocr_rapid import RapidOCRBackend

    cfg = Config().ocr
    try:
        return RapidOCRBackend(cfg)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"RapidOCR indisponível: {exc}")


@pytest.fixture(scope="module")
def page() -> np.ndarray:
    img = np.full((400, 1000, 3), 245, np.uint8)
    cv2.putText(img, TEXT, (120, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (25, 25, 25), 2, cv2.LINE_AA)
    return img


def test_bbox_sai_em_coordenada_de_desktop(ocr, page):
    config = Config()
    pipeline = Pipeline(config, FakeCapture(page), ocr, EchoTranslator())
    blocks = pipeline.run()

    assert blocks, "o OCR não encontrou nada na imagem sintética"
    block = blocks[0]
    x1, y1, x2, y2 = block.bbox

    # O texto foi desenhado por volta de (120, 200) no espaço da imagem, então em
    # coordenada de desktop tem que estar deslocado pela origem da região.
    assert ORIGIN[0] + 60 < x1 < ORIGIN[0] + 200, f"x1={x1} fora do esperado"
    assert ORIGIN[1] + 120 < y1 < ORIGIN[1] + 220, f"y1={y1} fora do esperado"
    assert x2 > x1 and y2 > y1


def test_upscale_e_desfeito_na_conversao(ocr, page):
    """Com upscale 2x o bbox precisa voltar para a mesma coordenada de desktop."""
    base = Config()
    scaled = Config()
    scaled.capture.upscale = 2.0
    scaled.ocr.max_side_len = base.ocr.max_side_len

    a = Pipeline(base, FakeCapture(page), ocr, EchoTranslator()).run()
    b = Pipeline(scaled, FakeCapture(page), ocr, EchoTranslator()).run()
    assert a and b

    # Tolerância generosa: o detector não devolve exatamente o mesmo polígono nas
    # duas resoluções. O que importa é não haver um fator de 2 sobrando.
    assert abs(a[0].bbox[0] - b[0].bbox[0]) < 40
    assert abs(a[0].bbox[1] - b[0].bbox[1]) < 40


def test_cada_bloco_e_traduzido_isoladamente(ocr, page):
    """Nada de `" ".join` — a marca do EchoTranslator tem que envolver cada bloco."""
    pipeline = Pipeline(Config(), FakeCapture(page), ocr, EchoTranslator())
    blocks = pipeline.run()
    assert blocks
    for block in blocks:
        assert block.translated == f"[{block.source}]"
