"""Quanto a página andou entre dois quadros, e o que fazer com as caixas já desenhadas.

Funções puras, sem Qt e sem GPU — dá para testar com imagem sintética e listas de bbox,
como `gate.py` e `grouping.py`. Quem roda o laço e fala com a UI é `core/scroll.py`.

**Convenção de sinal:** `Shift.dy` é o deslocamento do conteúdo **na tela**. Rolar a
página para baixo faz o conteúdo subir, então `dy` fica negativo. Isso é o que permite
`shift_blocks` simplesmente somar `dy` ao topo de cada caixa.

Por que correlação de fase e não casar features: ela mede a translação da imagem inteira
de uma vez, em 8 ms na imagem reduzida a 1/4, e devolve junto uma resposta que serve de
confiança. Medido nesta máquina: recupera o deslocamento exato até ~400 px (40% da altura
da viewport), com resposta caindo de 0.97 em 60 px para 0.41 em 400 px e 0.01 quando o
conteúdo mudou demais para ser translação.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ..config import ScrollConfig
from ..models import Region, TextBlock


def prepare(image: np.ndarray, downscale: float) -> np.ndarray:
    """Quadro no formato que a correlação exige: cinza, reduzido e `float64`.

    Reduzir não é só economia — é o que torna o laço viável: 8 ms a 1/4 contra 92 ms em
    resolução cheia, com a mesma precisão (erro abaixo de 0.5 px).
    """
    small = cv2.resize(image, None, fx=downscale, fy=downscale, interpolation=cv2.INTER_AREA)
    gray = small if small.ndim == 2 else cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    # O `phaseCorrelate` completa a entrada até `getOptimalDFTSize`, e com esse tamanho
    # ímpar todo deslocamento sai com meio pixel de viés — 2 px na tela, por quadro, que
    # a rolagem soma e o registro de balões herda. Num tamanho par que já é ótimo a
    # medida é exata, então o quadro é cortado até um.
    height, width = gray.shape
    return gray[: _even_dft_size(height), : _even_dft_size(width)].astype(np.float64)


def _even_dft_size(n: int) -> int:
    """O maior tamanho até `n` que é par e que a DFT do OpenCV usa sem completar."""
    while n > 2 and (n % 2 or cv2.getOptimalDFTSize(n) != n):
        n -= 1
    return n


@dataclass(frozen=True)
class Shift:
    """Deslocamento medido entre dois quadros, em pixels da imagem original."""

    dy: float
    dx: float
    # Resposta da correlação de fase: o quanto os dois quadros realmente se explicam por
    # uma translação.
    response: float
    # Desvio padrão do quadro. Ver `trustworthy`.
    texture: float
    # Altura do quadro, em pixels da imagem original.
    span: float

    def trustworthy(self, cfg: ScrollConfig) -> bool:
        """Se dá para acreditar neste deslocamento.

        O piso de textura **não** é redundante com a resposta, e é a armadilha desta
        medição: um quadro totalmente liso — o vão branco entre dois quadrinhos de um
        webtoon — devolve deslocamento zero com resposta 0.99. Confiante e errado. Sem o
        piso, as caixas ficariam paradas enquanto a página rola embaixo delas.

        O teto de `dy` também não é redundante: a correlação é cíclica, e um salto perto
        de meia altura volta com o sinal trocado e resposta alta. As caixas e o registro
        pulariam uma tela inteira na direção errada.
        """
        return (
            self.response >= cfg.min_response
            and abs(self.dx) <= cfg.max_dx
            and abs(self.dy) <= cfg.max_dy * self.span
            and self.texture >= cfg.min_texture
        )


# Devolvido quando não há com o que comparar, ou os quadros têm formatos diferentes (a
# região de captura mudou). Nunca é confiável: `response` e `texture` zerados reprovam.
UNKNOWN = Shift(dy=0.0, dx=0.0, response=0.0, texture=0.0, span=0.0)


def estimate_shift(previous: np.ndarray, current: np.ndarray, cfg: ScrollConfig) -> Shift:
    """Deslocamento entre dois quadros já passados por `prepare`."""
    if previous.shape != current.shape or previous.size == 0:
        return UNKNOWN

    # Medido antes da correlação, e sobre cópias, porque `cv2.phaseCorrelate` **escreve
    # nos arrays que recebe**: ele aplica a janela de Hanning no lugar. Sem as cópias,
    # o quadro que o laço guarda para a próxima comparação sai corrompido, e a textura
    # medida depois é a da janela, não a da imagem (um quadro branco chega a "medir"
    # 74.9 de desvio padrão depois da chamada, contra 0.0 antes).
    texture = float(min(previous.std(), current.std()))

    window = cv2.createHanningWindow((previous.shape[1], previous.shape[0]), cv2.CV_64F)
    (dx, dy), response = cv2.phaseCorrelate(previous.copy(), current.copy(), window)
    back = 1.0 / cfg.downscale
    return Shift(
        dy=dy * back,
        dx=dx * back,
        response=float(response),
        # O menor dos dois: um quadro liso entrando é tão ruim quanto um saindo.
        texture=texture,
        span=previous.shape[0] * back,
    )


def is_partial(block: TextBlock) -> bool:
    """O balão estava cortado pela borda da captura quando foi lido."""
    return any(line.partial for line in block.lines)


def shift_blocks(blocks: list[TextBlock], dy: int, region: Region) -> list[TextBlock]:
    """Move as caixas junto com o conteúdo e descarta as que saíram da viewport.

    Muda o `bbox` no lugar, e não numa cópia, de propósito: o sinal `refined` do worker
    identifica os blocos por identidade (ver `App._on_refined`), e trocar os objetos a
    cada quadro quebraria isso.
    """
    kept: list[TextBlock] = []
    for block in blocks:
        x1, y1, x2, y2 = block.bbox
        y1, y2 = y1 + dy, y2 + dy
        if y2 <= region.top or y1 >= region.bottom:
            continue
        block.bbox = (x1, y1, x2, y2)
        kept.append(block)
    return kept
