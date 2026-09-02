"""Benchmark de tradutores locais/nuvem sobre imagens reais de webtoon.

    uv run scripts/benchmark_llm.py --candidate nmt
    uv run scripts/benchmark_llm.py --candidate cloud
    uv run scripts/benchmark_llm.py --candidate llm --model-path models/qwen3-4b-q4.gguf
    uv run scripts/benchmark_llm.py --candidate llm --model-path ... --n-gpu-layers 20

Mede, por candidato, latência ponta a ponta, latência do primeiro bloco pronto e
pico de VRAM. Um candidato por processo -- VRAM de modelos diferentes não é
liberada de forma confiável no mesmo processo Python, e rodar cada um isolado é o
que garante que o pico medido é só daquele candidato.

Sem métrica automática de acurácia: o dataset (Kaggle webtoons-comic-pages-and-text,
em `dataset/`) não vem com nenhuma referência limpa por balão -- o `.txt` que
acompanha cada imagem é ruidoso (despejo de página inteira, com onomatopeia, texto
de logo invertido etc.) e é ignorado de propósito. A avaliação de qualidade
(correção de OCR pelo LLM, tradução) é impressa lado a lado para julgamento visual.

Roda o pipeline de OCR (detector + reconhecedor, reaproveitando `build_ocr`) sobre
arquivo de imagem em vez de captura de tela -- é também a primeira validação do
detector/OCR/gate contra página de webtoon real, não só contra tela de IDE.

Sem cobertura de teste -- ferramenta exploratória, não pipeline de produção.
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger("benchmark_llm")

ROOT = Path(__file__).resolve().parent.parent
# O projeto não é instalado como pacote (mesma razão do `pythonpath = ["."]` do
# pytest em pyproject.toml) -- rodar este arquivo diretamente não põe a raiz no
# sys.path sozinho, só o diretório scripts/.
sys.path.insert(0, str(ROOT))

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
RESET = "\033[0m"


@dataclass
class BlockResult:
    source: str
    confidence: float
    needs_review: bool
    output: str | None
    latency: float


@dataclass
class PageResult:
    path: Path
    blocks: list[BlockResult] = field(default_factory=list)
    detected: int = 0
    ocr_time: float = 0.0
    translate_time: float = 0.0
    first_block_time: float | None = None


def _sample_images(data_dir: Path, count: int, seed: int) -> list[Path]:
    images = sorted(data_dir.glob("*/*.jpg"))
    if not images:
        raise SystemExit(f"Nenhuma imagem em {data_dir} (esperado <id>/<id>.jpg)")
    random.Random(seed).shuffle(images)
    return images[:count]


class VramSampler:
    """Amostra o uso de VRAM em background pra capturar o pico, não só antes/depois."""

    def __init__(self, interval: float = 0.05) -> None:
        self._interval = interval
        self._peak = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        try:
            import pynvml

            pynvml.nvmlInit()
            self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self._pynvml = pynvml
        except Exception:  # noqa: BLE001 — sem driver/GPU, degrada pra "sem medição"
            log.warning("pynvml indisponível; pico de VRAM não será medido.")
            self._pynvml = None

    def _poll(self) -> None:
        while not self._stop.is_set():
            info = self._pynvml.nvmlDeviceGetMemoryInfo(self._handle)
            self._peak = max(self._peak, info.used)
            time.sleep(self._interval)

    def __enter__(self) -> VramSampler:
        if self._pynvml is not None:
            self._peak = self._pynvml.nvmlDeviceGetMemoryInfo(self._handle).used
            self._thread = threading.Thread(target=self._poll, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)

    @property
    def peak_mb(self) -> float | None:
        return self._peak / (1 << 20) if self._pynvml is not None else None


def build_ocr_pipeline():
    """Monta detector + reconhecedor com os defaults de produção (já baixados)."""
    from translatorocr.config import Config
    from translatorocr.registry import build_ocr

    config = Config()
    return config, build_ocr(config)


def run_ocr_and_gate(ocr, config, image: np.ndarray) -> tuple[list, float]:
    from translatorocr.core.gate import apply_gate
    from translatorocr.core.grouping import group
    from translatorocr.models import Capture

    started = time.perf_counter()
    lines = ocr.read(image)
    blocks = group(lines, config.grouping)
    shot = Capture(image=image, origin=(0, 0))
    for block in blocks:
        block.bbox = shot.to_desktop(block.bbox)
    blocks = apply_gate(blocks, config.gate, config.ocr.lang)
    return blocks, time.perf_counter() - started


class NMTCandidate:
    name = "nmt"

    def __init__(self, config) -> None:
        from translatorocr.backends.cache import TranslationCache
        from translatorocr.backends.translate_nmt import NMTTranslator

        cache = TranslationCache(":memory:")
        self._translator = NMTTranslator(config.translation, cache)

    def translate_one(self, text: str, context: list[str]) -> str | None:
        return self._translator.translate([text], "en", "pt")[0]


class CloudCandidate:
    name = "cloud"

    def __init__(self, config) -> None:
        from translatorocr.backends.cache import TranslationCache
        from translatorocr.backends.translate_cloud import CloudTranslator

        cache = TranslationCache(":memory:")
        self._translator = CloudTranslator(config.translation, cache)

    def translate_one(self, text: str, context: list[str]) -> str | None:
        return self._translator.translate([text], "en", "pt")[0]


def _strip_think(text: str) -> str:
    """Remove o bloco `<think>...</think>` do Qwen3 (vazio, com `/no_think`).

    Se `<think>` abriu mas nunca fechou, o `max_tokens` cortou no meio do
    raciocínio antes de chegar numa resposta de verdade -- o que sobrou é
    raciocínio truncado, não tradução, então devolve vazio em vez de expor lixo
    como se fosse a saída.
    """
    text = text.strip()
    if "</think>" in text:
        return text.rsplit("</think>", 1)[-1].strip()
    if text.startswith("<think>"):
        return ""
    return text


class LLMCandidate:
    """Wrapper ad-hoc de exploração -- não é a `LLMTranslator` de produção.

    Esse modelo é experimental; isolar o experimento aqui evita construir a peça
    de produção em cima de um modelo que pode não ser o escolhido.
    """

    name = "llm"

    def __init__(self, model_path: str, n_gpu_layers: int, n_ctx: int, glossary: dict) -> None:
        from llama_cpp import Llama

        self._llm = Llama(
            model_path=model_path,
            n_gpu_layers=n_gpu_layers,
            n_ctx=n_ctx,
            verbose=False,
        )
        self._glossary = glossary

    def _user_content(self, text: str, context: list[str]) -> str:
        glossary_txt = ""
        if self._glossary:
            pairs = ", ".join(f"{k} -> {v}" for k, v in self._glossary.items())
            glossary_txt = f"Glossário de nomes próprios: {pairs}\n"
        context_txt = ""
        if context:
            context_txt = "Contexto (falas anteriores já traduzidas): " + " / ".join(context) + "\n"
        # "/no_think" é a chave documentada do Qwen3 pra desligar o modo de raciocínio
        # por mensagem -- sem isso a resposta vem precedida de um bloco <think>...</think>
        # que o completion cru (sem chat template) não sabia nem que existia.
        return (
            f"{glossary_txt}{context_txt}Texto (com possíveis erros de OCR): {text}\n"
            "Responda APENAS com a tradução final em português brasileiro, sem "
            "explicação, sem aspas, sem repetir o original. /no_think"
        )

    def translate_one(self, text: str, context: list[str]) -> str | None:
        # create_chat_completion (não __call__ com prompt cru) porque modelos
        # instruct-tuned como o Qwen3 esperam o chat template embutido no GGUF --
        # sem ele o modelo às vezes só ecoa o texto de entrada em vez de segui-lo
        # como instrução (medido: "Hey Dog." voltou "Hey Dog." sem tradução nenhuma).
        messages = [
            {
                "role": "system",
                "content": (
                    "Você corrige erros de OCR em texto de balão de quadrinho em inglês "
                    "e traduz para português brasileiro, num só passo."
                ),
            },
            {"role": "user", "content": self._user_content(text, context)},
        ]
        out = self._llm.create_chat_completion(messages=messages, max_tokens=300, temperature=0.2)
        result = _strip_think(out["choices"][0]["message"]["content"])
        return result or None


def _load_glossary(path: str | None) -> dict:
    if not path:
        return {}
    import json

    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_candidate(candidate, config, ocr, images: list[Path]) -> list[PageResult]:
    results: list[PageResult] = []
    context: deque[str] = deque(maxlen=6)

    for path in images:
        image = cv2.imread(str(path))
        if image is None:
            log.warning("Não abriu %s, pulando", path)
            continue

        blocks, ocr_time = run_ocr_and_gate(ocr, config, image)
        page = PageResult(path=path, detected=len(blocks), ocr_time=ocr_time)

        t_start = time.perf_counter()
        for i, block in enumerate(blocks):
            b_start = time.perf_counter()
            try:
                output = candidate.translate_one(block.source, list(context))
            except Exception:
                log.exception("Candidato falhou no bloco %r", block.source[:60])
                output = None
            elapsed = time.perf_counter() - b_start
            if output:
                context.append(output)
            if i == 0:
                page.first_block_time = elapsed
            page.blocks.append(
                BlockResult(block.source, block.confidence, block.needs_review, output, elapsed)
            )
        page.translate_time = time.perf_counter() - t_start
        results.append(page)

    return results


def _print_report(
    candidate_name: str, results: list[PageResult], vram_peak_mb: float | None
) -> None:
    total_blocks = sum(len(p.blocks) for p in results)
    total_ocr = sum(p.ocr_time for p in results)
    total_translate = sum(p.translate_time for p in results)
    first_block_times = [p.first_block_time for p in results if p.first_block_time is not None]

    print(f"\n{BOLD}=== {candidate_name} ==={RESET}")
    print(f"  páginas: {len(results)}  ·  blocos (pós-gate): {total_blocks}")
    print(f"  ocr+gate total: {total_ocr:.2f}s  ·  tradução total: {total_translate:.2f}s")
    if first_block_times:
        avg_first = sum(first_block_times) / len(first_block_times)
        print(f"  latência do 1º bloco (média): {avg_first:.3f}s")
    if vram_peak_mb is not None:
        print(f"  pico de VRAM: {vram_peak_mb:.0f} MB")

    print(f"\n  {DIM}amostras (original / saída){RESET}")
    shown = 0
    for page in results:
        for block in page.blocks:
            if shown >= 12:
                break
            review = " [needs_review]" if block.needs_review else ""
            print(f"    {DIM}{page.path.parent.name}{RESET}{review}")
            print(f"      EN: {block.source[:90]}")
            print(f"      ->  {block.output!r}")
            shown += 1
        if shown >= 12:
            break


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="benchmark_llm", description=__doc__)
    parser.add_argument("--candidate", required=True, choices=["nmt", "cloud", "llm"])
    parser.add_argument(
        "--data", default=str(ROOT / "dataset" / "Action"), help="pasta <id>/<id>.jpg"
    )
    parser.add_argument("--samples", type=int, default=8)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--model-path", help="obrigatório para --candidate llm (arquivo .gguf)")
    parser.add_argument("--n-gpu-layers", type=int, default=-1, help="-1 = offload total")
    parser.add_argument("--n-ctx", type=int, default=4096)
    parser.add_argument("--glossary", help="JSON opcional {'nome': 'tradução'}")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    # Console do Windows costuma abrir em cp1252, que não cobre nem todo Latin-1
    # Supplement (õ passa, → não) -- degrada em vez de estourar no meio do relatório.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    if args.candidate == "llm" and not args.model_path:
        parser.error("--candidate llm precisa de --model-path")

    images = _sample_images(Path(args.data), args.samples, args.seed)
    print(f"{len(images)} imagens de {args.data}")

    config, ocr = build_ocr_pipeline()

    with VramSampler() as vram:
        if args.candidate == "nmt":
            candidate = NMTCandidate(config)
        elif args.candidate == "cloud":
            candidate = CloudCandidate(config)
        else:
            glossary = _load_glossary(args.glossary)
            candidate = LLMCandidate(args.model_path, args.n_gpu_layers, args.n_ctx, glossary)

        results = run_candidate(candidate, config, ocr, images)

    _print_report(args.candidate, results, vram.peak_mb)

    report_path = ROOT / "benchmark_results.md"
    with report_path.open("a", encoding="utf-8") as fh:
        total_blocks = sum(len(p.blocks) for p in results)
        fh.write(f"\n## {args.candidate} ({time.strftime('%Y-%m-%d %H:%M')})\n\n")
        fh.write(f"- páginas: {len(results)}, blocos: {total_blocks}\n")
        fh.write(f"- ocr+gate: {sum(p.ocr_time for p in results):.2f}s\n")
        fh.write(f"- tradução: {sum(p.translate_time for p in results):.2f}s\n")
        if vram.peak_mb is not None:
            fh.write(f"- pico VRAM: {vram.peak_mb:.0f} MB\n")
    print(f"\n{GREEN}Relatório também salvo em {report_path}{RESET}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
