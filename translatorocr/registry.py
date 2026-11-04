"""Constrói os backends a partir da configuração.

Único lugar que conhece as implementações concretas — o pipeline só vê os protocolos de
`backends/base.py`. Adicionar um backend é adicionar uma entrada aqui.
"""

from __future__ import annotations

import logging

from .backends.base import CaptureBackend, OCRBackend, RefinerBackend, TranslatorBackend
from .backends.cache import TranslationCache
from .config import Config
from .core.collector import CaptureCollector
from .core.ledger import BlockLedger
from .core.pipeline import Pipeline

log = logging.getLogger(__name__)


def build_capture(config: Config) -> CaptureBackend:
    name = config.capture.backend.lower()
    if name == "mss":
        from .backends.capture_mss import MSSCapture

        return MSSCapture(monitor=config.capture.monitor)
    if name == "dxcam":
        from .backends.capture_dxcam import DXCamCapture

        return DXCamCapture(monitor=config.capture.monitor)
    raise ValueError(f"Backend de captura desconhecido: {config.capture.backend!r}")


def build_ocr(config: Config) -> OCRBackend:
    from .backends.ocr_rapid import RapidOCRBackend

    recognizer = RapidOCRBackend(config.ocr)
    if not config.detector.enabled:
        return recognizer

    # Com o detector, o reconhecedor roda só nos recortes que ele marcou como texto.
    # Isso é o que remove a UI da tela cheia antes de ela virar bloco.
    from .backends.detect_bubble import BubbleDetector
    from .backends.ocr_composite import CompositeOCR

    try:
        detector = BubbleDetector(config.detector)
    except FileNotFoundError as exc:
        # Sem o detector o app ainda funciona, só volta a agrupar por heurística e a
        # deixar passar texto fora de balão. WARNING porque a diferença é visível.
        log.warning("Detector de balão indisponível, seguindo sem ele: %s", exc)
        return recognizer
    return CompositeOCR(detector, recognizer, config.detector)


def build_translator(config: Config) -> TranslatorBackend:
    from .backends.translate_nmt import NMTTranslator

    cache = TranslationCache(config.translation.cache_path)
    try:
        return NMTTranslator(config.translation, cache)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Tradutor offline indisponível: {exc}. "
            "Verifique a conexão e reinicie, ou rode `uv run scripts/fetch_models.py`."
        ) from exc


def build_refiner(config: Config) -> RefinerBackend | None:
    """`None` quando desligado, sem o modelo ou sem o llama-cpp: o app segue só com o
    opus-mt, com um warning dizendo o que fazer."""
    if not config.refine.enabled:
        return None

    from .backends.translate_gemma import GemmaTranslator

    try:
        return GemmaTranslator(config.refine, TranslationCache(config.translation.cache_path))
    except FileNotFoundError as exc:
        log.warning("Segunda passada da tradução indisponível: %s", exc)
        return None
    except ImportError as exc:
        log.warning(
            "Segunda passada da tradução indisponível: %s. Rode `uv sync --group llm` "
            '(precisa de CMAKE_ARGS="-DGGML_CUDA=on" pra compilar com suporte a GPU).',
            exc,
        )
        return None


def build_pipeline(
    config: Config,
    capture: CaptureBackend | None = None,
    ledger: BlockLedger | None = None,
) -> Pipeline:
    """`capture` pronto substitui o backend de tela — é assim que o `--image` roda o
    pipeline inteiro sobre um arquivo, sem a tela participar. `ledger` é o registro de
    balões, que o `App` também alimenta com a rolagem."""
    collector = CaptureCollector(config.collector) if config.collect else None
    return Pipeline(
        config=config,
        capture=capture or build_capture(config),
        ocr=build_ocr(config),
        translator=build_translator(config),
        refiner=build_refiner(config),
        ledger=ledger,
        collector=collector,
    )
