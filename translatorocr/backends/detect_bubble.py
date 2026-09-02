"""Detector de balão — RT-DETR-v2 fine-tunado em mangá/HQ, em ONNXRuntime.

Resolve a causa do ruído de UI: o DBNet do RapidOCR acha *texto*, e numa captura de
tela cheia isso é toda a interface. Este modelo acha *balão*, com as três classes que
o agrupamento precisa (`bubble`, `text_bubble`, `text_free`).

Escolhido no lugar do comic-text-detector do ecossistema manga-image-translator: aquele
é GPL-3.0, tem entrada de shape fixo, exige reimplementar NMS do YOLOv5 e unclip do
DBNet em numpy, e suas 3 classes são idioma (eng/ja/unknown), não balão. Este é
Apache-2.0, NMS-free, e traz o pós-processamento embutido no grafo.

Sobre a ordem dos eixos de `orig_target_sizes`: o grafo multiplica as caixas xyxy por
`orig_target_sizes.repeat(1, 2)`, então o primeiro valor escala x e o segundo y — o
inverso da convenção `(height, width)` do `transformers`, apesar de o modelo vir de lá.
Em vez de apostar num dos dois, passamos `[[1, 1]]` e escalamos aqui: as caixas voltam
normalizadas em 0..1 e a ambiguidade deixa de existir. Verificado com o modelo real.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from ..config import DetectorConfig
from ..models import BBox, Detection
from ._ort import check_providers, preload_cuda_dlls, session_providers

log = logging.getLogger(__name__)

# Do `id2label` do modelo. A ordem é a dos índices e não pode ser reordenada.
LABELS = ("bubble", "text_bubble", "text_free")

# As classes que carregam texto para reconhecer. `bubble` é o desenho do balão, sem
# valor por si só — o texto dentro dele vem como `text_bubble`.
TEXT_KINDS = frozenset({"text_bubble", "text_free"})


class BubbleDetector:
    def __init__(self, cfg: DetectorConfig) -> None:
        path = Path(cfg.model_path)
        if not path.is_file():
            raise FileNotFoundError(
                f"Modelo do detector não encontrado em {path.resolve()}. "
                "Rode `uv run scripts/fetch_models.py detector`."
            )

        preload_cuda_dlls()
        import onnxruntime as ort

        self._cfg = cfg
        self._session: Any = ort.InferenceSession(
            str(path), providers=session_providers(cfg.use_gpu)
        )
        check_providers(
            "detector",
            list(self._session.get_providers()),
            use_gpu=cfg.use_gpu,
            strict_gpu=cfg.strict_gpu,
        )

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        """BGR uint8 → NCHW float32 normalizado como o modelo espera.

        Conforme o `preprocessor_config.json`: resize bilinear para 640x640 **sem
        preservar o aspecto** (`do_pad: false`), `rescale` por 1/255, e **sem** mean/std
        (`do_normalize: false`). Aplicar a normalização ImageNet aqui, que é o reflexo
        automático, degrada a detecção em silêncio.
        """
        size = self._cfg.input_size
        resized = cv2.resize(image, (size, size), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        chw = rgb.astype(np.float32).transpose(2, 0, 1) / 255.0
        return chw[np.newaxis, ...]

    def detect(self, image: np.ndarray) -> list[Detection]:
        height, width = image.shape[:2]
        outputs = self._session.run(
            None,
            {
                "images": self._preprocess(image),
                # Ver a nota do módulo: [[1, 1]] devolve as caixas normalizadas.
                "orig_target_sizes": np.array([[1, 1]], dtype=np.int64),
            },
        )
        labels, boxes, scores = (np.asarray(o) for o in outputs)

        detections: list[Detection] = []
        for label, box, score in zip(labels[0], boxes[0], scores[0], strict=True):
            if score < self._cfg.score_threshold:
                continue
            kind = LABELS[label] if 0 <= label < len(LABELS) else "unknown"
            x1, y1, x2, y2 = box
            bbox: BBox = (
                max(0, min(width, int(x1 * width))),
                max(0, min(height, int(y1 * height))),
                max(0, min(width, int(x2 * width))),
                max(0, min(height, int(y2 * height))),
            )
            if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                continue
            detections.append(Detection(bbox=bbox, kind=kind, score=float(score)))

        log.debug(
            "detector: %d regiões acima de %.2f (%d brutas)",
            len(detections),
            self._cfg.score_threshold,
            len(scores[0]),
        )
        return detections
