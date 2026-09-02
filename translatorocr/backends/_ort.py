"""As duas armadilhas do ONNXRuntime, num lugar só.

Ambas já custaram uma sessão de debug neste projeto, e ambas valem para *qualquer*
sessão de inferência — o reconhecedor do RapidOCR e o detector de balão inclusive.
Ficam aqui para não serem reimplementadas pela metade a cada backend novo.

1. `preload_cuda_dlls()` **precisa** rodar antes de criar qualquer sessão, senão o ORT
   não acha `cudnn64_9.dll` dos pacotes pip da NVIDIA e o primeiro Conv estoura em
   runtime — mesmo com `CUDAExecutionProvider` aparecendo na lista de disponíveis.
2. Provider disponível ≠ provider carregado. `check_providers()` existe porque a falha
   silenciosa é o modo de falha padrão aqui: o venv anterior tinha `torch 2.12.0+cpu` e
   o EasyOCR rodava em CPU sem avisar por meses.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def preload_cuda_dlls() -> None:
    """Carrega os DLLs de CUDA/cuDNN dos pacotes pip da NVIDIA. Idempotente."""
    import onnxruntime as ort

    if hasattr(ort, "preload_dlls"):
        ort.preload_dlls()


def check_providers(
    stage: str,
    providers: list[str],
    *,
    use_gpu: bool,
    strict_gpu: bool,
) -> None:
    """Confere que a GPU pedida foi de fato carregada.

    Levanta se `strict_gpu` e o provider efetivo veio CPU; só avisa caso contrário.
    """
    log.info("%s providers: %s", stage, providers)
    if not use_gpu or any("CUDA" in p for p in providers):
        return
    message = (
        f"GPU foi pedida para {stage} mas o CUDAExecutionProvider não carregou "
        f"(providers={providers}). Verifique se onnxruntime-gpu foi instalado com os "
        "extras [cuda,cudnn]."
    )
    if strict_gpu:
        raise RuntimeError(message)
    log.warning("%s Seguindo em CPU.", message)


def session_providers(use_gpu: bool) -> list[str]:
    """Lista de providers a pedir, em ordem de preferência."""
    return (
        ["CUDAExecutionProvider", "CPUExecutionProvider"] if use_gpu else ["CPUExecutionProvider"]
    )
