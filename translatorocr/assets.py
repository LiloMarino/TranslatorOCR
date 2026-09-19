"""Os pesos que não vêm por pip: onde moram e como chegam.

Os modelos do RapidOCR não estão aqui — o próprio pacote os busca no primeiro uso. Estes
não têm esse mecanismo, então o app baixa sozinho o que faltar na inicialização
(`ensure`), e `scripts/fetch_models.py` continua existindo para baixar à mão ou forçar.

Os caminhos são constantes e não configuração de propósito: cada backend está amarrado
ao seu modelo (o NMT ao par en→pt e ao token `>>pob<<`, o detector às três classes do
RT-DETR), então apontar para outro arquivo não funcionaria sem mudar código.

Só stdlib — o download não adiciona dependência ao projeto.
"""

from __future__ import annotations

import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"

HF = "https://huggingface.co/{repo}/resolve/main/{path}"


@dataclass(frozen=True)
class Asset:
    repo: str
    remote: str
    local: str
    size: int  # bytes exatos, conferidos contra a API do HF

    @property
    def url(self) -> str:
        return HF.format(repo=self.repo, path=self.remote)

    @property
    def path(self) -> Path:
        return MODELS_DIR / self.local

    def present(self) -> bool:
        return self.path.is_file() and self.path.stat().st_size == self.size


# Detector de balão. Apache-2.0. RT-DETR-v2 com o pós-processamento embutido no
# grafo: as saídas já saem em coordenada da imagem original.
#
# Escolhido no lugar do comic-text-detector, que é GPL-3.0, tem entrada de shape fixo
# e cujas 3 classes são idioma (eng/ja/unknown), não balão. Este devolve
# bubble/text_bubble/text_free, que é o que o agrupamento precisa.
#
# Se a VRAM apertar com as duas sessões ONNX abertas, o mesmo repo tem
# `detector_int8.onnx` (43.838.857 B) e `detector-v4-s_int8.onnx` (11.120.765 B).
DETECTOR = [
    Asset(
        repo="ogkalu/comic-text-and-bubble-detector",
        remote="detector.onnx",
        local="comic-bubble-detector.onnx",
        size=168_481_531,
    ),
]

# NMT local en→pt (tier 1). Modelo já convertido para CTranslate2 — não há passo de
# conversão, e `compute_type="int8"` requantiza no load.
#
# O modelo upstream é Helsinki-NLP/opus-mt-tc-big-en-pt, CC-BY-4.0. O repo do mirror
# está tagueado apache-2.0, o que contradiz o upstream; vale a licença do upstream.
NMT = [
    Asset("ooeoeo/opus-mt-tc-big-en-pt-ct2-float16", f, f"opus-mt-en-pt-ct2/{f}", size)
    for f, size in [
        ("model.bin", 467_111_989),
        ("source.spm", 802_741),
        ("target.spm", 824_855),
        ("shared_vocabulary.json", 1_008_431),
        ("config.json", 223),
    ]
]

# Tier de LLM local, desligado por padrão (ver `config.LLMConfig`) e por isso fora do
# download automático. Requer `uv sync --group llm` antes de ser ligado.
LLM = [
    Asset(
        repo="Qwen/Qwen3-4B-GGUF",
        remote="Qwen3-4B-Q4_K_M.gguf",
        local="Qwen3-4B-Q4_K_M.gguf",
        size=2_497_280_256,
    ),
]

GROUPS = {"detector": DETECTOR, "nmt": NMT, "llm": LLM}

# O que cada backend abre. Derivado das listas acima para as duas não divergirem.
DETECTOR_PATH = DETECTOR[0].path
NMT_DIR = NMT[0].path.parent
LLM_PATH = LLM[0].path

# Nome legível de cada grupo, para o progresso na primeira execução.
LABELS = {"detector": "detector de balão", "nmt": "tradutor offline", "llm": "LLM local"}

# (feito, total, bytes/s) — chamado a cada pedaço baixado.
Progress = Callable[[int, int, float], None]


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def download(asset: Asset, progress: Progress | None = None) -> None:
    """Baixa um asset, levantando `OSError` se falhar ou vier com tamanho errado."""
    target = asset.path
    target.parent.mkdir(parents=True, exist_ok=True)
    # Escreve em .part e só renomeia no fim: um download interrompido não deixa para
    # trás um arquivo truncado que a checagem de tamanho depois trataria como válido.
    partial = target.with_suffix(target.suffix + ".part")
    started = time.perf_counter()
    try:
        request = urllib.request.Request(asset.url, headers={"User-Agent": "translatorocr"})
        with urllib.request.urlopen(request) as response, partial.open("wb") as fh:
            total = int(response.headers.get("Content-Length") or asset.size)
            done = 0
            while chunk := response.read(1 << 20):
                fh.write(chunk)
                done += len(chunk)
                if progress is not None:
                    elapsed = time.perf_counter() - started
                    progress(done, total, done / elapsed if elapsed > 0 else 0.0)
    except (urllib.error.URLError, OSError):
        partial.unlink(missing_ok=True)
        raise

    actual = partial.stat().st_size
    if actual != asset.size:
        partial.unlink(missing_ok=True)
        raise OSError(
            f"{asset.local}: {actual} bytes, esperava {asset.size}. "
            "O modelo pode ter sido republicado."
        )
    partial.replace(target)


def missing(groups: list[str]) -> list[tuple[str, Asset]]:
    return [(g, a) for g in groups for a in GROUPS[g] if not a.present()]


def ensure(
    groups: list[str],
    on_start: Callable[[str, Asset], None] | None = None,
    progress: Progress | None = None,
) -> list[str]:
    """Baixa o que faltar dos grupos pedidos; devolve os grupos que falharam.

    Não levanta: um grupo que não veio (sem rede) é tratado mais adiante pelo
    `registry`, que já sabe seguir sem o detector ou cair para a nuvem, com aviso.
    """
    failed: list[str] = []
    for group, asset in missing(groups):
        if group in failed:
            continue
        if on_start is not None:
            on_start(group, asset)
        try:
            download(asset, progress)
        except (urllib.error.URLError, OSError) as exc:
            log.warning("Download de %s falhou: %s", asset.local, exc)
            failed.append(group)
    return failed
