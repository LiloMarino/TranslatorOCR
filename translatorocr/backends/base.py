"""Protocolos dos estágios plugáveis.

Três backends principais (Capture, OCR, Translator) mais LLM opcional e DetectorBackend
para reconhecimento de regiões de texto/balão. DetectorBackend não é um estágio
independente do pipeline — é consumido pela CompositeOCR que combina detector e
reconhecedor sob um único OCRBackend.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

from ..models import Capture, Detection, Region, TextBlock, TextLine


@runtime_checkable
class CaptureBackend(Protocol):
    def grab(self, region: Region | None = None) -> Capture | None:
        """Captura a região. Devolve `None` quando não há frame novo."""
        ...

    def monitor_region(self) -> Region:
        """A região do monitor configurado, em pixels físicos do desktop."""
        ...

    def close(self) -> None: ...


@runtime_checkable
class DetectorBackend(Protocol):
    def detect(self, image: np.ndarray) -> list[Detection]:
        """Acha regiões de texto/balão. Os bboxes saem no espaço da imagem recebida."""
        ...


@runtime_checkable
class OCRBackend(Protocol):
    def read(self, image: np.ndarray) -> list[TextLine]:
        """Detecta e reconhece. Os bboxes saem no espaço da imagem recebida."""
        ...


@runtime_checkable
class TranslatorBackend(Protocol):
    def translate(self, texts: list[str], source: str, target: str) -> list[str | None]:
        """Traduz em lote, preservando a ordem.

        Recebe lista em vez de string para permitir otimizações futuras (ex: mandar
        a página inteira numa chamada). Uma entrada que falhou volta como `None` —
        a falha é por item e nunca derruba o lote inteiro.
        """
        ...


@runtime_checkable
class LLMBackend(Protocol):
    def refine(self, blocks: list[TextBlock]) -> list[str | None]:
        """Corrige OCR e traduz num só passo, só para os blocos que o gate marcou
        `needs_review`. Chamado à parte por `Pipeline.refine` após a tradução rápida
        já estar sendo exibida. `None` mantém a tradução provisória; o refino nunca
        regride para pior.
        """
        ...
