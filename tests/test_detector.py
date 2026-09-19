"""Detector de balão e CompositeOCR — pós-processamento, sem carregar o modelo.

O que importa testar aqui é a aritmética: a desnormalização das caixas e a translação
das linhas do espaço do recorte de volta para o espaço da imagem cheia. Errar isso põe
a caixa no lugar errado da tela, que é o sintoma mais caro de diagnosticar.
"""

from __future__ import annotations

import numpy as np
import pytest

from translatorocr.backends.detect_bubble import LABELS, BubbleDetector
from translatorocr.backends.ocr_composite import CompositeOCR
from translatorocr.config import DetectorConfig
from translatorocr.models import Detection, TextLine


class FakeSession:
    """Dublê da sessão ONNX, devolvendo labels/boxes/scores como o grafo real."""

    def __init__(self, labels, boxes, scores) -> None:
        self.labels = np.array([labels], dtype=np.int64)
        self.boxes = np.array([boxes], dtype=np.float32)
        self.scores = np.array([scores], dtype=np.float32)
        self.feeds: list[dict] = []

    def run(self, _outputs, feeds):
        self.feeds.append(feeds)
        return [self.labels, self.boxes, self.scores]

    def get_providers(self):
        return ["CPUExecutionProvider"]


def detector(labels, boxes, scores, **kw) -> BubbleDetector:
    """Monta o detector sem tocar no disco nem no onnxruntime."""
    det = BubbleDetector.__new__(BubbleDetector)
    det._cfg = DetectorConfig(**kw)
    det._session = FakeSession(labels, boxes, scores)
    return det


def test_caixas_normalizadas_viram_pixel_da_imagem():
    # Meia largura, meia altura: com uma imagem 200x100 tem que sair (50,25)-(100,50).
    det = detector([1], [[0.25, 0.25, 0.5, 0.5]], [0.9])
    out = det.detect(np.zeros((100, 200, 3), dtype=np.uint8))
    assert [d.bbox for d in out] == [(50, 25, 100, 50)]


def test_orig_target_sizes_e_unitario():
    """A sonda que torna a ordem dos eixos irrelevante.

    O grafo multiplica as caixas por `orig_target_sizes.repeat(1,2)`, e as duas
    convenções possíveis (h,w)/(w,h) dão resultados diferentes numa imagem não-quadrada.
    Passando [[1,1]] as caixas voltam normalizadas e a escala é nossa.
    """
    det = detector([1], [[0.0, 0.0, 1.0, 1.0]], [0.9])
    det.detect(np.zeros((100, 200, 3), dtype=np.uint8))
    assert det._session.feeds[0]["orig_target_sizes"].tolist() == [[1, 1]]


def test_imagem_e_reescalada_para_o_input_size():
    det = detector([1], [[0, 0, 1, 1]], [0.9], input_size=640)
    det.detect(np.zeros((100, 200, 3), dtype=np.uint8))
    assert det._session.feeds[0]["images"].shape == (1, 3, 640, 640)


def test_score_abaixo_do_limiar_e_descartado():
    det = detector([1, 1], [[0, 0, 0.5, 0.5], [0.5, 0.5, 1, 1]], [0.9, 0.1])
    assert len(det.detect(np.zeros((100, 100, 3), dtype=np.uint8))) == 1


def test_labels_viram_os_nomes_do_modelo():
    det = detector([0, 1, 2], [[0, 0, 1, 1]] * 3, [0.9] * 3)
    out = det.detect(np.zeros((100, 100, 3), dtype=np.uint8))
    assert [d.kind for d in out] == list(LABELS)


def test_caixa_degenerada_e_descartada():
    det = detector([1], [[0.5, 0.5, 0.5, 0.5]], [0.9])
    assert det.detect(np.zeros((100, 100, 3), dtype=np.uint8)) == []


def test_caixa_estourando_a_borda_e_clampada():
    det = detector([1], [[-0.5, -0.5, 1.5, 1.5]], [0.9])
    assert [d.bbox for d in det.detect(np.zeros((100, 200, 3), dtype=np.uint8))] == [
        (0, 0, 200, 100)
    ]


# -- CompositeOCR ----------------------------------------------------------


class FakeDetector:
    def __init__(self, detections: list[Detection]) -> None:
        self._detections = detections
        self.calls = 0

    def detect(self, image):
        self.calls += 1
        return self._detections


class FakeRecognizer:
    """Devolve linhas fixas na imagem cheia e conta quantas vezes foi chamado."""

    def __init__(self, lines: list[TextLine] | None = None) -> None:
        self.calls = 0
        self._lines = lines or [TextLine(bbox=(10, 10, 50, 30), text="oi", confidence=0.9)]

    def read(self, image):
        self.calls += 1
        return list(self._lines)


@pytest.fixture
def image() -> np.ndarray:
    return np.zeros((200, 300, 3), dtype=np.uint8)


def composite(regions, lines, **kw):
    # Sem a segunda passada por padrão: estes testes são sobre a atribuição, e o dublê
    # de reconhecedor devolveria as mesmas linhas também no mosaico.
    cfg = DetectorConfig(**{"fallback": False, **kw})
    return CompositeOCR(FakeDetector(regions), FakeRecognizer(lines), cfg)


def region(x1, y1, x2, y2, kind="text_bubble") -> Detection:
    return Detection(bbox=(x1, y1, x2, y2), kind=kind, score=0.9)


def line(x1, y1, x2, y2, text="oi") -> TextLine:
    return TextLine(bbox=(x1, y1, x2, y2), text=text, confidence=0.9)


def test_reconhecedor_roda_uma_vez_na_imagem_inteira(image):
    """O caro é chamar o reconhecedor; por região custou 21.7s contra 1.95s."""
    recognizer = FakeRecognizer()
    cfg = DetectorConfig(fallback=False)
    CompositeOCR(FakeDetector([region(0, 0, 100, 100)]), recognizer, cfg).read(image)
    assert recognizer.calls == 1


def test_linha_dentro_da_regiao_recebe_o_region_id(image):
    out = composite([region(0, 0, 100, 100)], [line(10, 10, 50, 30)]).read(image)
    assert [ln.region_id for ln in out] == [0]


def test_linha_fora_de_qualquer_regiao_e_descartada(image):
    """É assim que o ruído de UI sai antes de virar bloco."""
    out = composite([region(0, 0, 100, 100)], [line(200, 150, 280, 180)]).read(image)
    assert out == []


def test_linha_vai_para_a_regiao_de_maior_sobreposicao(image):
    # A primeira pega só um pedaço da linha (x 60..80); a segunda a contém inteira.
    regions = [region(0, 0, 80, 100), region(40, 0, 300, 100)]
    out = composite(regions, [line(60, 10, 95, 30)]).read(image)
    assert out[0].region_id == 1


def test_linha_so_parcialmente_coberta_e_descartada(image):
    # Só 1/4 da linha entra na região; abaixo do min_line_overlap de 0.5.
    out = composite([region(0, 0, 20, 100)], [line(10, 10, 50, 30)]).read(image)
    assert out == []


def test_min_line_overlap_configuravel(image):
    out = composite([region(0, 0, 20, 100)], [line(10, 10, 50, 30)], min_line_overlap=0.2).read(
        image
    )
    assert [ln.region_id for ln in out] == [0]


def test_balao_sem_texto_nao_conta_como_regiao(image):
    """'bubble' é o desenho do balão; o texto dentro dele vem como 'text_bubble'."""
    out = composite([region(0, 0, 100, 100, kind="bubble")], [line(10, 10, 50, 30)]).read(image)
    assert out == []


def test_text_free_conta_como_regiao(image):
    out = composite([region(0, 0, 100, 100, kind="text_free")], [line(10, 10, 50, 30)]).read(image)
    assert len(out) == 1


def test_sem_regiao_o_reconhecedor_nem_e_chamado(image):
    recognizer = FakeRecognizer()
    assert CompositeOCR(FakeDetector([]), recognizer, DetectorConfig()).read(image) == []
    assert recognizer.calls == 0


def test_texto_e_confianca_sao_preservados(image):
    out = composite([region(0, 0, 100, 100)], [line(10, 10, 50, 30, "Hello")]).read(image)
    assert (out[0].text, out[0].confidence, out[0].bbox) == ("Hello", 0.9, (10, 10, 50, 30))


# -- segunda passada em mosaico ----------------------------------------------
# Em página real o DBNet perdeu um balão de uma palavra só e recortou mal uma linha
# curta (letra duplicada, 0.61); o
# reconhecedor acerta os dois quando recebe a região recortada com margem.


class ScriptedRecognizer:
    """Uma lista de linhas por chamada: a 1ª é a imagem cheia, a 2ª o mosaico."""

    def __init__(self, *calls: list[TextLine]) -> None:
        self._calls = list(calls)
        self.images: list[np.ndarray] = []

    def read(self, image):
        self.images.append(image)
        return self._calls.pop(0) if self._calls else []


def fallback_ocr(regions, *calls, **kw):
    recognizer = ScriptedRecognizer(*calls)
    return CompositeOCR(FakeDetector(regions), recognizer, DetectorConfig(**kw)), recognizer


def test_regiao_sem_linha_e_refeita_no_mosaico_e_volta_na_coordenada_original(image):
    # Região 100x40 em (100, 50); com margem 30 o recorte ocupa 160x100 no mosaico.
    ocr, recognizer = fallback_ocr(
        [region(100, 50, 200, 90)],
        [],
        [line(40, 40, 120, 60, "OK!")],
        fallback_pad=30,
    )
    out = ocr.read(image)
    assert len(recognizer.images) == 2
    assert recognizer.images[1].shape[:2] == (100, 160)
    assert [(ln.text, ln.bbox, ln.region_id) for ln in out] == [("OK!", (110, 60, 190, 80), 0)]


def test_mosaico_e_uma_chamada_so_para_varias_regioes(image):
    """Uma chamada por região custou 11x; o mosaico tem que ser uma chamada só."""
    regions = [region(20, 20, 80, 60), region(150, 100, 250, 140)]
    # Faixas no mosaico: [0, 100) e [120, 220). Uma linha em cada.
    ocr, recognizer = fallback_ocr(
        regions,
        [],
        [line(35, 40, 90, 60, "HI,"), line(35, 160, 130, 180, "OK!")],
        fallback_pad=30,
    )
    out = ocr.read(image)
    assert len(recognizer.images) == 2
    assert {ln.text: ln.region_id for ln in out} == {"HI,": 0, "OK!": 1}
    assert next(ln for ln in out if ln.text == "OK!").bbox == (155, 110, 250, 130)


def test_regiao_bem_lida_nao_e_refeita(image):
    good = TextLine(bbox=(30, 20, 70, 60), text="OK", confidence=0.95)
    ocr, recognizer = fallback_ocr([region(20, 20, 80, 60)], [good], fallback_confidence=0.8)
    assert [ln.text for ln in ocr.read(image)] == ["OK"]
    assert len(recognizer.images) == 1


def test_leitura_duvidosa_e_trocada_pela_do_mosaico(image):
    bad = TextLine(bbox=(30, 30, 70, 50), text="HHI", confidence=0.61)
    ocr, _ = fallback_ocr(
        [region(20, 20, 80, 60)], [bad], [line(35, 40, 90, 60, "HI,")], fallback_confidence=0.8
    )
    assert [ln.text for ln in ocr.read(image)] == ["HI,"]


def test_mosaico_vazio_mantem_a_primeira_leitura(image):
    bad = TextLine(bbox=(30, 30, 70, 50), text="HHI", confidence=0.61)
    ocr, _ = fallback_ocr([region(20, 20, 80, 60)], [bad], [])
    assert [ln.text for ln in ocr.read(image)] == ["HHI"]


def test_fallback_desligado_chama_o_reconhecedor_uma_vez(image):
    ocr, recognizer = fallback_ocr([region(20, 20, 80, 60)], [], [line(0, 0, 5, 5)], fallback=False)
    assert ocr.read(image) == []
    assert len(recognizer.images) == 1


# -- regiões duplicadas e balão cortado --------------------------------------


def test_duas_caixas_para_o_mesmo_balao_viram_uma(image):
    """Sem fundir, a mesma fala saía duas vezes."""
    regions = [region(20, 20, 120, 80), region(25, 22, 118, 85)]
    lines = [TextLine(bbox=(30, 30, 100, 50), text="WAIT A", confidence=0.95)]
    ocr, _ = fallback_ocr(regions, lines)
    assert {ln.region_id for ln in ocr.read(image)} == {0}


def test_merge_overlapping_nao_funde_baloes_vizinhos():
    from translatorocr.backends.ocr_composite import merge_overlapping

    # Encostados, com sobreposição pequena: são dois balões.
    regions = [region(0, 0, 100, 100), region(90, 0, 200, 100)]
    assert len(merge_overlapping(regions, 0.6)) == 2


def test_regiao_na_borda_da_captura_marca_as_linhas_como_parciais(image):
    # A imagem tem 300x200; a primeira região encosta embaixo.
    regions = [region(20, 20, 80, 60), region(100, 150, 200, 199)]
    lines = [
        TextLine(bbox=(30, 30, 70, 50), text="WHOLE", confidence=0.95),
        TextLine(bbox=(110, 160, 190, 190), text="CUT", confidence=0.95),
    ]
    ocr, _ = fallback_ocr(regions, lines)
    assert {ln.text: ln.partial for ln in ocr.read(image)} == {"WHOLE": False, "CUT": True}


def test_linha_perdida_e_detectada_pela_cobertura(image):
    """Balão de quatro linhas que perdeu a primeira: as outras tinham confiança 1.0."""
    kept = [TextLine(bbox=(30, 60, 110, 80), text="SECOND, PLEASE", confidence=1.0)]
    # No mosaico (margem 30): voltam como y 20..46 e 46..72, cobrindo 87% da região.
    full = [
        line(35, 30, 115, 56, "WAIT A"),
        line(35, 56, 115, 82, "SECOND, PLEASE"),
    ]
    # Região 20..80 de altura: a linha que sobrou cobre só 1/3 dela.
    ocr, recognizer = fallback_ocr([region(20, 20, 120, 80)], kept, full)
    assert [ln.text for ln in ocr.read(image)] == ["WAIT A", "SECOND, PLEASE"]
    assert len(recognizer.images) == 2


def test_segunda_passada_pior_nao_substitui_a_primeira(image):
    """A leitura do mosaico só entra se for melhor: cobrir a região, depois confiança."""
    first = [TextLine(bbox=(30, 20, 70, 60), text="~0o", confidence=0.6)]
    ocr, _ = fallback_ocr([region(20, 20, 80, 60)], first, [line(35, 35, 85, 50, "~000")])
    # A linha do mosaico volta como y 25..40: cobre só 3/8 da região.
    assert [ln.text for ln in ocr.read(image)] == ["~0o"]
