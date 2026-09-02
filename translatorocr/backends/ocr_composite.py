"""Detector + reconhecedor, por trás do mesmo `OCRBackend`.

Composição de um detector separado com o reconhecedor OCR.

**O reconhecedor roda uma vez, na imagem inteira**, e as regiões do detector servem para
atribuir e filtrar as linhas resultantes. Isso não é detalhe de otimização — é crítico.
Reconhecer uma vez na imagem cheia é 11x mais rápido do que rodar o pipeline por região
recortada (medido: 103 ms em lote contra 4987 ms em 20 chamadas separadas), porque o
pipeline RapidOCR redetectaria texto dentro de cada recorte.

Chamar apenas o reconhecedor sobre o recorte da região também não resolve: ele espera um
recorte **justo de uma linha**, e com uma região inteira devolve lixo ("HELLO WORLD" saiu
como "cYEnmPGenaYYlo"). Quem produz o recorte justo é o DBNet do RapidOCR, e ele já faz
isso de uma vez na imagem inteira.

Uma linha que o DBNet não achar na imagem cheia não aparece — tudo que cai fora de toda
região detectada é descartado antes de virar bloco.
"""

from __future__ import annotations

import logging

import numpy as np

from ..config import DetectorConfig
from ..models import BBox, Detection, TextLine
from .base import DetectorBackend, OCRBackend
from .detect_bubble import TEXT_KINDS

log = logging.getLogger(__name__)


def _intersection_area(a: BBox, b: BBox) -> int:
    width = min(a[2], b[2]) - max(a[0], b[0])
    height = min(a[3], b[3]) - max(a[1], b[1])
    return width * height if width > 0 and height > 0 else 0


def assign_region(bbox: BBox, regions: list[Detection], min_overlap: float) -> int | None:
    """Índice da região que mais cobre o bbox, ou None se nenhuma cobre o bastante.

    O critério é a fração da **linha** coberta, e não da região: uma linha pequena dentro
    de um balão grande tem que casar, e é o contrário que precisa ser rejeitado.
    """
    area = max(1, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
    best_index, best_area = None, 0
    for index, region in enumerate(regions):
        overlap = _intersection_area(bbox, region.bbox)
        if overlap > best_area:
            best_index, best_area = index, overlap
    return best_index if best_area / area >= min_overlap else None


class CompositeOCR:
    def __init__(
        self,
        detector: DetectorBackend,
        recognizer: OCRBackend,
        cfg: DetectorConfig,
    ) -> None:
        self._detector = detector
        self._recognizer = recognizer
        self._cfg = cfg

    def read(self, image: np.ndarray) -> list[TextLine]:
        regions = [d for d in self._detector.detect(image) if d.kind in TEXT_KINDS]
        if not regions:
            # Nenhum balão. Devolver vazio é deliberado: cair para a imagem inteira aqui
            # traria de volta exatamente o ruído de UI que o detector existe para remover,
            # e faria isso justamente quando ele decidiu que não havia texto.
            log.debug("detector não achou região de texto; nada a reconhecer")
            return []

        lines: list[TextLine] = []
        dropped = 0
        for line in self._recognizer.read(image):
            region_id = assign_region(line.bbox, regions, self._cfg.min_line_overlap)
            if region_id is None:
                dropped += 1
                continue
            lines.append(
                TextLine(
                    bbox=line.bbox,
                    text=line.text,
                    confidence=line.confidence,
                    region_id=region_id,
                )
            )

        log.info(
            "composite: %d regiões → %d linhas (%d fora de qualquer região)",
            len(regions),
            len(lines),
            dropped,
        )
        return lines
