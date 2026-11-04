"""Orquestra os estágios. Sem nenhum import de Qt — o núcleo não conhece a UI.

capturar → upscale → OCR → agrupar → converter coordenadas → gate → traduzir

e, fora desse caminho, a segunda passada: `refine_next` retraduz um balão por vez com
as falas anteriores como contexto (ver `backends/translate_gemma.py`).
"""

from __future__ import annotations

import logging
import time
from collections import deque
from pathlib import Path

import cv2

from ..backends.base import CaptureBackend, OCRBackend, RefinerBackend, TranslatorBackend
from ..config import Config
from ..models import Capture, Region, TextBlock
from .collector import CaptureCollector
from .ledger import BlockLedger, Entry, Reading

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(
        self,
        config: Config,
        capture: CaptureBackend,
        ocr: OCRBackend,
        translator: TranslatorBackend,
        refiner: RefinerBackend | None = None,
        ledger: BlockLedger | None = None,
        collector: CaptureCollector | None = None,
    ) -> None:
        self._cfg = config
        self._capture = capture
        self._ocr = ocr
        self._translator = translator
        self._refiner = refiner
        self._ledger = ledger
        self._collector = collector
        # Balões à espera da segunda passada, em ordem de leitura. A fila guarda a
        # entrada do registro, e não o bloco: o bloco muda de posição na GUI e é
        # trocado por outro a cada leitura, a entrada é o que dura.
        self._refine_queue: deque[Entry] = deque()

    def _collect(
        self,
        shot: Capture,
        blocks: list[TextBlock],
        pending: list[TextBlock],
        reading: Reading | None,
    ) -> None:
        if self._collector is None:
            return
        context: dict[int, list[str]] = {}
        for block in pending:
            before = self._ledger.context(reading, block) if self._ledger and reading else []
            context[id(block)] = [entry.source for entry in before]
        self._collector.save(shot, blocks, context)

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

    def warmup(self, region: Region | None = None) -> None:
        """Roda o OCR uma vez, descartando o resultado, para a primeira captura de
        verdade não pagar a inicialização da GPU.

        Sem isto a primeira captura levava 4.2 s, contra ~0.5 s nas seguintes: é o
        cuDNN escolhendo algoritmo de convolução na primeira inferência. A escolha é
        por formato de entrada, então o aquecimento usa uma captura real da tela — uma
        imagem sintética de outro tamanho não adiantaria.
        """
        shot = self._grab(region)
        if shot is not None:
            self._ocr.read(shot.image)

    def run(self, region: Region | None = None) -> list[TextBlock]:
        from .gate import apply_gate
        from .grouping import group

        started = time.perf_counter()
        # O deslocamento do registro é o de antes da captura: as posições dos blocos
        # descrevem a tela como ela estava quando o quadro foi tirado.
        reading = self._ledger.begin() if self._ledger else None
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

        # O portão fica aqui, e não depois da tradução: o que ele descarta não chega a
        # gastar tradução, e falso positivo traduzido só produz lixo na tela.
        detected = len(blocks)
        blocks = apply_gate(blocks, self._cfg.gate, self._cfg.ocr.lang)

        # Balão já traduzido e lido inteiro volta do registro com a tradução que tinha;
        # só o que o registro não conhece (ou conhece incompleto) vai para o tradutor.
        pending = (
            self._ledger.reconcile(reading, blocks, shot.region)
            if self._ledger and reading
            else blocks
        )
        if pending:
            translations = self._translator.translate(
                [b.source for b in pending],
                self._cfg.translation.source_lang,
                self._cfg.translation.target_lang,
            )
            # strict=True: o contrato de TranslatorBackend é devolver uma entrada por
            # texto, preservando a ordem. Um backend que quebrasse isso truncaria em
            # silêncio e desalinharia tradução com bloco — melhor estourar.
            for block, translated in zip(pending, translations, strict=True):
                block.translated = translated
            if self._ledger and reading:
                self._queue_refine(self._ledger.record(reading, pending))
        t_translate = time.perf_counter()
        self._collect(shot, blocks, pending, reading)

        log.info(
            "pipeline: %d linhas → %d blocos (%d após o gate, %d traduzidos, %d do registro) | "
            "captura %.2fs · ocr %.2fs · tradução %.2fs",
            len(lines),
            detected,
            len(blocks),
            len(pending),
            len(blocks) - len(pending),
            t_capture - started,
            t_ocr - t_capture,
            t_translate - t_ocr,
        )
        if self._cfg.debug_dump:
            self._dump(shot, blocks)
        return blocks

    def _queue_refine(self, entries: list[Entry]) -> None:
        if self._refiner is None:
            return
        for entry in entries:
            words = len(entry.source.split())
            queued = any(e is entry for e in self._refine_queue)
            if words >= self._cfg.refine.min_words and not queued:
                self._refine_queue.append(entry)

    @property
    def refining(self) -> bool:
        """Há balão esperando a segunda passada."""
        return bool(self._refine_queue)

    def refine_next(self) -> bool:
        """Retraduz o próximo balão da fila com as falas anteriores como contexto.

        Um balão por chamada, para quem chama poder intercalar uma captura entre um e
        outro. A tradução nova vai para o registro, de onde a tela a busca
        (`BlockLedger.refresh`). Devolve se ela mudou.
        """
        if self._refiner is None or self._ledger is None:
            return False
        while self._refine_queue:
            entry = self._refine_queue.popleft()
            history = self._ledger.history(entry)
            if history is None:
                continue
            started = time.perf_counter()
            pairs = [(e.source, e.translated) for e in history if e.translated]
            text = self._refiner.translate(entry.source, pairs)
            log.info(
                "segunda passada: 1 balão em %.2fs, %d de contexto, %d na fila",
                time.perf_counter() - started,
                len(pairs),
                len(self._refine_queue),
            )
            if not text or text == entry.translated:
                return False
            self._ledger.revise(entry, text)
            return True
        return False
