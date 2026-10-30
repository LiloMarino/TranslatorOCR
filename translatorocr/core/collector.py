"""Coletor de capturas: guarda o que o app realmente recebeu e o que fez com isso.

Cada rodada do pipeline vira um par `<hora>.webp` + `<hora>.json` em
`<root>/<data>/`. A imagem é a mesma entregue ao OCR, com o overlay fora dela; o JSON tem
os balões lidos, em coordenadas dessa imagem, e, para os balões novos daquela rodada, as
falas anteriores na ordem de leitura. É a matéria-prima dos scripts de avaliação.

Falha de disco fica em aviso: a leitura do usuário vale mais que a coleta.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from ..config import CollectorConfig
from ..models import BBox, Capture, TextBlock
from .tracker import is_partial, prepare

log = logging.getLogger(__name__)


def _to_image(shot: Capture, bbox: BBox) -> BBox:
    """Inverso de `Capture.to_desktop`."""
    ox, oy = shot.origin
    x1, y1, x2, y2 = bbox
    return (
        round((x1 - ox) * shot.scale),
        round((y1 - oy) * shot.scale),
        round((x2 - ox) * shot.scale),
        round((y2 - oy) * shot.scale),
    )


class CaptureCollector:
    def __init__(self, cfg: CollectorConfig, clock: Callable[[], datetime] = datetime.now) -> None:
        self._cfg = cfg
        self._clock = clock
        self._last: np.ndarray | None = None
        self.saved = 0

    def _repeated(self, frame: np.ndarray) -> bool:
        last = self._last
        if last is None or last.shape != frame.shape:
            return False
        return float(np.abs(frame - last).mean()) < self._cfg.min_change

    def save(
        self, shot: Capture, blocks: list[TextBlock], context: Mapping[int, list[str]]
    ) -> Path | None:
        """Grava a rodada e devolve o caminho da imagem, ou `None` se ela foi pulada.

        `context` vem indexado por `id(bloco)` e só tem os blocos traduzidos nesta rodada.
        """
        frame = prepare(shot.image, self._cfg.downscale)
        if self._repeated(frame):
            return None

        records = [
            {
                "bbox": _to_image(shot, block.bbox),
                "source": block.source,
                "translated": block.translated,
                "confidence": round(block.confidence, 4),
                "needs_review": block.needs_review,
                "partial": is_partial(block),
                "new": id(block) in context,
                "context": context.get(id(block), []),
            }
            for block in blocks
        ]
        now = self._clock()
        folder = self._cfg.root / now.strftime("%Y-%m-%d")
        image_path = folder / f"{now.strftime('%H%M%S-%f')}.webp"
        params = [cv2.IMWRITE_WEBP_QUALITY, self._cfg.webp_quality]
        try:
            encoded, data = cv2.imencode(".webp", shot.image, params)
            if not encoded:
                raise OSError("o OpenCV não codificou a captura em webp")
            folder.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(data.tobytes())
            payload = json.dumps({"blocks": records}, ensure_ascii=False, indent=2)
            image_path.with_suffix(".json").write_text(payload + "\n", encoding="utf-8")
        except OSError as exc:
            log.warning("Captura não gravada: %s", exc)
            return None

        self._last = frame
        self.saved += 1
        return image_path
