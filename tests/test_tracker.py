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
    estimate_shift,
    is_partial,
    merge_tracked,
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


# -- juntar leitura nova com o que já estava na tela ------------------------


def test_leitura_inteira_anterior_vence_a_nova_cortada(cfg):
    """A razão de o modo existir.

    O balão foi lido inteiro antes; agora encostou na borda e saiu pela metade. Deixar a
    nova ganhar transformaria uma tradução completa em meia tradução.
    """
    inteiro = block((10, 100, 300, 200), text="frase inteira")
    cortado = block((10, 100, 300, 190), text="frase pela", partial=True)

    resultado = merge_tracked([inteiro], [cortado], cfg)

    assert [b.source for b in resultado] == ["frase inteira"]


def test_leitura_nova_completa_substitui_a_antiga(cfg):
    antiga = block((10, 100, 300, 200), text="lido antes")
    nova = block((12, 102, 302, 202), text="lido agora")

    resultado = merge_tracked([antiga], [nova], cfg)

    assert [b.source for b in resultado] == ["lido agora"]


def test_cortado_anterior_cede_para_a_leitura_inteira(cfg):
    """O caminho inverso: rolou até o balão aparecer todo, então a nova manda."""
    cortado = block((10, 100, 300, 190), text="frase pela", partial=True)
    inteiro = block((10, 100, 300, 200), text="frase inteira")

    resultado = merge_tracked([cortado], [inteiro], cfg)

    assert [b.source for b in resultado] == ["frase inteira"]


def test_bloco_antigo_sem_correspondente_e_mantido(cfg):
    """Já foi lido quando estava visível; sumir agora seria pior que continuar."""
    longe = block((10, 100, 300, 200), text="de antes")
    nova = block((600, 400, 900, 500), text="de agora")

    resultado = merge_tracked([longe], [nova], cfg)

    assert sorted(b.source for b in resultado) == ["de agora", "de antes"]


def test_is_partial_olha_as_linhas():
    assert is_partial(block((0, 0, 10, 10), partial=True))
    assert not is_partial(block((0, 0, 10, 10)))
