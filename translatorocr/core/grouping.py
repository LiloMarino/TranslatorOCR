"""Linhas reconhecidas → blocos de texto, em ordem de leitura.

Preserva bbox e confiança por linha e agrupa em blocos com ordem de leitura
explícita, em vez de concatenar tudo numa string só na ordem arbitrária do detector.

Funções puras, sem GPU e sem Qt: dá para testar com listas de bbox sintéticas.
"""

from __future__ import annotations

from statistics import median

from ..config import GroupingConfig
from ..models import BBox, TextBlock, TextLine


def _h_overlap_ratio(a: BBox, b: BBox) -> float:
    """Sobreposição horizontal, como fração da largura do mais estreito."""
    overlap = min(a[2], b[2]) - max(a[0], b[0])
    if overlap <= 0:
        return 0.0
    narrowest = min(a[2] - a[0], b[2] - b[0])
    return overlap / narrowest if narrowest > 0 else 0.0


def _union(a: BBox, b: BBox) -> BBox:
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _v_overlap_ratio(a: BBox, b: BBox) -> float:
    """Sobreposição vertical, como fração da altura do mais baixo."""
    overlap = min(a[3], b[3]) - max(a[1], b[1])
    if overlap <= 0:
        return 0.0
    shortest = min(a[3] - a[1], b[3] - b[1])
    return overlap / shortest if shortest > 0 else 0.0


def order_lines(lines: list[TextLine], cfg: GroupingConfig) -> list[TextLine]:
    """Ordena pedaços de texto em ordem de leitura dentro de um bloco.

    Necessário porque o reconhecedor nem sempre devolve uma linha inteira por caixa:
    com espaçamento largo ele quebra por palavra. Empilhar isso só por `y` embaralha a
    frase — duas palavras lado a lado viram linhas diferentes e o texto sai em coluna.

    Agrupa em faixas pela sobreposição **vertical** (dois pedaços na mesma linha visual
    se sobrepõem em y), ordena as faixas por topo e, dentro da faixa, por x.
    """
    if not lines:
        return []

    bands: list[list[TextLine]] = []
    for line in sorted(lines, key=lambda ln: (ln.bbox[1], ln.bbox[0])):
        for band in bands:
            if _v_overlap_ratio(band[0].bbox, line.bbox) >= 0.5:
                band.append(line)
                break
        else:
            bands.append([line])

    right_to_left = cfg.reading_order.lower() == "rtl"
    ordered: list[TextLine] = []
    for band in bands:
        ordered.extend(sorted(band, key=lambda ln: ln.bbox[0], reverse=right_to_left))
    return ordered


def _make_block(lines: list[TextLine], cfg: GroupingConfig) -> TextBlock:
    ordered = order_lines(lines, cfg)
    bbox = ordered[0].bbox
    for line in ordered[1:]:
        bbox = _union(bbox, line.bbox)
    return TextBlock(
        bbox=bbox,
        source=" ".join(ln.text for ln in ordered),
        confidence=min(ln.confidence for ln in ordered),
        lines=ordered,
    )


def _merge_by_geometry(lines: list[TextLine], cfg: GroupingConfig) -> list[TextBlock]:
    """Reconstitui blocos por proximidade, para quando não houve detector.

    Duas linhas entram no mesmo bloco quando o gap vertical entre elas é menor que
    `line_gap_ratio` x altura mediana da linha **e** a sobreposição horizontal alcança
    `min_h_overlap`. O teto de `max_lines_per_block` é o freio contra encadeamento
    transitivo: sem ele, uma coluna de linhas igualmente espaçadas — uma sidebar de IDE,
    um índice — funde tudo num bloco só, porque cada linha casa com a anterior.
    """
    if not lines:
        return []

    ordered = sorted(lines, key=lambda ln: (ln.bbox[1], ln.bbox[0]))
    heights = [ln.height for ln in ordered if ln.height > 0]
    max_gap = median(heights) * cfg.line_gap_ratio if heights else 0.0

    groups: list[list[TextLine]] = []
    for line in ordered:
        for group_ in groups:
            if len(group_) >= cfg.max_lines_per_block:
                continue
            previous = group_[-1]
            gap = line.bbox[1] - previous.bbox[3]
            if gap <= max_gap and _h_overlap_ratio(previous.bbox, line.bbox) >= cfg.min_h_overlap:
                group_.append(line)
                break
        else:
            groups.append([line])

    return [_make_block(g, cfg) for g in groups]


def merge_lines(lines: list[TextLine], cfg: GroupingConfig) -> list[TextBlock]:
    """Linhas reconhecidas → blocos de tradução.

    Dois caminhos, e o primeiro é muito melhor que o segundo. Quando as linhas trazem
    `region_id` — isto é, quando um detector de balão rodou — **cada região é um
    bloco**, ponto: a fronteira veio do modelo e não há nada a inferir. Sem detector,
    cai-se na heurística de proximidade, que é o que o v1 fazia.

    A diferença não é acadêmica: o reconhecedor quebra por palavra quando o
    espaçamento é largo, e a heurística, que só funde na vertical, empilha as palavras
    em coluna — "I CAN'T BELIEVE YOU DID THAT!" sai como "I CAN'T YOU" e "BELIEVE
    THAT!". Dentro de uma região isso não acontece, porque a ordem de leitura é
    resolvida por `order_lines`.
    """
    if not lines:
        return []

    by_region: dict[int, list[TextLine]] = {}
    loose: list[TextLine] = []
    for line in lines:
        if line.region_id is None:
            loose.append(line)
        else:
            by_region.setdefault(line.region_id, []).append(line)

    blocks = [_make_block(group_, cfg) for group_ in by_region.values()]
    blocks.extend(_merge_by_geometry(loose, cfg))
    return blocks


def reading_order(blocks: list[TextBlock], cfg: GroupingConfig) -> list[TextBlock]:
    """Ordena os blocos em ordem de leitura.

    Agrupa em faixas horizontais — dois blocos estão na mesma faixa se seus topos
    diferem por menos que `row_band_ratio` x altura do bloco — e ordena dentro da
    faixa por x. `reading_order = "rtl"` inverte o sentido horizontal.
    """
    if not blocks:
        return []

    ordered = sorted(blocks, key=lambda b: b.bbox[1])
    bands: list[list[TextBlock]] = []
    for block in ordered:
        height = block.bbox[3] - block.bbox[1]
        tolerance = height * cfg.row_band_ratio
        if bands and abs(block.bbox[1] - bands[-1][0].bbox[1]) <= tolerance:
            bands[-1].append(block)
        else:
            bands.append([block])

    right_to_left = cfg.reading_order.lower() == "rtl"
    result: list[TextBlock] = []
    for band in bands:
        result.extend(sorted(band, key=lambda b: b.bbox[0], reverse=right_to_left))
    return result


def group(lines: list[TextLine], cfg: GroupingConfig) -> list[TextBlock]:
    return reading_order(merge_lines(lines, cfg), cfg)
