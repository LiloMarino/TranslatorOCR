<!-- ARQUIVO GERADO POR scripts/roadmap.py (skill problem-analysis-roadmap) -- NÃO EDITAR À MÃO. -->

> ⚠️ **Este arquivo é gerado automaticamente — não edite manualmente.** Toda mudança (inserir/mover/concluir/descartar/remover um card, cadastrar ou atualizar um achado/problema, o cabeçalho) passa por `scripts/roadmap.py` (ver `SKILL.md`); uma edição direta aqui é sobrescrita sem aviso na próxima regeneração.

# Roadmap — leitura de página (OCR) e sua medição

> Kanban de tracking, segue a metodologia da skill `problem-analysis-roadmap`. Companion: [OCR_ANALYSIS.md](OCR_ANALYSIS.md) — lá está o "porquê" (achados de código, problemas, ideias, síntese causal); aqui fica só o "o quê fazer e em que estado está".
>
> **Regra de sincronização:** os dois documentos usam os mesmos IDs (`A#`, `P#`, `I#`, `S#`) e devem sempre concordar sobre a decisão vigente de cada item.
>
> **Última mudança (2026-09-21):** Primeira rodada: catalogada a investigação da leitura instável em página reduzida, e trazidas para cá as limitações em aberto que viviam no README e no CLAUDE.md (A7-A11). A causa raiz (A3) está identificada mas sem correção fechada; a medição que a torna visível (S2) e os dois itens de usabilidade (I2, I3) estão implementados.

## Glossário

> Descrição completa de cada um em `OCR_ANALYSIS.md`.

### Em aberto

| ID | Resumo | Status |
| --- | --- | --- |
| **P1** | Lendo mangá no navegador, balões somem ou saem com letra trocada, de forma inconsistente | — |
| **P2** | Balão encostado na borda da tela sai traduzido pela metade, sem aviso | — |
| **P3** | Não dá para verificar se está funcionando sem ocupar a tela real | — |
| **A2** | O DBNet não gera caixa de linha para balão curto, em nenhuma escala | ⚠️ |
| **A3** | A ampliação de um recorte no mosaico depende das dimensões do mosaico inteiro, acoplando os recortes | ⚠️ |
| **A4** | A escolha entre primeira e segunda leitura usa a confiança do reconhecedor, que não arbitra bem | ⚠️ |
| **A7** | Não há gate de estabilidade: o overlay desenha a primeira leitura que chegar | ⚠️ |
| **A9** | Palavra curta com til decorativo sai errada em resolução nativa | ⚠️ |
| **A10** | O tradutor roda em CPU por incompatibilidade de versão de cuBLAS; correção conhecida e cara | ⚠️ |
| **A11** | A geração seguinte do OCR não é alcançável na versão atual do rapidocr; reavaliar ao subir de versão | ⚠️ |
| **S1** | Desacoplar a segunda passada de OCR da geometria do mosaico | 🔍 |
| **S3** | Gate de estabilidade: exigir duas leituras iguais antes de desenhar | 💤 |

<details>
<summary><strong>Resolvido / descartado (9 itens — clique pra expandir)</strong></summary>

| ID | Resumo | Status |
| --- | --- | --- |
| **A1** | O reconhecedor roda uma vez na imagem cheia; as regiões do detector só atribuem e filtram | ℹ️ |
| **A5** | O eval não cobrava recall nas vistas de tela (resolvido via S2) | ✅ |
| **A6** | O eval estourava com UnicodeEncodeError com a saída redirecionada (resolvido via S2) | ✅ |
| **A8** | O detector é treinado em mangá/HQ e rende menos fora dessa distribuição | ℹ️ |
| **S2** | Eval cobra recall em toda vista, usando a posição gravada de cada balão | ✅ |
| **I1** | Trocar o motor de OCR por outro modelo | 🚫 |
| **I2** | Modo --image: o pipeline lê de um arquivo, sem a tela participar | ✅ |
| **I3** | Modo de leitura (F6): as caixas acompanham a rolagem | ✅ |
| **I4** | Capturar só a janela do navegador em vez da tela inteira | 🚫 |

</details>

---

## 🧭 Frentes de trabalho

### Frente 1 — P1

| ID | Resumo | Status |
| --- | --- | --- |
| **A2** | O DBNet não gera caixa de linha para balão curto, em nenhuma escala | ⚠️ |
| **A3** | A ampliação de um recorte no mosaico depende das dimensões do mosaico inteiro, acoplando os recortes | ⚠️ |
| **A4** | A escolha entre primeira e segunda leitura usa a confiança do reconhecedor, que não arbitra bem | ⚠️ |
| **A9** | Palavra curta com til decorativo sai errada em resolução nativa | ⚠️ |
| **S1** | Desacoplar a segunda passada de OCR da geometria do mosaico | 🔍 |

<details><summary>Resolvido/descartado (3 itens)</summary>

| ID | Resumo | Status |
| --- | --- | --- |
| **A5** | O eval não cobrava recall nas vistas de tela (resolvido via S2) | ✅ |
| **A6** | O eval estourava com UnicodeEncodeError com a saída redirecionada (resolvido via S2) | ✅ |
| **S2** | Eval cobra recall em toda vista, usando a posição gravada de cada balão | ✅ |

</details>

### Frente 2 — P2

| ID | Resumo | Status |
| --- | --- | --- |
| — | *(nada em aberto)* | — |

<details><summary>Resolvido/descartado (1 item)</summary>

| ID | Resumo | Status |
| --- | --- | --- |
| **I3** | Modo de leitura (F6): as caixas acompanham a rolagem | ✅ |

</details>

### Frente 3 — P3

| ID | Resumo | Status |
| --- | --- | --- |
| — | *(nada em aberto)* | — |

<details><summary>Resolvido/descartado (4 itens)</summary>

| ID | Resumo | Status |
| --- | --- | --- |
| **A5** | O eval não cobrava recall nas vistas de tela (resolvido via S2) | ✅ |
| **A6** | O eval estourava com UnicodeEncodeError com a saída redirecionada (resolvido via S2) | ✅ |
| **S2** | Eval cobra recall em toda vista, usando a posição gravada de cada balão | ✅ |
| **I2** | Modo --image: o pipeline lê de um arquivo, sem a tela participar | ✅ |

</details>

### Sem frente definida

| ID | Resumo | Status |
| --- | --- | --- |
| **A7** | Não há gate de estabilidade: o overlay desenha a primeira leitura que chegar | ⚠️ |
| **A10** | O tradutor roda em CPU por incompatibilidade de versão de cuBLAS; correção conhecida e cara | ⚠️ |
| **A11** | A geração seguinte do OCR não é alcançável na versão atual do rapidocr; reavaliar ao subir de versão | ⚠️ |
| **S3** | Gate de estabilidade: exigir duas leituras iguais antes de desenhar | 💤 |

<details><summary>Resolvido/descartado (4 itens)</summary>

| ID | Resumo | Status |
| --- | --- | --- |
| **A1** | O reconhecedor roda uma vez na imagem cheia; as regiões do detector só atribuem e filtram | ℹ️ |
| **A8** | O detector é treinado em mangá/HQ e rende menos fora dessa distribuição | ℹ️ |
| **I1** | Trocar o motor de OCR por outro modelo | 🚫 |
| **I4** | Capturar só a janela do navegador em vez da tela inteira | 🚫 |

</details>

---

## 1. Resolve problema — via Ideia (I#)

| ID | Resumo | Resolve (P#) | A# | Esforço | Risco | Ganho esperado | Custo-benefício | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **I2** | Modo --image: o pipeline lê de um arquivo, sem a tela participar | P3 | — | Médio | Baixo | Alto | Excelente | ✅ Concluído |
| **I3** | Modo de leitura (F6): as caixas acompanham a rolagem | P2 | — | Alto | Médio | Alto | Bom | ✅ Concluído |

**I2 — Modo `--image`: o pipeline lê de um arquivo, sem a tela participar.** Resolve P3.

`translatorocr/backends/capture_still.py` (novo): `StillCapture` implementa `CaptureBackend` servindo uma viewport sobre a imagem carregada, com `origin` fixa em (0, 0) — assim os bboxes que saem do pipeline já ficam em coordenada da viewport, que é o que o visualizador desenha e o que o rastreio translada. `translatorocr/ui/viewer.py` (novo): janela comum que desenha a viewport e as caixas **no próprio widget**, e cuja roda do mouse move a viewport virtual. `registry.build_pipeline` e `PipelineWorker` passaram a aceitar um backend de captura pronto; no `App`, o visualizador entra no lugar do overlay por duck typing (mesma interface), então o resto do app não sabe em que modo está.

Decisão tomada durante a implementação: a primeira versão abria a imagem numa janela e deixava o app **fotografar a tela** por cima, o que exercitaria também captura, DPI e os flags Win32 do overlay. Foi descartado a pedido — qualquer janela que passe na frente invalida o teste e prende a máquina. O modo atual não cobre esses três; ficam para a conferência ocasional com o app de verdade e para o `--debug-dump`, que foi mantido justamente por ser a única coisa que mostra o que a captura enxergou.

**I3 — Modo de leitura (F6): as caixas acompanham a rolagem.** Resolve P2.

`core/tracker.py` (puro, testável sem GPU nem Qt): `prepare` reduz o quadro a 1/4 e converte para cinza; `estimate_shift` mede o deslocamento por correlação de fase e devolve junto resposta e textura; `shift_blocks` translada as caixas e descarta o que saiu; `merge_tracked` junta a leitura nova com o que sobreviveu à rolagem, com uma exceção que é a razão do modo existir — se o balão novo está cortado e o antigo, no mesmo lugar, foi lido inteiro, vale o antigo. `core/scroll.py` roda o laço a ~16 fps numa thread própria e distingue três situações: nada mudou (conta para "parou"), mudou e é rolagem (translada), mudou e não é rolagem (limpa).

Medições que fixaram os defaults: correlação de fase recupera o deslocamento exato até ~400 px (40% da altura da viewport), com resposta caindo de 0.97 em 60 px para 0.41 em 400 px e 0.01 quando falha; custa 8 ms a 1/4 contra 92 ms em resolução cheia; captura MSS de tela cheia leva 22 ms.

Duas armadilhas pagas aqui. `cv2.phaseCorrelate` **escreve nos arrays que recebe** (aplica a janela de Hanning no lugar), o que corrompia o quadro guardado para a comparação seguinte — resolvido medindo a textura antes e passando cópias. E a resposta da correlação sozinha não basta: uma área totalmente lisa devolve "não andou nada" com resposta 0.99, confiante e errada, o que congelaria as caixas enquanto a página rola; por isso existe o piso de textura.

Pré-requisito que virou parte do item: o overlay precisou sair da captura, senão o laço mediria a rolagem contra as próprias caixas paradas e o OCR releria a tradução em português. Ver o card correspondente.

Não resolve: zoom e troca de página não são translação, e nesses casos o modo limpa em vez de arrastar caixa para o lugar errado.

---
## 2. Resolve problema — via Síntese (S#)

| ID | Resumo | Resolve (P#) | A# | Esforço | Risco | Ganho esperado | Custo-benefício | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **S2** | Eval cobra recall em toda vista, usando a posição gravada de cada balão | P1, P3 | A5, A6 | Baixo | Baixo | Alto | Excelente | ✅ Concluído |

**S2 — Recall cobrado em toda vista de tela.** Resolve P1 no sentido de torná-lo reproduzível e medível, não de corrigi-lo.

`scripts/eval_pages.py`: o JSON de cada página ganhou `boxes`, a posição de cada balão, gerada por `--fit-boxes` (roda o pipeline na página inteira e casa cada bloco com o texto esperado). Um tipo `View` passou a carregar escala, deslocamento e o retângulo do conteúdo, e responde por balão se ele está inteiro, cortado ou fora da vista; o recall é cobrado só sobre os inteiros. Balão cortado é classificado por posição, e não só pela marca `partial` do app, porque na vista simulada o conteúdo começa abaixo de uma faixa de cromo do navegador — o balão é cortado pelo conteúdo sem encostar na borda da imagem. Entrou também uma vista com a página ampliada a 1.3x, já que navegador ampliando é caso real, e `console.setup()` no início do `main()`.

Na primeira execução depois da mudança apareceram falhas que antes passavam verdes: um balão de uma palavra só ausente em 5 das 10 vistas de tela de uma página, e um balão curto lido errado na vista ampliada.

---
## 3. Nice-to-have

| ID | Resumo | A# | Esforço | Risco | Ganho esperado | Custo-benefício | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **S3** | Gate de estabilidade: exigir duas leituras iguais antes de desenhar | A7 | Baixo | Baixo | Baixo | Baixo | 💤 Registrado, sem prioridade |

**S3 - Exigir leitura repetida antes de desenhar.** Nao endereca nenhum P#: o caso que resolve e texto animado letra por letra, que e jogo, e o foco hoje e manga.

Plano: no modo de leitura, `App._on_ready` passa a comparar o `source` de cada bloco novo com o da rodada anterior na mesma posicao (o casamento por sobreposicao ja existe em `core/tracker.merge_tracked`) e so promove para desenhado o bloco cujo texto saiu igual duas vezes seguidas; enquanto nao sair, mantem o que ja estava. Como o pipeline so roda quando a rolagem para, isso custa uma segunda passada por parada - o gatilho seria um `settled` extra em vez de `mark_read` imediato, ou um `settle_frames` dobrado so quando o gate estiver ligado.

Condicao de disparo: alguem voltar a usar o app em jogo. Enquanto o uso for manga, o custo (dobrar a latencia de cada parada) nao se paga.

---
## 4. Descartada

| ID | Resumo | A# | Status |
| --- | --- | --- | --- |
| **I1** | Trocar o motor de OCR por outro modelo | — | 🚫 Descartado |
| **I4** | Capturar só a janela do navegador em vez da tela inteira | — | 🚫 Descartado |

**I1 — Trocar o motor de OCR: medido e pior.** Medido contra o vizinho imediato dentro do mesmo pacote (a geracao anterior do mesmo detector+reconhecedor): nas tres paginas inteiras ele le 17/21 baloes exatos contra 19/21 do atual, perde um balao numa pagina e inventa letra em outra. Alem disso a troca nao toca no estagio que falha: o reconhecedor atual le o texto certo quando recebe o recorte da regiao (A2), e quem nao produz caixa e o detector de linha. Trocar de modelo mudaria o reconhecedor, nao o DBNet.

Reavaliar so se aparecer um pacote que exponha um detector de linha diferente, nao um reconhecedor diferente.

**I4 — Capturar só a janela: desnecessário e mais caro.** Tres argumentos, em ordem de peso. Primeiro, nao e necessario: medido nesta maquina, SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE) tira o overlay da captura (de 15.7% da area para 0.0%) mantendo a translucidez e o click-through, entao o problema que a ideia resolveria ja esta resolvido de graca. Segundo, a variante barata nao funciona: BitBlt sobre o DC de uma janela le a mesma area composta da tela, entao o overlay continuaria na foto. Terceiro, a variante que funciona e cara: PrintWindow com PW_RENDERFULLCONTENT costuma voltar preto em navegador acelerado por GPU, e Windows.Graphics.Capture exige dependencia WinRT nova mais uma UI para escolher a janela, trocando "traduz o que estiver na tela" por "traduz aquela janela".

Reavaliar se a exclusao de captura falhar em alguma maquina: e o plano B natural.

---
## 5. Incerta / exploratória

| ID | Resumo | Conexão | Status |
| --- | --- | --- | --- |
| **S1** | Desacoplar a segunda passada de OCR da geometria do mosaico | P1; A2, A3, A4, A9 | 🔍 Em avaliação |

**S1 — o que falta definir:** Falta escolher o mecanismo. O que já foi medido e **não** serviu: (a) igualar a largura de todos os recortes antes de empilhar — recupera um balão curto a 65% e elimina o lixo que ele gerava, mas faz um balão que estava certo na página inteira passar a sair com letra trocada, empatando no total de vistas com falha; (b) fixar a largura do mosaico em 736 px para o DBNet não reescalar nada — piorou de 8 para 12 vistas com falha, porque a ampliação necessária vira borrão; (c) reconhecer cada região suspeita numa chamada isolada, dando a cada uma a ampliação de ~9x que ela teria sozinha — recupera dois casos que falhavam mas devolve leitura vazia em outros, e custa 137–529 ms contra ~150 ms do mosaico.

Três coisas precisam ser decididas antes de isto virar Pendente: qual mecanismo de desacoplamento (isolar por chamada, agrupar recortes por faixa de tamanho, ou outro); como arbitrar entre a primeira leitura e a segunda sem depender da confiança do reconhecedor (A4), já que hoje uma leitura confiante e errada ganha de uma correta; e qual orçamento de tempo é aceitável, dado que o desenho atual existe justamente para não pagar uma chamada por região (A1).

Condição de disparo natural: ter uma quarta e uma quinta página no eval, para o número de vistas com falha parar de oscilar por conta de uma página só.
