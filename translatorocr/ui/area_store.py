"""A área de captura escolhida, guardada entre sessões.

Arquivo ausente, ilegível ou com área fora da tela atual vale como "sem área": a captura
cai na tela cheia. A área é restaurada só na tela que a contém, e o arquivo sobrevive a
uma abertura em outro monitor.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path

from ..models import Region

log = logging.getLogger(__name__)


def _inside(region: Region, screen: Region) -> bool:
    return (
        region.width > 0
        and region.height > 0
        and screen.left <= region.left
        and screen.top <= region.top
        and region.right <= screen.right
        and region.bottom <= screen.bottom
    )


def load_area(path: Path, screen: Region) -> Region | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        region = Region(int(raw["left"]), int(raw["top"]), int(raw["width"]), int(raw["height"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return region if _inside(region, screen) else None


def save_area(path: Path, region: Region | None) -> None:
    """`None` apaga o que estava guardado. Falha de disco fica em aviso: a área continua
    valendo nesta sessão."""
    try:
        if region is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(json.dumps(asdict(region)) + "\n", encoding="utf-8")
    except OSError as exc:
        log.warning("Área selecionada não gravada: %s", exc)
