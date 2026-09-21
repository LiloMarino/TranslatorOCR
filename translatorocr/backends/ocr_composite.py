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

**Segunda passada, em mosaico, só para o que falhou.** Em página real de mangá o DBNet
perde balão curto — um balão de uma palavra só não ganhou caixa em nenhuma escala — e
às vezes recorta mal uma linha curta (letra duplicada, confiança ~0.6). O detector de
balão acha as duas regiões, e o reconhecedor lê as duas certo quando recebe a região com
margem. Então as regiões suspeitas — sem linha, com linha de confiança baixa, ou com
linhas cobrindo pouco da altura (linha perdida) — são recortadas, empilhadas numa imagem
só e reconhecidas numa **única** chamada (~150 ms a mais), o que mantém a regra acima.
A leitura da primeira passada concorre com a do mosaico, e fica a melhor.

Medido em duas páginas reais, cada uma inteira e em 8 vistas de tela
(`scripts/eval_pages.py`): sem a segunda passada, 69 balões lidos exatamente e 10
errados; com ela, 82 e 1. Três variações foram tentadas e descartadas:

- Margem tirada da própria imagem, no lugar da **branca**: puxa texto dos balões vizinhos
  que se sobrepõem.
- Refazer toda região, e não só as suspeitas: não ganha nada nas que já estavam certas e
  traz o mesmo vazamento entre balões.
- Cada região em várias escalas no mosaico, ficando a mais confiável: acertou alguns
  balões a mais, mas passou a produzir lixo (letras e números soltos) — a confiança do reconhecedor
  não é boa o bastante para escolher entre escalas. E a escala nem é controlável direito:
  o DBNet amplia a entrada até o lado **menor** chegar a 736 px, então a escala efetiva
  de um recorte depende da largura do mosaico inteiro.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

from ..config import DetectorConfig
from ..geometry import area, intersection_area, overlap_fraction
from ..models import BBox, Detection, TextLine
from .base import DetectorBackend, OCRBackend
from .detect_bubble import TEXT_KINDS

log = logging.getLogger(__name__)

# Espaço branco entre dois recortes no mosaico, para o DBNet não emendar linhas de
# regiões vizinhas.
_MOSAIC_GAP = 20
_WHITE = (255, 255, 255)


def assign_region(bbox: BBox, regions: list[Detection], min_overlap: float) -> int | None:
    """Índice da região que mais cobre o bbox, ou None se nenhuma cobre o bastante.

    O critério é a fração da **linha** coberta, e não da região: uma linha pequena dentro
    de um balão grande tem que casar, e é o contrário que precisa ser rejeitado.
    """
    box_area = max(1, area(bbox))
    best_index, best_area = None, 0
    for index, region in enumerate(regions):
        overlap = intersection_area(bbox, region.bbox)
        if overlap > best_area:
            best_index, best_area = index, overlap
    return best_index if best_area / box_area >= min_overlap else None


def merge_overlapping(regions: list[Detection], threshold: float) -> list[Detection]:
    """Funde regiões em que a sobreposição cobre `threshold` da menor delas.

    O detector às vezes devolve duas caixas de texto para o mesmo balão; com elas
    separadas, a mesma fala virava dois blocos.
    """
    merged = list(regions)
    changed = True
    while changed:
        changed = False
        for i in range(len(merged)):
            for j in range(i + 1, len(merged)):
                a, b = merged[i].bbox, merged[j].bbox
                if overlap_fraction(a, b) < threshold:
                    continue
                union = (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))
                keep = merged[i] if merged[i].score >= merged[j].score else merged[j]
                merged[i] = Detection(bbox=union, kind=keep.kind, score=keep.score)
                del merged[j]
                changed = True
                break
            if changed:
                break
    return merged


def coverage(lines: list[TextLine], region: BBox) -> float:
    """Fração da altura da região ocupada pelas linhas, do topo da primeira ao pé da última.

    A caixa `text_bubble` é justa em volta do texto, então linhas que cobrem pouco dela
    são o sinal de que alguma linha não foi achada.
    """
    if not lines:
        return 0.0
    height = max(1, region[3] - region[1])
    return (max(ln.bbox[3] for ln in lines) - min(ln.bbox[1] for ln in lines)) / height


def touches_edge(bbox: BBox, width: int, height: int, margin: int) -> bool:
    """A região encosta na borda da captura — o balão provavelmente está cortado."""
    return (
        bbox[0] <= margin
        or bbox[1] <= margin
        or bbox[2] >= width - margin
        or bbox[3] >= height - margin
    )


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
        regions = merge_overlapping(regions, self._cfg.region_merge)

        by_region: dict[int, list[TextLine]] = {}
        dropped = 0
        for line in self._recognizer.read(image):
            region_id = assign_region(line.bbox, regions, self._cfg.min_line_overlap)
            if region_id is None:
                dropped += 1
                continue
            by_region.setdefault(region_id, []).append(line)

        redo: list[int] = []
        if self._cfg.fallback:
            redo = [
                i for i in range(len(regions)) if self._suspect(by_region.get(i, []), regions[i])
            ]
            for region_id, second in self._read_mosaic(image, regions, redo).items():
                # A primeira leitura concorre: a segunda passada só troca o que leu melhor.
                first = by_region.get(region_id, [])
                region = regions[region_id]
                if self._rank(second, region) > self._rank(first, region):
                    by_region[region_id] = second

        height, width = image.shape[:2]
        out: list[TextLine] = []
        for region_id, lines in by_region.items():
            partial = touches_edge(regions[region_id].bbox, width, height, self._cfg.edge_margin)
            out.extend(
                TextLine(
                    bbox=ln.bbox,
                    text=ln.text,
                    confidence=ln.confidence,
                    region_id=region_id,
                    partial=partial,
                )
                for ln in lines
            )

        log.info(
            "composite: %d regiões → %d linhas (%d fora de qualquer região, %d refeitas)",
            len(regions),
            len(out),
            dropped,
            len(redo),
        )
        return out

    def _suspect(self, lines: list[TextLine], region: Detection) -> bool:
        return (
            min((ln.confidence for ln in lines), default=0.0) < self._cfg.fallback_confidence
            or coverage(lines, region.bbox) < self._cfg.min_coverage
        )

    def _rank(self, lines: list[TextLine], region: Detection) -> tuple[bool, float]:
        """Ordem entre leituras da mesma região: cobrir a região vem antes da confiança,
        senão a leitura que perdeu uma linha, mas acertou as outras, ganharia."""
        if not lines:
            return (False, -1.0)
        return (
            coverage(lines, region.bbox) >= self._cfg.min_coverage,
            min(ln.confidence for ln in lines),
        )

    def _read_mosaic(
        self, image: np.ndarray, regions: list[Detection], indices: list[int]
    ) -> dict[int, list[TextLine]]:
        """Reconhece as regiões pedidas numa chamada só, devolvendo linhas no espaço da
        imagem original, por região."""
        if not indices:
            return {}

        pad = self._cfg.fallback_pad
        tiles: list[np.ndarray] = []
        # (região, topo da faixa no mosaico, altura da faixa)
        strips: list[tuple[int, int, int]] = []
        top = 0
        for index in indices:
            x1, y1, x2, y2 = regions[index].bbox
            tile = cv2.copyMakeBorder(
                image[y1:y2, x1:x2], pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=_WHITE
            )
            tiles.append(tile)
            strips.append((index, top, tile.shape[0]))
            top += tile.shape[0] + _MOSAIC_GAP

        mosaic = np.full(
            (top - _MOSAIC_GAP, max(t.shape[1] for t in tiles), 3), 255, dtype=image.dtype
        )
        for tile, (_, strip_top, strip_height) in zip(tiles, strips, strict=True):
            mosaic[strip_top : strip_top + strip_height, : tile.shape[1]] = tile

        found: dict[int, list[TextLine]] = {index: [] for index in indices}
        for line in self._recognizer.read(mosaic):
            center_y = (line.bbox[1] + line.bbox[3]) / 2
            for index, strip_top, strip_height in strips:
                if strip_top <= center_y < strip_top + strip_height:
                    # Do mosaico de volta para a imagem: tira o topo da faixa e a margem,
                    # soma a origem da região.
                    dx = regions[index].bbox[0] - pad
                    dy = regions[index].bbox[1] - pad - strip_top
                    x1, y1, x2, y2 = line.bbox
                    found[index].append(
                        TextLine(
                            bbox=(x1 + dx, y1 + dy, x2 + dx, y2 + dy),
                            text=line.text,
                            confidence=line.confidence,
                        )
                    )
                    break
        return found
