"""Registro de balões: o que já foi lido e traduzido na tira que o usuário percorre.

Puro, sem Qt e sem GPU, no estilo de `tracker.py`. O `tracker` responde "onde está na
tela o que eu já desenhei"; o registro responde "o que eu já li desta página", inclusive
o que saiu da tela.

**Posição na tira.** Cada balão guarda o y que teria se a página estivesse na rolagem
zero: y da tela menos o deslocamento acumulado. Dois balões de leituras diferentes são o
mesmo quando a posição na tira coincide, não quando o texto coincide — o OCR lê o mesmo
balão de jeitos diferentes, e é a posição que sobrevive a isso.

**Trecho.** A posição na tira só vale enquanto o rastreio acompanha a rolagem. Quando ele
se perde (`lost`: zoom, rolagem rápida, troca de página) as posições deixam de ser
comparáveis, e as leituras seguintes abrem um trecho novo. Se um balão lido agora tem o
mesmo texto de um já registrado, o trecho antigo é reaproveitado com o novo deslocamento.

**Contexto não é posição.** O contexto de tradução são os balões anteriores em ordem de
leitura, e atravessa os trechos. Ele recomeça junto com o registro inteiro quando o
título da janela em primeiro plano muda (outro capítulo) ou quando passa muito tempo sem
leitura.

Duas threads tocam isto: a GUI (rolagem, `lost`, título) e o worker (leitura). Todo
método público segura o mesmo lock.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from ..config import LedgerConfig, ScrollConfig
from ..geometry import overlap_fraction
from ..models import BBox, Region, TextBlock
from .tracker import is_partial

# Folga, em pixels, para dois deslocamentos contarem como o mesmo ao reancorar um trecho.
_ANCHOR_TOLERANCE = 8


def _same_text(a: str, b: str) -> bool:
    return " ".join(a.split()).casefold() == " ".join(b.split()).casefold()


@dataclass
class Entry:
    """Um balão registrado. `bbox` está na tira do trecho a que ele pertence."""

    bbox: BBox
    source: str
    translated: str | None
    confidence: float
    partial: bool
    needs_review: bool


@dataclass
class Segment:
    """Trecho contínuo da tira. `base` leva o y de tela de agora para a tira dele."""

    base: int = 0
    entries: list[Entry] = field(default_factory=list)
    # Carimbo do último uso, para ordenar trechos por tempo.
    used: int = 0


@dataclass
class Reading:
    """Uma rodada do pipeline: o deslocamento e a geração de quando ela começou, mais o
    que `reconcile` decidiu e `record` precisa saber."""

    offset: int
    generation: int
    segment: Segment | None = None
    # Entrada que a leitura de cada bloco pendente substitui (chave: `id(block)`).
    replaces: dict[int, Entry] = field(default_factory=dict)


def _reusable(entry: Entry, block: TextBlock) -> bool:
    """A tradução guardada vale para este bloco lido de novo.

    A primeira leitura inteira fica: relida com letra diferente, ela continua valendo.
    Cedem à leitura nova a entrada cortada pela borda (o texto dela estava incompleto) e
    a entrada duvidosa diante de uma leitura limpa.
    """
    if entry.translated is None:
        return False
    if _same_text(entry.source, block.source):
        return True
    if entry.partial:
        return False
    return not (entry.needs_review and not block.needs_review)


class BlockLedger:
    def __init__(
        self,
        cfg: LedgerConfig,
        scroll: ScrollConfig,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cfg = cfg
        self._overlap = scroll.merge_overlap
        self._clock = clock
        self._lock = threading.Lock()
        self._offset = 0
        # Sobe a cada `lost` e a cada recomeço: uma leitura iniciada numa geração e
        # concluída em outra descreve uma tela cujas posições não valem mais.
        self._generation = 0
        self._segments: list[Segment] = []
        self._current: Segment | None = None
        self._title: str | None = None
        self._last_read: float | None = None
        self._stamp = 0

    # -- eventos que vêm da GUI ---------------------------------------------

    def scrolled(self, dy: int) -> None:
        with self._lock:
            self._offset += dy

    def lost(self) -> None:
        """O rastreio se perdeu: as posições atuais não são comparáveis às anteriores."""
        with self._lock:
            self._current = None
            self._generation += 1

    def observe_title(self, title: str) -> None:
        """Título da janela em primeiro plano. Título novo é outro capítulo."""
        if not title:
            return
        with self._lock:
            if self._title is not None and title != self._title:
                self._restart()
            self._title = title

    # -- leitura (worker) ----------------------------------------------------

    def begin(self) -> Reading:
        with self._lock:
            now = self._clock()
            if self._last_read is not None and now - self._last_read >= self._cfg.idle_seconds:
                self._restart()
            self._last_read = now
            return Reading(offset=self._offset, generation=self._generation)

    def reconcile(self, reading: Reading, blocks: list[TextBlock]) -> list[TextBlock]:
        """Casa cada bloco lido com o registro por posição.

        O bloco casado cuja tradução vale (`_reusable`) herda o texto e a tradução
        guardados e sai da lista. Devolve só os blocos que ainda precisam de tradução.
        """
        with self._lock:
            if reading.generation != self._generation:
                return list(blocks)

            segment = self._current or self._anchor(reading, blocks)
            reading.segment = segment
            segment.used = self._tick()

            pending: list[TextBlock] = []
            for block in blocks:
                strip = self._to_strip(block.bbox, reading.offset, segment)
                entry = self._match(segment, strip)
                if entry is None:
                    pending.append(block)
                    continue
                if not _reusable(entry, block):
                    reading.replaces[id(block)] = entry
                    pending.append(block)
                    continue
                block.source = entry.source
                block.translated = entry.translated
                block.needs_review = entry.needs_review
                if entry.partial and not is_partial(block):
                    entry.bbox = strip
                    entry.partial = False
            return pending

    def record(self, reading: Reading, pending: list[TextBlock]) -> None:
        """Guarda os blocos que acabaram de ser traduzidos."""
        with self._lock:
            segment = reading.segment
            if reading.generation != self._generation or segment is None:
                return
            for block in pending:
                strip = self._to_strip(block.bbox, reading.offset, segment)
                entry = reading.replaces.get(id(block))
                if entry is None:
                    entry = Entry(strip, block.source, None, block.confidence, False, False)
                    segment.entries.append(entry)
                entry.bbox = strip
                entry.source = block.source
                entry.translated = block.translated
                entry.confidence = block.confidence
                entry.partial = is_partial(block)
                entry.needs_review = block.needs_review

    def context(self, reading: Reading, block: TextBlock, limit: int | None = None) -> list[Entry]:
        """Os balões anteriores a `block`, em ordem de leitura.

        Primeiro os trechos mais antigos, cada um de cima para baixo; por último, no
        trecho do próprio bloco, o que está acima dele. Devolve os últimos `limit`.
        """
        with self._lock:
            current = reading.segment
            ordered = sorted((s for s in self._segments if s is not current), key=lambda s: s.used)
            before: list[Entry] = []
            for segment in ordered:
                before.extend(_reading_order(segment.entries))
            if current is not None:
                top = self._to_strip(block.bbox, reading.offset, current)[1]
                before.extend(_reading_order([e for e in current.entries if e.bbox[1] < top]))
            return before[-(limit or self._cfg.context_size) :]

    # -- redesenho (GUI) -----------------------------------------------------

    def restore(self, region: Region, shown: list[TextBlock]) -> list[TextBlock]:
        """Balões registrados que estão na viewport e ainda não estão desenhados.

        É o que redesenha a tira ao rolar de volta, sem OCR. Entrada cortada pela borda
        fica de fora: o texto dela estava incompleto, e a leitura seguinte a refaz.
        """
        with self._lock:
            segment = self._current
            if segment is None:
                return []
            restored: list[TextBlock] = []
            for entry in segment.entries:
                if entry.partial or entry.translated is None:
                    continue
                x1, y1, x2, y2 = entry.bbox
                bbox = (x1, y1 + self._offset - segment.base, x2, y2 + self._offset - segment.base)
                if bbox[3] <= region.top or bbox[1] >= region.bottom:
                    continue
                if any(overlap_fraction(bbox, s.bbox) >= self._overlap for s in shown):
                    continue
                restored.append(
                    TextBlock(
                        bbox=bbox,
                        source=entry.source,
                        confidence=entry.confidence,
                        translated=entry.translated,
                        needs_review=entry.needs_review,
                    )
                )
            return restored

    # -- internos (já com o lock) --------------------------------------------

    def _tick(self) -> int:
        self._stamp += 1
        return self._stamp

    def _restart(self) -> None:
        self._segments = []
        self._current = None
        self._generation += 1

    @staticmethod
    def _to_strip(bbox: BBox, offset: int, segment: Segment) -> BBox:
        shift = segment.base - offset
        return (bbox[0], bbox[1] + shift, bbox[2], bbox[3] + shift)

    def _match(self, segment: Segment, strip: BBox) -> Entry | None:
        best, best_overlap = None, self._overlap
        for entry in segment.entries:
            score = overlap_fraction(entry.bbox, strip)
            if score >= best_overlap:
                best, best_overlap = entry, score
        return best

    def _anchor(self, reading: Reading, blocks: list[TextBlock]) -> Segment:
        """Trecho para as posições desta leitura: um antigo reancorado, ou um novo.

        Reancora quando balões lidos agora têm o mesmo texto de balões de um trecho
        registrado, todos no mesmo deslocamento — ou um só, se o texto for longo o
        bastante para não ser coincidência.
        """
        best: tuple[int, int, Segment, int] | None = None
        for segment in self._segments:
            pairs = [
                (entry.bbox[1] - (block.bbox[1] - reading.offset), len(block.source))
                for block in blocks
                for entry in segment.entries
                if _same_text(entry.source, block.source)
            ]
            for delta, _ in pairs:
                agreeing = [chars for d, chars in pairs if abs(d - delta) <= _ANCHOR_TOLERANCE]
                if len(agreeing) < 2 and max(agreeing) < self._cfg.reanchor_min_chars:
                    continue
                candidate = (len(agreeing), segment.used, segment, delta)
                if best is None or candidate[:2] > best[:2]:
                    best = candidate

        if best is None:
            segment = Segment()
            self._segments.append(segment)
        else:
            _, _, segment, delta = best
            segment.base = delta
        self._current = segment
        return segment


def _reading_order(entries: list[Entry]) -> list[Entry]:
    return sorted(entries, key=lambda e: (e.bbox[1], e.bbox[0]))
