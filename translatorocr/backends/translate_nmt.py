"""Tradução NMT local — opus-mt en→pt em CTranslate2.

É o tier 1 de tradução local: sem rede, sem cota, sem rate limit. A nuvem funciona bem
a ritmo humano, mas depende de conexão e pode falhar sob rajada.

Roda em **CPU** por decisão, não por limitação de esforço: o `ctranslate2.dll` carrega
`cublas64_12.dll` por nome e este venv tem CUDA 13 (veio do `onnxruntime-gpu`). Ligar a
GPU exigiria o wheel `nvidia-cublas-cu12` de ~553 MB mais um `os.add_dll_directory`
manual — para então disputar os 6 GB da placa com o OCR e o detector. Em CPU a tradução
ainda roda concorrente com a inferência de GPU, que é o que interessa.

Três detalhes de tokenização, cada um capaz de degradar a saída **sem** levantar erro:

1. O `opus-mt-tc-big-en-pt` é multi-alvo e exige token inicial de idioma — `>>pob<<`
   para português brasileiro, `>>por<<` para o europeu.
2. Esse token entra **cru, como peça literal, antes** da saída do SentencePiece. Passar
   `">>pob<< texto"` inteiro para o `sp.encode` faz o tokenizador fatiar o próprio
   marcador em pedaços, e o modelo perde a instrução de idioma.
3. O `config.json` deste modelo traz `add_source_eos: false`, então o `</s>` final é
   responsabilidade nossa. O campo é **lido**, não presumido: um modelo convertido pelo
   caminho Marian vem com `true`, e aí anexar de novo duplicaria o token.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..config import TranslationConfig
from .cache import TranslationCache, resolve_with_cache

log = logging.getLogger(__name__)

NAME = "nmt"

# O modelo é um par fixo. Fora deste par ele não tem o que fazer, e é melhor devolver
# vazio para a cadeia cair no próximo tier do que produzir tradução errada em silêncio.
SOURCE_LANGS = frozenset({"en", "eng", "en-us", "en-gb"})
TARGET_LANGS = frozenset({"pt", "por", "pt-br", "pob"})

EOS = "</s>"


class NMTTranslator:
    def __init__(self, cfg: TranslationConfig, cache: TranslationCache | None = None) -> None:
        import ctranslate2
        import sentencepiece as spm

        path = Path(cfg.nmt_model_path)
        if not path.is_dir():
            raise FileNotFoundError(
                f"Modelo de NMT não encontrado em {path.resolve()}. "
                "Rode `uv run scripts/fetch_models.py nmt`."
            )

        self._cfg = cfg
        self._cache = cache
        self._translator: Any = ctranslate2.Translator(
            str(path),
            device="cpu",
            compute_type=cfg.nmt_compute_type,
            inter_threads=cfg.nmt_threads or 1,
        )
        # Any: só usamos Encode/Decode, e é o que permite dublar isto em teste.
        self._sp_source: Any = spm.SentencePieceProcessor()
        self._sp_source.Load(str(path / "source.spm"))
        self._sp_target: Any = spm.SentencePieceProcessor()
        self._sp_target.Load(str(path / "target.spm"))

        # Ver a nota 3 do módulo: lido do modelo, não presumido.
        model_cfg = json.loads((path / "config.json").read_text(encoding="utf-8"))
        self._add_eos = not model_cfg.get("add_source_eos", False)
        log.info(
            "NMT carregado de %s (compute_type=%s, eos manual=%s)",
            path,
            cfg.nmt_compute_type,
            self._add_eos,
        )

    def _supports(self, source: str, target: str) -> bool:
        source, target = source.lower(), target.lower()
        # "auto" é aceito porque o reconhecedor só produz inglês; qualquer outro idioma
        # explícito que não seja inglês significa que este modelo é o backend errado.
        return (source in SOURCE_LANGS or source == "auto") and target in TARGET_LANGS

    def _encode(self, text: str) -> list[str]:
        pieces: list[str] = self._sp_source.Encode(text, out_type=str)
        if self._cfg.nmt_lang_token:
            pieces = [self._cfg.nmt_lang_token, *pieces]
        if self._add_eos:
            pieces.append(EOS)
        return pieces

    def translate(self, texts: list[str], source: str, target: str) -> list[str | None]:
        if not self._supports(source, target):
            log.debug("NMT não cobre %s→%s; deixando para o próximo tier", source, target)
            return [None] * len(texts)

        def run(pending: list[int]) -> list[str | None]:
            batch = [self._encode(texts[i]) for i in pending]
            try:
                results = self._translator.translate_batch(
                    batch,
                    beam_size=self._cfg.nmt_beam_size,
                    # O modelo tem `decoder_start_token: </s>`; deixar o CT2 usar o
                    # default dele evita reimplementar essa escolha aqui.
                )
            except Exception as exc:  # noqa: BLE001 — fronteira com lib nativa
                log.warning("NMT falhou no lote de %d: %s", len(batch), exc)
                return [None] * len(pending)

            out: list[str | None] = []
            for result in results:
                if not result.hypotheses:
                    out.append(None)
                    continue
                decoded = self._sp_target.Decode(result.hypotheses[0]).strip()
                out.append(decoded or None)
            return out

        return resolve_with_cache(texts, source, target, self._cache, NAME, run)
