"""Orquestra os estágios. Sem nenhum import de Qt — o núcleo não conhece a UI.

capturar → upscale → OCR → agrupar → converter coordenadas → gate → traduzir
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import cv2

from ..backends.base import CaptureBackend, LLMBackend, OCRBackend, TranslatorBackend
from ..config import Config
from ..models import Capture, Region, TextBlock

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(
        self,
        config: Config,
        capture: CaptureBackend,
        ocr: OCRBackend,
        translator: TranslatorBackend,
        llm: LLMBackend | None = None,
    ) -> None:
        self._cfg = config
        self._capture = capture
        self._ocr = ocr
        self._translator = translator
        self._llm = llm

    def _grab(self, region: Region | None) -> Capture | None:
        shot = self._capture.grab(region)
        if shot is None:
            return None

        factor = self._cfg.capture.upscale
        if factor and factor != 1.0:
            # Nota: para o upscale ter algum efeito real, `ocr.max_side_len` precisa
            # subir junto — senão o RapidOCR reescala a imagem de volta para baixo e
            # o trabalho é jogado fora. Medição de 2026-09 não mostrou ganho de
            # acurácia, por isso o default é 1.0.
            image = cv2.resize(
                shot.image, None, fx=factor, fy=factor, interpolation=cv2.INTER_LANCZOS4
            )
            shot = Capture(image=image, origin=shot.origin, scale=factor)
        return shot

    def _dump(self, shot: Capture, blocks: list[TextBlock]) -> None:
        """Salva a captura com os bboxes desenhados por cima.

        Ferramenta para diagnosticar erros de conversão de coordenadas: se as caixas
        não caem em cima do texto na imagem salva, a conversão está errada.
        """
        image = shot.image.copy()
        ox, oy = shot.origin
        for block in blocks:
            x1, y1, x2, y2 = block.bbox
            pt1 = (int((x1 - ox) * shot.scale), int((y1 - oy) * shot.scale))
            pt2 = (int((x2 - ox) * shot.scale), int((y2 - oy) * shot.scale))
            cv2.rectangle(image, pt1, pt2, (0, 0, 255), 2)
        path = Path(f"debug_dump_{int(time.time())}.png")
        cv2.imwrite(str(path), image)
        log.info("Debug dump salvo em %s", path.resolve())

    def run(self, region: Region | None = None) -> list[TextBlock]:
        from .gate import apply_gate
        from .grouping import group

        started = time.perf_counter()
        shot = self._grab(region)
        if shot is None:
            return []
        t_capture = time.perf_counter()

        lines = self._ocr.read(shot.image)
        t_ocr = time.perf_counter()

        blocks = group(lines, self._cfg.grouping)
        # A partir daqui todo bbox está em pixels físicos do desktop.
        for block in blocks:
            block.bbox = shot.to_desktop(block.bbox)

        # O portão fica aqui, e não depois da tradução, porque descartar antes evita
        # pagar rede por reconhecimento falho — traduzir falsos positivos poderia
        # produzir output corrompido ou inútil.
        detected = len(blocks)
        blocks = apply_gate(blocks, self._cfg.gate, self._cfg.ocr.lang)

        if blocks:
            translations = self._translator.translate(
                [b.source for b in blocks],
                self._cfg.translation.source_lang,
                self._cfg.translation.target_lang,
            )
            # strict=True: o contrato de TranslatorBackend é devolver uma entrada por
            # texto, preservando a ordem. Um backend que quebrasse isso truncaria em
            # silêncio e desalinharia tradução com bloco — melhor estourar.
            for block, translated in zip(blocks, translations, strict=True):
                block.translated = translated
        t_translate = time.perf_counter()

        log.info(
            "pipeline: %d linhas → %d blocos (%d após o gate) | "
            "captura %.2fs · ocr %.2fs · tradução %.2fs",
            len(lines),
            detected,
            len(blocks),
            t_capture - started,
            t_ocr - t_capture,
            t_translate - t_ocr,
        )
        if self._cfg.debug_dump:
            self._dump(shot, blocks)
        return blocks

    def refine(self, blocks: list[TextBlock]) -> list[TextBlock]:
        """Segunda passada: corrige OCR + traduz de novo só os blocos duvidosos.

        Chamado à parte de `run()`, depois que a tradução rápida (nmt/cloud) já foi
        mostrada — fica fora do caminho crítico de latência. Devolve só os blocos que
        de fato mudaram, para o chamador atualizar o overlay in-place sem tocar no
        resto.
        """
        if self._llm is None:
            return []
        # Blocos de uma palavra só (onomatopeia, número de página) não têm contexto
        # suficiente para correção confiável de LLM — melhor deixar a tradução rápida
        # que já funciona bem. Blocos maiores ganham da passada de refino.
        pending = [b for b in blocks if b.needs_review and len(b.source.split()) > 1]
        if not pending:
            return []

        started = time.perf_counter()
        refined = self._llm.refine(pending)
        changed = []
        for block, text in zip(pending, refined, strict=True):
            if text:
                block.translated = text
                changed.append(block)
        log.info(
            "refino LLM: %d/%d blocos atualizados em %.2fs",
            len(changed),
            len(pending),
            time.perf_counter() - started,
        )
        return changed
