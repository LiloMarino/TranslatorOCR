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
    return CompositeOCR(FakeDetector(regions), FakeRecognizer(lines), DetectorConfig(**kw))


def region(x1, y1, x2, y2, kind="text_bubble") -> Detection:
    return Detection(bbox=(x1, y1, x2, y2), kind=kind, score=0.9)


def line(x1, y1, x2, y2, text="oi") -> TextLine:
    return TextLine(bbox=(x1, y1, x2, y2), text=text, confidence=0.9)


def test_reconhecedor_roda_uma_vez_na_imagem_inteira(image):
    """O caro é chamar o reconhecedor; por região custou 21.7s contra 1.95s."""
    recognizer = FakeRecognizer()
    CompositeOCR(FakeDetector([region(0, 0, 100, 100)]), recognizer, DetectorConfig()).read(image)
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
