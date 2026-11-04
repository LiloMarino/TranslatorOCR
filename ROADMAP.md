<!-- ARQUIVO GERADO POR scripts/roadmap.py (skill problem-analysis-roadmap) -- NÃO EDITAR À MÃO. -->

> ⚠️ **Este arquivo é gerado automaticamente — não edite manualmente.** Toda mudança (inserir/mover/concluir/descartar/remover um card, cadastrar ou atualizar um achado/problema, o cabeçalho) passa por `scripts/roadmap.py` (ver `SKILL.md`); uma edição direta aqui é sobrescrita sem aviso na próxima regeneração.

# Roadmap — leitura de página (OCR) e sua medição

> Kanban de tracking, segue a metodologia da skill `problem-analysis-roadmap`. Companion: [OCR_ANALYSIS.md](OCR_ANALYSIS.md) — lá está o "porquê" (achados de código, problemas, ideias, síntese causal); aqui fica só o "o quê fazer e em que estado está".
>
> **Regra de sincronização:** os dois documentos usam os mesmos IDs (`A#`, `P#`, `I#`, `S#`) e devem sempre concordar sobre a decisão vigente de cada item.
>
> **Arquivo morto:** [OCR_ARCHIVE.md](OCR_ARCHIVE.md) — itens encerrados e problemas fechados saem dos dois documentos pra lá, inteiros. Consulta por ID.
>
> **Última mudança (2026-11-04):** A régua do gabarito achou o classificador de ângulo desvirando linha curta (A22); desligado, balões a 210 de 210 exatos, e S1, I7 e I8 descartados pela medição.

## Glossário

> Descrição completa de cada um em `OCR_ANALYSIS.md`.

### Em aberto

| ID | Resumo | Status |
| --- | --- | --- |
| **P1** | Lendo mangá no navegador, balões somem ou saem com letra trocada, de forma inconsistente | — |
| **P2** | Balão encostado na borda da tela sai traduzido pela metade, sem aviso | — |
| **P3** | Não dá para verificar se está funcionando sem ocupar a tela real | — |
| **P4** | A tradução sai literal, sem entender a frase nem a fala anterior | — |
| **P5** | Teclas demais, espalhadas, e que tiram teclas do navegador | — |
| **A2** | O DBNet não gera caixa de linha para balão curto, em nenhuma escala | ⚠️ |
| **A3** | A ampliação de um recorte no mosaico depende das dimensões do mosaico inteiro, acoplando os recortes | ⚠️ |
| **A4** | A escolha entre primeira e segunda leitura usa a confiança do reconhecedor, que não arbitra bem | ⚠️ |
| **A7** | Não há gate de estabilidade: o overlay desenha a primeira leitura que chegar | ⚠️ |
| **A9** | Palavra curta com til decorativo sai errada em resolução nativa | ⚠️ |
| **A10** | O tradutor roda em CPU por incompatibilidade de versão de cuBLAS; correção conhecida e cara | ⚠️ |
| **A11** | A geração seguinte do OCR não é alcançável na versão atual do rapidocr; reavaliar ao subir de versão | ⚠️ |
| **A21** | A segunda passada é dezenas de vezes mais lenta que o opus-mt, numa fila FIFO; a GPU não tem tensor cores | ⚠️ |
| [**S3**](#s3) | Gate de estabilidade: exigir duas leituras iguais antes de desenhar | 💤 |
| [**I14**](#i14) | OCR só na faixa que entrou na tela, em vez da tela inteira | 🔍 |
| [**I15**](#i15) | Recompilar o llama-cpp-python para GPU sem tensor cores (MMQ, arquiteturas 61/80 virtuais) | 💤 |

<details>
<summary><strong>Resolvido / descartado / informativo (2 itens — clique pra expandir)</strong></summary>

| ID | Resumo | Status |
| --- | --- | --- |
| **A1** | O reconhecedor roda uma vez na imagem cheia; as regiões do detector só atribuem e filtram | ℹ️ |
| **A8** | O detector é treinado em mangá/HQ e rende menos fora dessa distribuição | ℹ️ |

</details>

---

## 🧭 Frentes de trabalho

### Frente 1 — P1

| ID | Resumo | Status |
| --- | --- | --- |
| [**I14**](#i14) | OCR só na faixa que entrou na tela, em vez da tela inteira | 🔍 |

### Sem frente definida

| ID | Resumo | Status |
| --- | --- | --- |
| **A2** | O DBNet não gera caixa de linha para balão curto, em nenhuma escala | ⚠️ |
| **A3** | A ampliação de um recorte no mosaico depende das dimensões do mosaico inteiro, acoplando os recortes | ⚠️ |
| **A4** | A escolha entre primeira e segunda leitura usa a confiança do reconhecedor, que não arbitra bem | ⚠️ |
| **A7** | Não há gate de estabilidade: o overlay desenha a primeira leitura que chegar | ⚠️ |
| **A9** | Palavra curta com til decorativo sai errada em resolução nativa | ⚠️ |
| **A10** | O tradutor roda em CPU por incompatibilidade de versão de cuBLAS; correção conhecida e cara | ⚠️ |
| **A11** | A geração seguinte do OCR não é alcançável na versão atual do rapidocr; reavaliar ao subir de versão | ⚠️ |
| **A21** | A segunda passada é dezenas de vezes mais lenta que o opus-mt, numa fila FIFO; a GPU não tem tensor cores | ⚠️ |
| [**S3**](#s3) | Gate de estabilidade: exigir duas leituras iguais antes de desenhar | 💤 |
| [**I15**](#i15) | Recompilar o llama-cpp-python para GPU sem tensor cores (MMQ, arquiteturas 61/80 virtuais) | 💤 |

---

## 1. Resolve problema — via Ideia (I#)

> Nenhum item nesta categoria atualmente.

---
## 2. Resolve problema — via Síntese (S#)

> Nenhum item nesta categoria atualmente.

---
## 3. Nice-to-have

| ID | Resumo | A# | Esforço | Risco | Ganho esperado | Custo-benefício | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **S3** | Gate de estabilidade: exigir duas leituras iguais antes de desenhar | A7 | Baixo | Baixo | Baixo | Baixo | 💤 Registrado, sem prioridade |
| **I15** | Recompilar o llama-cpp-python para GPU sem tensor cores (MMQ, arquiteturas 61/80 virtuais) | A21 | Baixo | Baixo | Incerto | Bom | 💤 Registrado, sem prioridade |

<a id="s3"></a>
**S3 - Exigir leitura repetida antes de desenhar.** Nao endereca nenhum P#: o caso que resolve e texto animado letra por letra, que e jogo, e o foco hoje e manga.

Plano: no modo de leitura, `App._on_ready` passa a comparar o `source` de cada bloco novo com o da rodada anterior na mesma posicao (o casamento por posicao ja existe em `BlockLedger._match`, e a `Entry` ja conta leituras seguidas em `misses`) e so promove para desenhado o bloco cujo texto saiu igual duas vezes seguidas; enquanto nao sair, mantem o que ja estava. Como o pipeline so roda quando a rolagem para, e `ScrollTracker.settled` so dispara uma vez por parada, isso custa uma segunda passada por parada - o gatilho seria pedir uma leitura extra ao fim da primeira, ou um `settle_frames` dobrado so quando o gate estiver ligado.

Condicao de disparo: alguem voltar a usar o app em jogo. Enquanto o uso for manga, o custo (dobrar a latencia de cada parada) nao se paga.

<a id="i15"></a>
**I15 — Recompilar o llama-cpp-python para GPU sem tensor cores (MMQ, arquiteturas 61/80 virtuais).** Ataca A21 sem mexer no desenho da fila.

O build atual já é CUDA, mas o llama.cpp avisa ao carregar que a GPU não tem tensor cores e que o caminho compilado é o subótimo.

Plano:
1. Medir antes: `uv run --group llm scripts/benchmark_llm.py --candidate gemma` sobre `eval/pages` (tempo por balão e pico de VRAM), e o tempo por balão no log do app com `-v`.
2. Recompilar: `CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=61-virtual;80-virtual -DGGML_CUDA_FORCE_MMQ=on"`, com o ambiente do MSVC (vcvars) e Ninja, forçando a reinstalação do `llama-cpp-python` no grupo `llm`.
3. Medir de novo nas mesmas páginas, com a mesma semente, e conferir que o aviso de tensor cores sumiu do log.
4. Ficar com o build novo só se o tempo por balão cair. Se ficar, os flags vão para o aviso de instalação em `registry.build_refiner` e para o README.

Custo: uma recompilação (alguns minutos) e duas medições. Volta atrás reinstalando o build atual.

---
## 4. Descartada

> Nenhum item nesta categoria atualmente.

---
## 5. Incerta / exploratória

| ID | Resumo | Conexão | Status |
| --- | --- | --- | --- |
| **I14** | OCR só na faixa que entrou na tela, em vez da tela inteira | P1; A14 | 🔍 Em avaliação |

<a id="i14"></a>
**I14 — OCR só na faixa que entrou na tela, em vez da tela inteira.** Falta definir o tratamento do balão cortado na fronteira da faixa: ou a faixa ganha uma margem que cobre um balão inteiro, ou o balão de fronteira é relido pela tela toda. Falta também medir o ganho de GPU, que depende de a rolagem típica ser curta. Depende do registro de balões (I13).
