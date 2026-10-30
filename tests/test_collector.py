"""Coletor de capturas: o par imagem + JSON, sem GPU e sem Qt."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import pytest

from translatorocr.config import CollectorConfig, Config
from translatorocr.core.collector import CaptureCollector
from translatorocr.core.ledger import BlockLedger
from translatorocr.core.pipeline import Pipeline
from translatorocr.models import Capture, Region, TextBlock, TextLine

NOW = datetime(2026, 10, 30, 13, 45, 7, 123456)


def noisy_image(seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 255, (200, 300, 3), dtype=np.uint8)


def make_collector(tmp_path) -> CaptureCollector:
    return CaptureCollector(CollectorConfig(root=tmp_path), clock=lambda: NOW)


def saved(collector: CaptureCollector, *args) -> Path:
    path = collector.save(*args)
    assert path is not None
    return path


def block(source: str = "Hello", bbox=(110, 220, 150, 260), partial: bool = False) -> TextBlock:
    line = TextLine(bbox=bbox, text=source, confidence=0.9, partial=partial)
    return TextBlock(bbox=bbox, source=source, confidence=0.9, lines=[line], translated="Olá")


def test_grava_o_par_na_pasta_do_dia(tmp_path):
    shot = Capture(image=noisy_image(), origin=(100, 200))
    path = saved(make_collector(tmp_path), shot, [block()], {})

    assert path == tmp_path / "2026-10-30" / "134507-123456.webp"
    decoded = cv2.imread(str(path))
    assert decoded is not None
    assert decoded.shape == shot.image.shape
    assert path.with_suffix(".json").exists()


def test_bbox_sai_nas_coordenadas_da_imagem(tmp_path):
    shot = Capture(image=noisy_image(), origin=(100, 200), scale=2.0)
    path = saved(make_collector(tmp_path), shot, [block()], {})

    data = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    assert data["blocks"][0]["bbox"] == [20, 40, 100, 120]


def test_balao_novo_leva_o_contexto(tmp_path):
    shot = Capture(image=noisy_image(), origin=(0, 0))
    new, known = block("Novo"), block("Antigo")
    path = saved(make_collector(tmp_path), shot, [new, known], {id(new): ["fala 1", "fala 2"]})

    records = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))["blocks"]
    assert (records[0]["new"], records[0]["context"]) == (True, ["fala 1", "fala 2"])
    assert (records[1]["new"], records[1]["context"]) == (False, [])


def test_balao_cortado_fica_marcado(tmp_path):
    shot = Capture(image=noisy_image(), origin=(0, 0))
    path = saved(make_collector(tmp_path), shot, [block(partial=True)], {})
    data = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    assert data["blocks"][0]["partial"] is True


def test_tela_repetida_nao_e_gravada(tmp_path):
    collector = make_collector(tmp_path)
    shot = Capture(image=noisy_image(), origin=(0, 0))
    assert collector.save(shot, [], {}) is not None
    assert collector.save(shot, [], {}) is None
    assert collector.saved == 1


def test_tela_diferente_e_gravada(tmp_path):
    moments = iter([NOW, NOW.replace(second=8)])
    collector = CaptureCollector(CollectorConfig(root=tmp_path), clock=lambda: next(moments))
    assert collector.save(Capture(noisy_image(1), (0, 0)), [], {}) is not None
    assert collector.save(Capture(noisy_image(2), (0, 0)), [], {}) is not None
    assert collector.saved == 2


def test_falha_de_disco_nao_interrompe_a_leitura(tmp_path):
    blocked = tmp_path / "arquivo"
    blocked.write_text("")
    collector = make_collector(blocked)
    assert collector.save(Capture(noisy_image(), (0, 0)), [], {}) is None
    assert collector.saved == 0


# -- integração com o pipeline -----------------------------------------------


class FakeCapture:
    def __init__(self, image: np.ndarray) -> None:
        self.image = image

    def grab(self, region: Region | None = None) -> Capture | None:
        return Capture(image=self.image, origin=(0, 0))

    def monitor_region(self) -> Region:
        return Region(0, 0, 300, 200)

    def close(self) -> None: ...


class FakeOCR:
    def __init__(self, lines: list[TextLine]) -> None:
        self.lines = lines

    def read(self, image: np.ndarray) -> list[TextLine]:
        return self.lines


class FakeTranslator:
    def translate(self, texts: list[str], source: str, target: str) -> list[str | None]:
        return [f"pt({text})" for text in texts]


@pytest.fixture
def pipeline_parts(tmp_path):
    config = Config()
    config.gate.enabled = False
    lines = [
        TextLine(bbox=(20, 20, 120, 40), text="First line here", confidence=0.95),
        TextLine(bbox=(20, 120, 120, 140), text="Second line here", confidence=0.95),
    ]
    collector = make_collector(tmp_path)
    ledger = BlockLedger(config.ledger, config.scroll)
    return config, lines, collector, ledger


def test_pipeline_grava_o_contexto_em_ordem_de_leitura(pipeline_parts):
    config, lines, collector, ledger = pipeline_parts
    pipeline = Pipeline(
        config,
        FakeCapture(noisy_image()),
        FakeOCR(lines),  # type: ignore[arg-type]
        FakeTranslator(),
        ledger=ledger,
        collector=collector,
    )
    pipeline.run()

    day = next(collector._cfg.root.iterdir())
    records = json.loads(next(day.glob("*.json")).read_text(encoding="utf-8"))["blocks"]
    assert [r["new"] for r in records] == [True, True]
    assert records[0]["context"] == []
    assert records[1]["context"] == ["First line here"]
    assert records[1]["translated"] == "pt(Second line here)"


def test_pipeline_sem_coletor_nao_grava_nada(pipeline_parts, tmp_path):
    config, lines, _, ledger = pipeline_parts
    pipeline = Pipeline(
        config,
        FakeCapture(noisy_image()),
        FakeOCR(lines),  # type: ignore[arg-type]
        FakeTranslator(),
        ledger=ledger,
    )
    pipeline.run()
    assert list(tmp_path.iterdir()) == []
