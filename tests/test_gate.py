"""Gate entre reconhecimento e tradução.

Funções puras: nenhum modelo, nenhuma rede.
"""

from __future__ import annotations

import pytest

from translatorocr.config import GateConfig
from translatorocr.core.gate import (
    apply_gate,
    charset_violation,
    looks_like_garbage,
    normalize_text,
    symbol_ratio,
)
from translatorocr.models import TextBlock


@pytest.fixture
def cfg() -> GateConfig:
    return GateConfig()


def block(text: str, confidence: float = 0.9) -> TextBlock:
    return TextBlock(bbox=(0, 0, 100, 20), source=text, confidence=confidence)


# -- charset ---------------------------------------------------------------


def test_ideograma_com_ocr_em_ingles_e_violacao():
    # O input não tem nada de CJK, mas o reconhecedor emitiu.
    assert charset_violation("Hello 世界", "en")


def test_acentuacao_latina_nao_e_violacao():
    assert not charset_violation("café naïve", "en")


def test_pontuacao_tipografica_nao_e_violacao():
    assert not charset_violation("\u201cDon\u2019t\u201d \u2014 he said\u2026", "en")


def test_charset_nao_se_aplica_a_outro_idioma():
    # O lock só vale para o idioma configurado; outro idioma não é restringido.
    assert not charset_violation("こんにちは", "pt")


# -- heurísticas de lixo ---------------------------------------------------


def test_texto_normal_passa(cfg):
    assert not looks_like_garbage("Are you sure about this?", cfg)


def test_bloco_curto_demais_e_lixo(cfg):
    assert looks_like_garbage("a", cfg)


def test_sopa_de_simbolos_e_lixo(cfg):
    assert looks_like_garbage("|<>*#~ ^^", cfg)


def test_palavra_longa_sem_vogal_e_lixo(cfg):
    # Ruído de borda/ícone lido como letra.
    assert looks_like_garbage("Hello wrtlk", cfg)


def test_sigla_curta_sobrevive(cfg):
    # "HP" não tem vogal mas é curta demais para a regra de 4+ letras disparar.
    assert not looks_like_garbage("HP 240", cfg)


def test_symbol_ratio_de_texto_vazio_e_total():
    assert symbol_ratio("   ") == 1.0


# -- normalização ----------------------------------------------------------


def test_normalize_resolve_ligadura_e_largura_dupla():
    assert normalize_text("ﬁre") == "fire"
    assert normalize_text("Ａ") == "A"  # noqa: RUF001 — a largura dupla é o caso testado


def test_normalize_colapsa_espacos():
    assert normalize_text("  a\n\n  b ") == "a b"


def test_ligadura_normalizada_nao_vira_violacao_de_charset(cfg):
    # Sem o NFKC, 'ﬁ' (U+FB01) passaria de 0xFF e o bloco seria descartado por engano.
    kept = apply_gate([block("ﬁreworks tonight")], cfg, "en")
    assert [b.source for b in kept] == ["fireworks tonight"]


# -- as duas saídas do gate ------------------------------------------------


def test_bloco_bom_passa_sem_marca(cfg):
    kept = apply_gate([block("Let's go home.", 0.95)], cfg, "en")
    assert len(kept) == 1
    assert kept[0].needs_review is False


def test_confianca_intermediaria_passa_marcada(cfg):
    # Entre drop_below e min_confidence: segue para tradução, mas avisado.
    kept = apply_gate([block("Let's go home.", 0.5)], cfg, "en")
    assert len(kept) == 1
    assert kept[0].needs_review is True


def test_confianca_muito_baixa_e_descartada(cfg):
    assert apply_gate([block("Let's go home.", 0.1)], cfg, "en") == []


def test_ideograma_e_descartado(cfg):
    assert apply_gate([block("Hello 世界", 0.99)], cfg, "en") == []


def test_gate_desligado_devolve_tudo_intacto():
    cfg = GateConfig(enabled=False)
    blocks = [block("|<>*#", 0.01), block("Hello 世界", 0.99)]
    assert apply_gate(blocks, cfg, "en") == blocks


def test_ordem_dos_blocos_e_preservada(cfg):
    kept = apply_gate([block("First one."), block("|<>#*"), block("Third one.")], cfg, "en")
    assert [b.source for b in kept] == ["First one.", "Third one."]
