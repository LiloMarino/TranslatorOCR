"""Rastreio da rolagem: medir o deslocamento e decidir em quem acreditar.

Funções puras sobre imagem sintética: nenhum modelo, nenhuma captura, nenhuma página
real. O que importa aqui é a aritmética do deslocamento e, principalmente, os casos em
que a medição **não** pode ser acreditada — é ela que decide se a caixa desenhada
acompanha o texto ou fica parada em cima da arte errada.
"""

from __future__ import annotations

import numpy as np
import pytest

from translatorocr.config import ScrollConfig
from translatorocr.core.tracker import (
    Shift,
    estimate_shift,
    is_partial,
    prepare,
    shift_blocks,
)
from translatorocr.models import Region, TextBlock, TextLine


@pytest.fixture
def cfg() -> ScrollConfig:
    return ScrollConfig()


def textured(height: int = 2000, width: int = 1200) -> np.ndarray:
    """Página sintética com estrutura, como conteúdo de verdade.

    Ruído fino **não** serve: a correlação roda na imagem reduzida a 1/4, e ruído de um
    pixel não sobrevive à redução. Por isso a base é um campo grosso (blocos de 16 px)
    esticado, que é o que uma página de quadrinhos tem — formas grandes — com um pouco
    de ruído fino por cima.
    """
    rng = np.random.default_rng(1234)
    coarse = rng.integers(0, 255, size=(height // 16 + 1, width // 16 + 1), dtype=np.uint8)
    gray = np.repeat(np.repeat(coarse, 16, axis=0), 16, axis=1)[:height, :width]
    fine = rng.integers(0, 40, size=(height, width), dtype=np.uint8)
    gray = np.clip(gray.astype(np.int16) + fine - 20, 0, 255).astype(np.uint8)
    return np.repeat(gray[:, :, None], 3, axis=2)


def blank(height: int = 2000, width: int = 1200) -> np.ndarray:
    """O vão branco entre dois quadrinhos."""
    return np.full((height, width, 3), 255, dtype=np.uint8)


def viewport(page: np.ndarray, top: int, height: int = 800) -> np.ndarray:
    return page[top : top + height]


def block(bbox, text: str = "abc", partial: bool = False) -> TextBlock:
    line = TextLine(bbox=bbox, text=text, confidence=0.9, partial=partial)
    return TextBlock(bbox=bbox, source=text, confidence=0.9, lines=[line])


# -- medição do deslocamento ------------------------------------------------


# A tolerância cresce com a rolagem porque a precisão cai junto com a sobreposição entre
# os dois quadros: quanto menos conteúdo em comum, menos há para correlacionar. Errar 1-2 px
# não incomoda — a caixa desencosta um fio enquanto rola e volta ao lugar quando o pipeline
# roda na parada.
@pytest.mark.parametrize("rolagem,tolerancia", [(8, 1.0), (40, 1.0), (150, 2.0)])
def test_rolar_para_baixo_move_o_conteudo_para_cima(cfg, rolagem, tolerancia):
    page = textured()
    antes = prepare(viewport(page, 100), cfg.downscale)
    depois = prepare(viewport(page, 100 + rolagem), cfg.downscale)

    shift = estimate_shift(antes, depois, cfg)

    # Sinal negativo: o conteúdo subiu na tela. É o que `shift_blocks` soma ao bbox.
    assert shift.dy == pytest.approx(-rolagem, abs=tolerancia)
    assert shift.trustworthy(cfg)


# Alturas cuja imagem reduzida o OpenCV completaria até um tamanho ímpar (135 e 225 a
# 1/4), ao lado de alturas que já caíam num tamanho par. A rolagem soma o erro de cada
# quadro, então aqui a tolerância é a de um quadro que não pode deixar resto.
@pytest.mark.parametrize("altura", [540, 536, 900, 800, 1000])
def test_medida_nao_depende_da_altura_da_regiao(cfg, altura):
    page = textured()
    antes = prepare(viewport(page, 100, altura), cfg.downscale)
    depois = prepare(viewport(page, 120, altura), cfg.downscale)

    assert estimate_shift(antes, depois, cfg).dy == pytest.approx(-20, abs=0.5)


def test_quadro_liso_nao_e_confiavel_apesar_da_resposta_alta(cfg):
    """A armadilha desta medição.

    Uma área sem nenhuma textura devolve "não andou nada" com resposta altíssima —
    confiante e errada. Se isso passasse, as caixas ficariam paradas enquanto a página
    rola por baixo delas. Quem barra é o piso de textura, não a resposta.
    """
    page = blank()
    shift = estimate_shift(
        prepare(viewport(page, 100), cfg.downscale),
        prepare(viewport(page, 140), cfg.downscale),
        cfg,
    )

    assert shift.response >= cfg.min_response  # a resposta sozinha aprovaria
    assert shift.texture < cfg.min_texture
    assert not shift.trustworthy(cfg)


def test_deslocamento_horizontal_nao_e_rolagem(cfg):
    page = textured()
    lado = np.roll(viewport(page, 100), 120, axis=1)
    shift = estimate_shift(
        prepare(viewport(page, 100), cfg.downscale), prepare(lado, cfg.downscale), cfg
    )

    assert abs(shift.dx) > cfg.max_dx
    assert not shift.trustworthy(cfg)


def test_salto_grande_demais_nao_e_confiavel(cfg):
    """Trocar de página ou pular o scroll: não sobra sobreposição para correlacionar."""
    page = textured()
    shift = estimate_shift(
        prepare(viewport(page, 100), cfg.downscale),
        prepare(viewport(page, 1100), cfg.downscale),
        cfg,
    )

    assert not shift.trustworthy(cfg)


def test_salto_perto_de_meia_altura_nao_e_confiavel(cfg):
    """A correlação é cíclica: perto de meia altura o sinal do deslocamento é ambíguo, e
    em página real a medida volta com o sinal trocado e resposta alta."""
    trocado = Shift(dy=480.0, dx=0.0, response=0.9, texture=50.0, span=1000.0)
    rapido = Shift(dy=-300.0, dx=0.0, response=0.9, texture=50.0, span=1000.0)

    assert not trocado.trustworthy(cfg)
    assert rapido.trustworthy(cfg)


def test_formatos_diferentes_nao_sao_comparaveis(cfg):
    """A região de captura mudou no meio do caminho (troca de monitor, nova seleção)."""
    shift = estimate_shift(
        prepare(textured(400, 600), cfg.downscale),
        prepare(textured(480, 600), cfg.downscale),
        cfg,
    )

    assert not shift.trustworthy(cfg)


def test_medir_nao_estraga_os_quadros_recebidos(cfg):
    """`cv2.phaseCorrelate` escreve nos arrays que recebe — aplica a janela de Hanning
    no lugar. O laço guarda o quadro atual para comparar com o próximo, então deixar
    isso passar corromperia toda medição a partir da segunda.
    """
    page = textured()
    antes = prepare(viewport(page, 100), cfg.downscale)
    depois = prepare(viewport(page, 140), cfg.downscale)
    copia_antes, copia_depois = antes.copy(), depois.copy()

    estimate_shift(antes, depois, cfg)

    assert np.array_equal(antes, copia_antes)
    assert np.array_equal(depois, copia_depois)


# -- caixas acompanhando a rolagem ------------------------------------------


def test_caixa_acompanha_o_conteudo(cfg):
    region = Region(left=0, top=0, width=1000, height=600)
    movido = shift_blocks([block((10, 200, 300, 260))], -50, region)

    assert movido[0].bbox == (10, 150, 300, 210)


def test_caixa_que_saiu_da_viewport_e_descartada(cfg):
    region = Region(left=0, top=0, width=1000, height=600)
    saindo = block((10, 20, 300, 80))
    ficando = block((10, 400, 300, 460))

    restaram = shift_blocks([saindo, ficando], -100, region)

    assert [b.bbox for b in restaram] == [(10, 300, 300, 360)]


def test_caixa_meio_fora_continua_valendo(cfg):
    """Sair pela metade não é sair: o pedaço visível ainda ajuda a ler."""
    region = Region(left=0, top=0, width=1000, height=600)
    restaram = shift_blocks([block((10, 20, 300, 120))], -60, region)

    assert restaram[0].bbox == (10, -40, 300, 60)


def test_is_partial_olha_as_linhas():
    assert is_partial(block((0, 0, 10, 10), partial=True))
    assert not is_partial(block((0, 0, 10, 10)))
