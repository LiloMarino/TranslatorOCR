"""Tier de refino por LLM local — segunda passada de refino após NMT/nuvem.

Diferente de `NMTTranslator`/`CloudTranslator`, isto **não** entra na
`ChainTranslator`: o contrato dela é "só recebe o que o tier anterior não conseguiu
(`None`)", mas NMT/nuvem quase sempre têm sucesso mesmo em blocos que o gate marcou
`needs_review` — o problema ali não é falta de tradução, é OCR duvidoso entrando cru
na tradução. Por isso o LLM é uma **segunda passada de refino**, chamada só por
`Pipeline.refine`, só nos blocos `needs_review`, depois que a tradução rápida
(nmt/cloud) já foi desenhada na tela. NMT pinta na hora, o LLM corrige e atualiza
a caixa no lugar.

Modelo e `n_gpu_layers` calibrados com base em benchmark (`scripts/benchmark_llm.py`) —
ver notas em `config.LLMConfig`.

**Chat completion, não completion cru.** A primeira versão mandava um prompt de texto
livre direto pro modelo (`Llama.__call__`) e o resultado saía sem seguir a instrução —
"HEY DOG." voltava "HEY DOG." sem tradução nenhuma. O Qwen3 é instruct-tuned e espera o
chat template embutido no GGUF; `create_chat_completion` é o que aplica esse template.

**`/no_think`.** Sem isso a resposta vem precedida de um bloco `<think>...</think>` de
raciocínio — o Qwen3 é um modelo "híbrido" que pensa por padrão. `/no_think` no fim da
mensagem do usuário é a chave documentada pra desligar isso por mensagem; mesmo assim o
bloco (vazio) ainda aparece na saída e precisa ser removido (`_strip_think`).

**Bloco de uma palavra não vai ao LLM.** Onomatopeia solta ("THUD",
"DROP") ou número de página sem contexto nenhum pra traduzir faz o modelo "alucinar"
e devolver a tradução do bloco anterior em vez de admitir que não há o que traduzir.
`Pipeline.refine` filtra isso antes de chamar `refine()` — ver lá.
"""

from __future__ import annotations

import json
import logging
from collections import deque
from pathlib import Path
from typing import Any

from ..config import LLMConfig
from ..models import TextBlock

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Você corrige erros de OCR em texto de balão de quadrinho em inglês e traduz "
    "para português brasileiro, num só passo."
)


def _strip_think(text: str) -> str:
    """Remove o bloco `<think>...</think>` do Qwen3 (vazio, por causa do `/no_think`).

    Se `<think>` abriu mas nunca fechou, `max_tokens` cortou no meio do raciocínio
    antes de chegar numa resposta de verdade — o que sobrou é raciocínio truncado,
    não tradução, então some vazio em vez de expor lixo como se fosse a saída.
    """
    text = text.strip()
    if "</think>" in text:
        return text.rsplit("</think>", 1)[-1].strip()
    if text.startswith("<think>"):
        return ""
    return text


class LLMTranslator:
    def __init__(self, cfg: LLMConfig) -> None:
        from llama_cpp import Llama

        path = Path(cfg.model_path)
        if not path.is_file():
            raise FileNotFoundError(
                f"Modelo de LLM não encontrado em {path.resolve()}. "
                "Rode `uv run scripts/fetch_models.py llm`."
            )

        self._cfg = cfg
        self._llm: Any = Llama(
            model_path=str(path),
            n_gpu_layers=cfg.n_gpu_layers,
            n_ctx=cfg.n_ctx,
            verbose=False,
        )
        # Contexto rolante vive na instância — mesmo padrão de "modelo carregado uma
        # vez, estado entre chamadas na própria instância" de NMTTranslator/CloudTranslator.
        self._context: deque[str] = deque(maxlen=cfg.context_window)
        self._glossary = self._load_glossary(cfg.glossary_path)
        log.info(
            "LLM carregado de %s (n_gpu_layers=%d, glossário=%d termos)",
            path,
            cfg.n_gpu_layers,
            len(self._glossary),
        )

    @staticmethod
    def _load_glossary(path: str | None) -> dict[str, str]:
        if not path:
            return {}
        candidate = Path(path)
        if not candidate.is_file():
            log.warning("LLMConfig.glossary_path configurado mas não encontrado: %s", candidate)
            return {}
        return json.loads(candidate.read_text(encoding="utf-8"))

    def _user_content(self, text: str) -> str:
        glossary_txt = ""
        if self._glossary:
            pairs = ", ".join(f"{k} -> {v}" for k, v in self._glossary.items())
            glossary_txt = f"Glossário de nomes próprios: {pairs}\n"
        context_txt = ""
        if self._context:
            context_txt = (
                "Contexto (falas anteriores já traduzidas): " + " / ".join(self._context) + "\n"
            )
        return (
            f"{glossary_txt}{context_txt}Texto (com possíveis erros de OCR): {text}\n"
            "Responda APENAS com a tradução final em português brasileiro, sem "
            "explicação, sem aspas, sem repetir o original. /no_think"
        )

    def refine(self, blocks: list[TextBlock]) -> list[str | None]:
        """Corrige OCR e traduz cada bloco, preservando ordem.

        `None` significa "nada aproveitável" (saída vazia ou exceção) — quem chama
        (`Pipeline.refine`) mantém a tradução provisória que o bloco já tinha; o
        refino nunca regride para pior que o tier rápido já produziu.
        """
        out: list[str | None] = []
        for block in blocks:
            try:
                completion = self._llm.create_chat_completion(
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": self._user_content(block.source)},
                    ],
                    max_tokens=300,
                    temperature=0.2,
                )
                text = _strip_think(completion["choices"][0]["message"]["content"])
            except Exception:
                log.exception("LLM falhou no bloco %r", block.source[:60])
                text = ""

            if text:
                self._context.append(text)
            out.append(text or None)
        return out
