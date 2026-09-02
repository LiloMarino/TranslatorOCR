"""OCR via RapidOCR — modelos PP-OCR rodando em ONNXRuntime.

Escolhido no lugar do `paddlepaddle-gpu` nativo porque são os mesmos modelos e a
instalação no Windows com Python 3.13 é limpa. Substitui o EasyOCR, que além de
menos preciso vinha rodando em CPU sem avisar.

As duas coisas que fazem a diferença entre funcionar e falhar em silêncio — o preload
dos DLLs de CUDA e a conferência de que o provider pedido realmente carregou — moram
em `_ort.py`, porque valem igualmente para o detector de balão.
"""

from __future__ import annotations

import logging

import numpy as np

from ..config import OCRConfig
from ..models import BBox, TextLine
from ._ort import check_providers, preload_cuda_dlls

log = logging.getLogger(__name__)

# O detector do PP-OCRv5 só existe na variante "ch", que é agnóstica de idioma —
# DBNet acha região de texto independente do script. Quem é específico de idioma é
# o reconhecedor.
#
# Sobre o PP-OCRv6: os pesos estão no catálogo do rapidocr 3.9.2, mas não são
# alcançáveis — `LangRec` não tem membro `multi` e a resolução de modelo rejeita a
# string crua. Verificado em 2026-09. Reavaliar numa versão futura do rapidocr.
#
# Efeito colateral bem-vindo da escolha de `lang="en"`: o charset do reconhecedor é
# só ASCII, o que torna ideograma irrepresentável na saída.
_SUPPORTED_VERSIONS = {"PP-OCRv4", "PP-OCRv5"}


def _build_params(cfg: OCRConfig) -> dict:
    from rapidocr import EngineType, LangDet, LangRec, ModelType, OCRVersion

    if cfg.ocr_version not in _SUPPORTED_VERSIONS:
        raise ValueError(
            f"ocr_version={cfg.ocr_version!r} não é utilizável com rapidocr 3.9.2; "
            f"use um de {sorted(_SUPPORTED_VERSIONS)}"
        )
    version = OCRVersion(cfg.ocr_version)
    det_lang, rec_lang = LangDet.CH, LangRec(cfg.lang)

    return {
        "EngineConfig.onnxruntime.use_cuda": cfg.use_gpu,
        "Global.max_side_len": cfg.max_side_len,
        "Global.text_score": cfg.text_score,
        "Global.log_level": "error",
        "Det.engine_type": EngineType.ONNXRUNTIME,
        "Det.lang_type": det_lang,
        "Det.model_type": ModelType(cfg.model_type),
        "Det.ocr_version": version,
        "Rec.engine_type": EngineType.ONNXRUNTIME,
        "Rec.lang_type": rec_lang,
        "Rec.model_type": ModelType(cfg.model_type),
        "Rec.ocr_version": version,
    }


def _providers_of(stage) -> list[str]:
    session = getattr(getattr(stage, "session", None), "session", None)
    if session is not None and hasattr(session, "get_providers"):
        return list(session.get_providers())
    return []


def _to_bbox(polygon) -> BBox:
    """Achata o polígono de 4 pontos do detector num retângulo alinhado aos eixos."""
    pts = np.asarray(polygon, dtype=np.float32).reshape(-1, 2)
    x1, y1 = pts.min(axis=0)
    x2, y2 = pts.max(axis=0)
    return (int(x1), int(y1), int(x2), int(y2))


class RapidOCRBackend:
    def __init__(self, cfg: OCRConfig) -> None:
        preload_cuda_dlls()
        from rapidocr import RapidOCR

        self._cfg = cfg
        self._engine = RapidOCR(params=_build_params(cfg))
        # Os dois estágios são sessões separadas e podem cair em CPU de forma
        # independente, então cada um é conferido por conta própria.
        for stage, holder in (
            ("OCR det", self._engine.text_det),
            ("OCR rec", self._engine.text_rec),
        ):
            check_providers(
                stage,
                _providers_of(holder),
                use_gpu=cfg.use_gpu,
                strict_gpu=cfg.strict_gpu,
            )

    def read(self, image: np.ndarray) -> list[TextLine]:
        result = self._engine(image)
        boxes = getattr(result, "boxes", None)
        texts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        if boxes is None or texts is None:
            return []

        # Fronteira com lib de terceiro: se boxes e txts divergirem em tamanho, um
        # zip silencioso emparelharia bbox com o texto errado. Aqui é preferível
        # truncar e avisar a estourar a captura inteira.
        if len(boxes) != len(texts):
            log.warning(
                "RapidOCR devolveu %d boxes para %d textos; truncando no menor.",
                len(boxes),
                len(texts),
            )

        lines: list[TextLine] = []
        for i, (polygon, text) in enumerate(zip(boxes, texts, strict=False)):
            stripped = text.strip()
            if not stripped:
                continue
            score = float(scores[i]) if scores is not None and i < len(scores) else 0.0
            lines.append(TextLine(bbox=_to_bbox(polygon), text=stripped, confidence=score))
        return lines
