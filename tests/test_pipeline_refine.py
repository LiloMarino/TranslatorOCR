"""`Pipeline.refine` — segunda passada de LLM, só nos blocos `needs_review`.

Sem OCR/captura real: exercita só a lógica de filtro e de merge do refino, com um
LLM dublê. Garante que o pipeline não manda todo bloco pro LLM (apenas os com
`needs_review=True`), evitando desperdício de latência, e que `None` não
sobrescreve a tradução provisória.
"""

from __future__ import annotations

from translatorocr.config import Config
from translatorocr.core.pipeline import Pipeline
from translatorocr.models import TextBlock


class FakeLLM:
    def __init__(self, mapping: dict[str, str | None]) -> None:
        self.mapping = mapping
        self.seen: list[str] = []

    def refine(self, blocks: list[TextBlock]) -> list[str | None]:
        self.seen = [b.source for b in blocks]
        return [self.mapping.get(b.source) for b in blocks]


def make_block(source: str, needs_review: bool, translated: str = "provisório") -> TextBlock:
    return TextBlock(
        bbox=(0, 0, 10, 10),
        source=source,
        confidence=0.5,
        needs_review=needs_review,
        translated=translated,
    )


def make_pipeline(llm) -> Pipeline:
    # Só `refine()` é exercitado; capture/ocr/translator não importam aqui.
    return Pipeline(Config(), capture=None, ocr=None, translator=None, llm=llm)  # type: ignore[arg-type]


def test_sem_llm_configurado_devolve_vazio():
    pipeline = make_pipeline(None)
    blocks = [make_block("a", needs_review=True)]
    assert pipeline.refine(blocks) == []


def test_so_blocos_needs_review_vao_ao_llm():
    llm = FakeLLM({"texto duvidoso": "corrigido"})
    pipeline = make_pipeline(llm)
    blocks = [make_block("ok", needs_review=False), make_block("texto duvidoso", needs_review=True)]

    pipeline.refine(blocks)
    assert llm.seen == ["texto duvidoso"]


def test_bloco_atualizado_aparece_no_resultado():
    llm = FakeLLM({"texto duvidoso": "corrigido"})
    pipeline = make_pipeline(llm)
    block = make_block("texto duvidoso", needs_review=True)

    changed = pipeline.refine([block])
    assert changed == [block]
    assert block.translated == "corrigido"


def test_none_do_llm_mantem_traducao_provisoria():
    llm = FakeLLM({"texto duvidoso": None})
    pipeline = make_pipeline(llm)
    block = make_block("texto duvidoso", needs_review=True, translated="provisório")

    changed = pipeline.refine([block])
    assert changed == []
    assert block.translated == "provisório"


def test_sem_blocos_needs_review_nao_chama_o_llm():
    llm = FakeLLM({})
    pipeline = make_pipeline(llm)
    pipeline.refine([make_block("a", needs_review=False)])
    assert llm.seen == []


def test_bloco_de_uma_palavra_nao_vai_ao_llm():
    """O LLM pode ecoar a tradução anterior quando não há o que traduzir de verdade
    (onomatopeia, número de página). É mais barato e mais seguro não chamar."""
    llm = FakeLLM({"THUD": "não deveria aparecer"})
    pipeline = make_pipeline(llm)
    pipeline.refine([make_block("THUD", needs_review=True)])
    assert llm.seen == []
