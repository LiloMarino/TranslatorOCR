"""Testes do agrupamento — o estágio que substitui o `" ".join` da versão antiga.

São puros: sem GPU, sem Qt, sem rede.
"""

from __future__ import annotations

import pytest

from translatorocr.config import GroupingConfig
from translatorocr.core.grouping import group, merge_lines, reading_order
from translatorocr.models import TextLine


def line(x1, y1, x2, y2, text="x", conf=0.9) -> TextLine:
    return TextLine(bbox=(x1, y1, x2, y2), text=text, confidence=conf)


@pytest.fixture
def cfg() -> GroupingConfig:
    return GroupingConfig()


def test_linhas_do_mesmo_balao_viram_um_bloco(cfg):
    lines = [
        line(100, 100, 300, 120, "Hello, are you"),
        line(100, 125, 300, 145, "alright?"),
    ]
    blocks = merge_lines(lines, cfg)
    assert len(blocks) == 1
    assert blocks[0].source == "Hello, are you alright?"
    assert blocks[0].bbox == (100, 100, 300, 145)


def test_baloes_verticalmente_distantes_nao_se_fundem(cfg):
    lines = [line(100, 100, 300, 120, "primeiro"), line(100, 600, 300, 620, "segundo")]
    blocks = merge_lines(lines, cfg)
    assert len(blocks) == 2


def test_baloes_lado_a_lado_nao_se_fundem(cfg):
    """Mesma altura, mas sem sobreposição horizontal — são balões diferentes."""
    lines = [line(100, 100, 300, 120, "esquerda"), line(700, 105, 900, 125, "direita")]
    blocks = merge_lines(lines, cfg)
    assert len(blocks) == 2
    assert {b.source for b in blocks} == {"esquerda", "direita"}


def test_confianca_do_bloco_e_a_menor_das_linhas(cfg):
    lines = [
        line(100, 100, 300, 120, "boa", conf=0.98),
        line(100, 125, 300, 145, "ruim", conf=0.42),
    ]
    (block,) = merge_lines(lines, cfg)
    assert block.confidence == pytest.approx(0.42)


def test_ordem_de_leitura_ltr(cfg):
    lines = [
        line(700, 100, 900, 120, "B"),
        line(100, 100, 300, 120, "A"),
        line(100, 500, 300, 520, "C"),
    ]
    assert [b.source for b in group(lines, cfg)] == ["A", "B", "C"]


def test_ordem_de_leitura_rtl_inverte_a_faixa():
    cfg = GroupingConfig(reading_order="rtl")
    lines = [
        line(100, 100, 300, 120, "esquerda"),
        line(700, 100, 900, 120, "direita"),
    ]
    assert [b.source for b in group(lines, cfg)] == ["direita", "esquerda"]


def test_coluna_longa_nao_vira_um_bloco_gigante():
    """Regressão: uma sidebar de IDE — linhas alinhadas e igualmente espaçadas —
    encadeava transitivamente e virava um bloco só de centenas de pixels."""
    cfg = GroupingConfig(max_lines_per_block=8)
    lines = [line(100, 100 + i * 25, 300, 118 + i * 25, f"item{i}") for i in range(30)]
    blocks = merge_lines(lines, cfg)
    assert len(blocks) >= 4
    assert all(len(b.lines) <= 8 for b in blocks)


def test_entrada_vazia(cfg):
    assert merge_lines([], cfg) == []
    assert reading_order([], cfg) == []


def test_bloco_unico_sobrevive(cfg):
    blocks = group([line(10, 10, 50, 30, "só")], cfg)
    assert len(blocks) == 1 and blocks[0].source == "só"


def test_texto_do_bloco_prefere_a_traducao(cfg):
    (block,) = merge_lines([line(0, 0, 10, 10, "hello")], cfg)
    assert block.text == "hello"
    block.translated = "olá"
    assert block.text == "olá"


# -- fronteira vinda do detector (region_id) -------------------------------
#
# Quando um detector de balão rodou, a fronteira do bloco veio do modelo e tem
# precedência sobre a heurística de proximidade.


def rline(x1, y1, x2, y2, region_id, text="x") -> TextLine:
    return TextLine(bbox=(x1, y1, x2, y2), text=text, confidence=0.9, region_id=region_id)


def test_linhas_de_regioes_diferentes_nunca_se_fundem(cfg):
    # Geometricamente estas duas se fundiriam: adjacentes e alinhadas. O detector diz
    # que são balões distintos, e isso vale mais que a geometria.
    lines = [rline(100, 100, 300, 120, 0), rline(100, 125, 300, 145, 1)]
    assert len(merge_lines(lines, cfg)) == 2


def test_linhas_da_mesma_regiao_se_fundem_normalmente(cfg):
    lines = [
        rline(100, 100, 300, 120, 0, "Hello, are you"),
        rline(100, 125, 300, 145, 0, "alright?"),
    ]
    blocks = merge_lines(lines, cfg)
    assert len(blocks) == 1
    assert blocks[0].source == "Hello, are you alright?"


def test_teto_de_linhas_nao_se_aplica_dentro_de_uma_regiao(cfg):
    # Um balão de 12 linhas é um bloco só. Sem region_id, o teto de 8 o quebraria em
    # dois — que é exatamente a limitação que o detector remove.
    lines = [rline(100, 100 + i * 25, 300, 120 + i * 25, 0) for i in range(12)]
    blocks = merge_lines(lines, cfg)
    assert len(blocks) == 1
    assert len(blocks[0].lines) == 12


def test_sem_region_id_o_teto_continua_valendo(cfg):
    # Comportamento do v1 preservado para o caminho sem detector.
    lines = [line(100, 100 + i * 25, 300, 120 + i * 25) for i in range(12)]
    assert len(merge_lines(lines, cfg)) > 1


def test_region_id_ausente_de_um_lado_nao_funde(cfg):
    # Situação mista não deveria acontecer, mas se acontecer o conservador é separar.
    lines = [rline(100, 100, 300, 120, 0), line(100, 125, 300, 145)]
    assert len(merge_lines(lines, cfg)) == 2


def test_palavras_lado_a_lado_saem_em_ordem_de_leitura(cfg):
    """Regressão: o reconhecedor quebra por palavra quando o espaçamento é largo.

    Encontrado rodando o pipeline de verdade. Agrupar só na vertical empilhava as
    colunas — "I CAN'T BELIEVE YOU DID THAT!" saía como dois blocos, "I CAN'T YOU" e
    "BELIEVE THAT!". Dentro de uma região a ordem tem que ser linha a linha.
    """
    lines = [
        rline(497, 409, 585, 434, 0, "I CAN'T"),
        rline(584, 410, 683, 434, 0, "BELIEVE"),
        rline(500, 456, 551, 477, 0, "YOU"),
        rline(551, 457, 595, 476, 0, "DID"),
        rline(588, 455, 667, 478, 0, "THAT!"),
    ]
    blocks = merge_lines(lines, cfg)
    assert len(blocks) == 1
    assert blocks[0].source == "I CAN'T BELIEVE YOU DID THAT!"
    assert blocks[0].bbox == (497, 409, 683, 478)


def test_ordem_de_leitura_dentro_do_bloco_respeita_rtl():
    cfg = GroupingConfig(reading_order="rtl")
    lines = [rline(10, 0, 40, 20, 0, "esquerda"), rline(60, 0, 90, 20, 0, "direita")]
    assert merge_lines(lines, cfg)[0].source == "direita esquerda"


def test_entrada_fora_de_ordem_ainda_sai_ordenada(cfg):
    lines = [
        rline(100, 100, 200, 120, 0, "segunda"),
        rline(10, 10, 90, 30, 0, "primeira"),
    ]
    assert merge_lines(lines, cfg)[0].source == "primeira segunda"
