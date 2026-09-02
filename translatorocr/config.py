"""Configuração do app.

Todos os campos têm default embutido, então `config.toml` é opcional — o app roda
sem nenhum arquivo de configuração. Existir um arquivo só sobrescreve o que ele
declara.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

CONFIG_FILENAME = "config.toml"


@dataclass
class CaptureConfig:
    backend: str = "mss"
    # Índice de monitor no padrão do mss: 0 = desktop virtual inteiro, 1 = primário.
    monitor: int = 1
    # Fator de upscale antes do OCR. Medido em 2026-09: com PP-OCRv5 o upscale não
    # melhora acurácia (o recognizer já normaliza os crops para 48px de altura) e,
    # para valer de fato, exigiria subir `ocr.max_side_len` junto — o que custou 17x
    # mais tempo pelo mesmo resultado. Fica como knob, desligado por padrão.
    upscale: float = 1.0


@dataclass
class OCRConfig:
    backend: str = "rapidocr"
    use_gpu: bool = True
    # Falha alto se use_gpu foi pedido e o provider efetivo veio CPU. Sem isso o ORT
    # cai em CPU silenciosamente — a mesma classe de falha do torch+cpu que passou
    # despercebida na versão antiga.
    strict_gpu: bool = True
    lang: str = "en"
    model_type: str = "mobile"
    ocr_version: str = "PP-OCRv5"
    max_side_len: int = 2000
    text_score: float = 0.5


@dataclass
class GroupingConfig:
    # Duas linhas entram no mesmo bloco se o gap vertical entre elas for menor que
    # `line_gap_ratio` x altura mediana da linha, e se a sobreposição horizontal for
    # de pelo menos `min_h_overlap` da largura da mais estreita.
    line_gap_ratio: float = 1.0
    min_h_overlap: float = 0.35
    # Freio contra encadeamento transitivo: sem isso, uma coluna de linhas alinhadas
    # e igualmente espaçadas — uma sidebar de IDE, um índice — funde tudo num bloco
    # só, porque cada linha casa com a anterior. Um balão de fala raramente passa
    # de 8 linhas.
    max_lines_per_block: int = 8
    reading_order: str = "ltr"  # "ltr" | "rtl" — inverte o sentido horizontal da ordem de leitura
    # Banda de tolerância vertical, em fração da altura do bloco, para considerar
    # dois blocos como estando "na mesma linha" ao ordenar.
    row_band_ratio: float = 0.6


@dataclass
class DetectorConfig:
    """Detector de balão (RT-DETR-v2, Apache-2.0), rodando antes do reconhecedor.

    Desligar faz o reconhecedor voltar a rodar na imagem inteira, que é o comportamento
    do v1 — útil para comparar, e o fallback quando o modelo não foi baixado.
    """

    enabled: bool = True
    model_path: str = "models/comic-bubble-detector.onnx"
    use_gpu: bool = True
    strict_gpu: bool = True
    # O modelo foi treinado em 640x640 e o preprocessor dele não preserva aspecto.
    # Mudar isto sem re-treinar degrada a detecção.
    input_size: int = 640
    score_threshold: float = 0.3
    # Fração da linha que precisa cair dentro de uma região para ser atribuída a ela.
    # Linha que não alcança isso em nenhuma região é descartada — é assim que a UI sai.
    min_line_overlap: float = 0.5


@dataclass
class GateConfig:
    """Portão entre reconhecimento e tradução."""

    enabled: bool = True
    # Abaixo disto o bloco é marcado `needs_review` e desenhado com borda distinta.
    min_confidence: float = 0.6
    # Abaixo disto é descartado: não paga tradução e não vai para a tela.
    drop_below: float = 0.35
    max_symbol_ratio: float = 0.5
    min_chars: int = 2


@dataclass
class TranslationConfig:
    backend: str = "cloud"
    source_lang: str = "auto"
    target_lang: str = "pt"
    cache_path: str = "cache.sqlite"
    max_retries: int = 3
    backoff_base: float = 0.4
    timeout: float = 10.0
    # Tradução é I/O de rede, então paralelizar tem ganho quase linear. Medido: uma
    # tela cheia com 82 blocos levava 64s em série, 11s com 8 workers. Mas 8 já
    # provocou rate limit numa tela com 55 blocos, então o default é 4 — a rajada
    # importa mais que o volume para este endpoint.
    max_workers: int = 4
    # Ordem dos tiers. Cada um só recebe o que o anterior não conseguiu traduzir, o que
    # reusa a semântica de falha-por-item que TranslatorBackend já contratualiza.
    # `backend` acima continua valendo como atalho de um tier só.
    tiers: list[str] = field(default_factory=lambda: ["nmt", "cloud"])
    nmt_model_path: str = "models/opus-mt-en-pt-ct2"
    # CPU de propósito: o ctranslate2 carrega `cublas64_12.dll` por nome e este venv tem
    # CUDA 13 (veio do onnxruntime-gpu). Ligar a GPU aqui exigiria o wheel
    # nvidia-cublas-cu12 de ~553 MB mais um os.add_dll_directory manual, para disputar
    # VRAM com o OCR. Em CPU a tradução ainda roda em paralelo com a inferência de GPU.
    nmt_compute_type: str = "int8"
    # Medido nesta máquina com 50 balões: beam 1 = 0.55s, beam 2 = 0.82s, beam 4 =
    # 1.27s (int8). Contra os 11.4s da nuvem, beam 2 sai de graça e traduz melhor.
    nmt_beam_size: int = 2
    # O opus-mt-tc-big-en-pt é multi-alvo e exige token inicial de idioma:
    # `>>pob<<` para português brasileiro, `>>por<<` para o europeu.
    nmt_lang_token: str = ">>pob<<"
    nmt_threads: int = 0  # 0 deixa o ctranslate2 decidir


@dataclass
class LLMConfig:
    """Refino por LLM local, só nos blocos que o gate marcou `needs_review`
    (ver `backends/translate_llm.py`).

    Modelo: Qwen3-4B-Q4_K_M, escolhido por benchmark (`scripts/benchmark_llm.py`)
    contra o Qwen3-8B — qualidade equivalente em frases reais, mas ~3x mais rápido por
    bloco e com bem mais folga de VRAM.
    """

    enabled: bool = True
    model_path: str = "models/Qwen3-4B-Q4_K_M.gguf"
    # -1 = offload total pra GPU. Testado com OCR+detector já carregados: 5.1GB de
    # pico numa placa de 6GB — reduza se um modelo de detector maior entrar depois.
    n_gpu_layers: int = -1
    n_ctx: int = 4096
    # Quantas traduções anteriores entram como contexto rolante no prompt — ajuda o
    # LLM a manter consistência de tom/nome entre falas do mesmo balão.
    context_window: int = 6
    # JSON simples {"nome original": "tradução"}. None = prompt não inclui glossário.
    glossary_path: str | None = None


@dataclass
class OverlayConfig:
    box_color: tuple[int, int, int, int] = (0, 0, 0, 205)
    text_color: tuple[int, int, int] = (245, 245, 245)
    outline_color: tuple[int, int, int, int] = (0, 0, 0, 180)
    # Borda das caixas que o gate marcou como duvidosas (âmbar).
    review_color: tuple[int, int, int, int] = (230, 160, 30, 230)
    corner_radius: int = 6
    padding: int = 6
    min_font_pt: int = 7
    max_font_pt: int = 42
    font_family: str = "Segoe UI"


@dataclass
class HotkeyConfig:
    # Nomes resolvidos em ui/hotkey.py. "capture" dispara o pipeline, "dismiss"
    # apaga o overlay — necessário porque a janela é transparente a input e nunca
    # recebe um Esc por conta própria.
    capture: str = "F8"
    dismiss: str = "F9"
    quit: str = "F10"
    # Todo backend de captura já aceita região opcional (mss/dxcam); estas duas só
    # dão uma forma de escolher a região por UI em vez de só por config.toml.
    select_area: str = "F11"
    # F12 era o default óbvio (ao lado de F8-F11), mas é comumente reservado por
    # outro programa no Windows (overlay de GPU, gravador de tela) — nesta máquina
    # `RegisterHotKey` recusou com erro 1409. F7 não colide com nada do app nem com
    # essas reservas comuns.
    show_region_outline: str = "F7"


@dataclass
class Config:
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    ocr: OCRConfig = field(default_factory=OCRConfig)
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    gate: GateConfig = field(default_factory=GateConfig)
    grouping: GroupingConfig = field(default_factory=GroupingConfig)
    translation: TranslationConfig = field(default_factory=TranslationConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    hotkeys: HotkeyConfig = field(default_factory=HotkeyConfig)
    debug_dump: bool = False


def _apply(target: Any, data: dict[str, Any], path: str = "") -> None:
    known = {f.name: f for f in fields(target)}
    for key, value in data.items():
        if key not in known:
            raise ValueError(f"Chave desconhecida em {CONFIG_FILENAME}: {path}{key}")
        current = getattr(target, key)
        if is_dataclass(current) and isinstance(value, dict):
            _apply(current, value, f"{path}{key}.")
        elif isinstance(current, tuple) and isinstance(value, list):
            setattr(target, key, tuple(value))
        else:
            setattr(target, key, value)


def load_config(path: str | Path | None = None) -> Config:
    """Carrega a config, caindo nos defaults quando o arquivo não existe."""
    cfg = Config()
    candidate = Path(path) if path else Path(CONFIG_FILENAME)
    if candidate.is_file():
        with candidate.open("rb") as fh:
            _apply(cfg, tomllib.load(fh))
    return cfg
