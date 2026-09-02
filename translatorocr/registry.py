"""Constrói os backends a partir da configuração.

Único lugar que conhece as implementações concretas — o pipeline só vê os protocolos de
`backends/base.py`. Adicionar um backend é adicionar uma entrada aqui.
"""

from __future__ import annotations

import logging

from .backends.base import CaptureBackend, LLMBackend, OCRBackend, TranslatorBackend
from .backends.cache import TranslationCache
from .config import Config
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
    name = config.ocr.backend.lower()
    if name != "rapidocr":
        raise ValueError(f"Backend de OCR desconhecido: {config.ocr.backend!r}")

    from .backends.ocr_rapid import RapidOCRBackend

    recognizer = RapidOCRBackend(config.ocr)
    if not config.detector.enabled:
        return recognizer

    # Com o detector, o reconhecedor roda só nos recortes que ele marcou como texto.
    # Isso é o que remove a UI da tela cheia antes de ela virar bloco.
    from .backends.detect_bubble import BubbleDetector
    from .backends.ocr_composite import CompositeOCR

    return CompositeOCR(BubbleDetector(config.detector), recognizer, config.detector)


def _build_tier(name: str, config: Config, cache: TranslationCache) -> TranslatorBackend:
    if name == "cloud":
        from .backends.translate_cloud import CloudTranslator

        return CloudTranslator(config.translation, cache)
    if name == "nmt":
        from .backends.translate_nmt import NMTTranslator

        return NMTTranslator(config.translation, cache)
    raise ValueError(f"Tier de tradução desconhecido: {name!r}")


def build_translator(config: Config) -> TranslatorBackend:
    cache = TranslationCache(config.translation.cache_path)
    names = config.translation.tiers or [config.translation.backend]

    tiers: list[TranslatorBackend] = []
    for name in names:
        try:
            tiers.append(_build_tier(name.lower(), config, cache))
        except FileNotFoundError as exc:
            # Modelo não baixado. Pular é aceitável **se sobrar outro tier** — mas em
            # WARNING e dizendo o que fazer, porque tradução silenciosamente pior é
            # exatamente o modo de falha que este projeto já pagou duas vezes.
            log.warning("Tier de tradução %r indisponível: %s", name, exc)

    if not tiers:
        raise RuntimeError(
            f"Nenhum tier de tradução pôde ser construído (pedidos: {names}). "
            "Rode `uv run scripts/fetch_models.py` ou ajuste [translation].tiers."
        )
    if len(tiers) == 1:
        return tiers[0]

    from .backends.chain import ChainTranslator

    return ChainTranslator(tiers)


def build_llm(config: Config) -> LLMBackend | None:
    """`None` quando desligado ou o modelo não foi baixado — mesmo padrão de
    warning-e-segue-sem que `build_translator` já usa pros tiers de tradução."""
    if not config.llm.enabled:
        return None

    from .backends.translate_llm import LLMTranslator

    try:
        return LLMTranslator(config.llm)
    except FileNotFoundError as exc:
        log.warning("Tier de LLM indisponível: %s", exc)
        return None
    except ImportError as exc:
        log.warning(
            "Tier de LLM indisponível: %s. Rode `uv sync --group llm` "
            '(precisa de CMAKE_ARGS="-DGGML_CUDA=on" pra compilar com suporte a GPU).',
            exc,
        )
        return None


def build_pipeline(config: Config) -> Pipeline:
    return Pipeline(
        config=config,
        capture=build_capture(config),
        ocr=build_ocr(config),
        translator=build_translator(config),
        llm=build_llm(config),
    )
