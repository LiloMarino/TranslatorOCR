"""Área selecionada guardada entre sessões, sem Qt."""

from __future__ import annotations

import pytest

from translatorocr.models import Region
from translatorocr.ui.area_store import load_area, save_area

SCREEN = Region(0, 0, 1920, 1080)


def test_area_volta_igual_ao_que_foi_gravado(tmp_path):
    path = tmp_path / "area.json"
    area = Region(100, 50, 800, 900)
    save_area(path, area)
    assert load_area(path, SCREEN) == area


def test_sem_arquivo_nao_ha_area(tmp_path):
    assert load_area(tmp_path / "area.json", SCREEN) is None


def test_none_apaga_o_que_estava_guardado(tmp_path):
    path = tmp_path / "area.json"
    save_area(path, Region(100, 50, 800, 900))
    save_area(path, None)
    assert not path.exists()


def test_apagar_sem_nada_guardado_nao_falha(tmp_path):
    save_area(tmp_path / "area.json", None)


@pytest.mark.parametrize(
    "content",
    [
        "",
        "não é json",
        "[1, 2, 3, 4]",
        '{"left": 1}',
        '{"left": "x", "top": 0, "width": 10, "height": 10}',
        '{"left": null, "top": 0, "width": 10, "height": 10}',
    ],
)
def test_arquivo_corrompido_vale_como_sem_area(tmp_path, content):
    path = tmp_path / "area.json"
    path.write_text(content, encoding="utf-8")
    assert load_area(path, SCREEN) is None


@pytest.mark.parametrize(
    "area",
    [
        Region(1920, 0, 800, 600),  # outro monitor, à direita
        Region(-1000, 0, 800, 600),  # outro monitor, à esquerda
        Region(1500, 0, 800, 600),  # atravessa a borda
        Region(100, 100, 0, 600),  # sem largura
    ],
)
def test_area_fora_da_tela_atual_e_ignorada(tmp_path, area):
    path = tmp_path / "area.json"
    save_area(path, area)
    assert load_area(path, SCREEN) is None
    assert path.exists()


def test_area_vale_em_monitor_com_coordenada_negativa(tmp_path):
    path = tmp_path / "area.json"
    area = Region(-1800, 100, 800, 600)
    save_area(path, area)
    assert load_area(path, Region(-1920, 0, 1920, 1080)) == area


def test_falha_de_disco_nao_interrompe(tmp_path):
    blocked = tmp_path / "arquivo"
    blocked.write_text("")
    save_area(blocked / "area.json", Region(0, 0, 10, 10))
