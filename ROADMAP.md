<!-- ARQUIVO GERADO POR scripts/roadmap.py (skill problem-analysis-roadmap) -- NÃO EDITAR À MÃO. -->

> ⚠️ **Este arquivo é gerado automaticamente — não edite manualmente.** Toda mudança (inserir/mover/concluir/descartar/remover um card, cadastrar ou atualizar um achado/problema, o cabeçalho) passa por `scripts/roadmap.py` (ver `SKILL.md`); uma edição direta aqui é sobrescrita sem aviso na próxima regeneração.

# Roadmap — leitura de página (OCR) e sua medição

> Kanban de tracking, segue a metodologia da skill `problem-analysis-roadmap`. Companion: [OCR_ANALYSIS.md](OCR_ANALYSIS.md) — lá está o "porquê" (achados de código, problemas, ideias, síntese causal); aqui fica só o "o quê fazer e em que estado está".
>
> **Regra de sincronização:** os dois documentos usam os mesmos IDs (`A#`, `P#`, `I#`, `S#`) e devem sempre concordar sobre a decisão vigente de cada item.
>
> **Última mudança (2026-10-30):** A nuvem como tier principal (I9) foi revertida: o rate limit do endpoint (A19) faz cada rodada pagar os retries antes do NMT. O I9 volta a Pendente, à espera de um tratamento para o A19.

## Glossário

> Descrição completa de cada um em `OCR_ANALYSIS.md`.

### Em aberto

| ID | Resumo | Status |
| --- | --- | --- |
| **P1** | Lendo mangá no navegador, balões somem ou saem com letra trocada, de forma inconsistente | — |
| **P2** | Balão encostado na borda da tela sai traduzido pela metade, sem aviso | — |
| **P3** | Não dá para verificar se está funcionando sem ocupar a tela real | — |
| **P4** | A tradução sai literal, sem entender a frase nem a fala anterior | — |
| **P5** | Teclas demais, espalhadas, e que tiram F6 e F11 do navegador | — |
| **A2** | O DBNet não gera caixa de linha para balão curto, em nenhuma escala | ⚠️ |
| **A3** | A ampliação de um recorte no mosaico depende das dimensões do mosaico inteiro, acoplando os recortes | ⚠️ |
| **A4** | A escolha entre primeira e segunda leitura usa a confiança do reconhecedor, que não arbitra bem | ⚠️ |
| **A7** | Não há gate de estabilidade: o overlay desenha a primeira leitura que chegar | ⚠️ |
| **A9** | Palavra curta com til decorativo sai errada em resolução nativa | ⚠️ |
| **A10** | O tradutor roda em CPU por incompatibilidade de versão de cuBLAS; correção conhecida e cara | ⚠️ |
| **A11** | A geração seguinte do OCR não é alcançável na versão atual do rapidocr; reavaliar ao subir de versão | ⚠️ |
| **A15** | O contexto de tradução só existe no tier LLM, e na ordem de chegada | ⚠️ |
| **A16** | A ordem padrão dos tiers põe o tradutor mais literal (NMT) na frente; a correção (I9) espera o A19 | ⚠️ |
| **A17** | Seis comandos em teclas de função globais, uma por comando | ⚠️ |
| **A18** | A área selecionada vive só na memória do processo | ⚠️ |
| **A19** | Com a nuvem na frente, cada rodada paga os retries do rate limit antes de cair no NMT | ⚠️ |
| [**S1**](#s1) | Desacoplar a segunda passada de OCR da geometria do mosaico | 🔍 |
| [**S3**](#s3) | Gate de estabilidade: exigir duas leituras iguais antes de desenhar | 💤 |
| [**I5**](#i5) | Coletor de capturas: --collect grava o que o OCR recebeu e o que o app leu e traduziu | ⏳ |
| [**I6**](#i6) | Gabarito por dois professores (PaddleOCR-VL e Baberu OCR) sobre as capturas | ⏳ |
| [**I7**](#i7) | OCR com model_type = server, medido contra o gabarito | 🔍 |
| [**I8**](#i8) | comic-text-detector no lugar do DBNet em ocr_composite.py | 🔍 |
| [**I9**](#i9) | Google gratuito como tradutor principal: tiers = [cloud, nmt] | ⏳ |
| [**I10**](#i10) | TranslateGemma 4B offline, com os balões anteriores como contexto | ⏳ |
| [**I11**](#i11) | Alt+1 liga/desliga, Alt+2 oculta/mostra, Alt+3 seleciona a área | ⏳ |
| [**I12**](#i12) | Persistir a área selecionada entre sessões | ⏳ |
| [**I14**](#i14) | OCR só na faixa que entrou na tela, em vez da tela inteira | 🔍 |

<details>
<summary><strong>Resolvido / descartado / informativo (13 itens — clique pra expandir)</strong></summary>

| ID | Resumo | Status |
| --- | --- | --- |
| **A1** | O reconhecedor roda uma vez na imagem cheia; as regiões do detector só atribuem e filtram | ℹ️ |
| **A5** | O eval não cobrava recall nas vistas de tela (resolvido via S2) | ✅ |
| **A6** | O eval estourava com UnicodeEncodeError com a saída redirecionada (resolvido via S2) | ✅ |
| **A8** | O detector é treinado em mangá/HQ e rende menos fora dessa distribuição | ℹ️ |
| **A12** | A leitura nova substituía a antiga mesmo quando a antiga estava certa (resolvido via I13) | ✅ |
| **A13** | O cache de tradução só acerta com o texto idêntico; a posição agora passa na frente (resolvido via I13) | ✅ |
| **A14** | O balão que saía da tela era descartado e nada guardava o que já foi lido (resolvido via I13) | ✅ |
| [**S2**](#s2) | Eval cobra recall em toda vista, usando a posição gravada de cada balão | ✅ |
| [**I1**](#i1) | Trocar o motor de OCR por outro modelo | 🚫 |
| [**I2**](#i2) | Modo --image: o pipeline lê de um arquivo, sem a tela participar | ✅ |
| [**I3**](#i3) | Modo de leitura (F6): as caixas acompanham a rolagem | ✅ |
| [**I4**](#i4) | Capturar só a janela do navegador em vez da tela inteira | 🚫 |
| [**I13**](#i13) | Registro de balões: posição na tira, casamento por posição e contexto em ordem de leitura | ✅ |

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
| [**S1**](#s1) | Desacoplar a segunda passada de OCR da geometria do mosaico | 🔍 |
| [**I5**](#i5) | Coletor de capturas: --collect grava o que o OCR recebeu e o que o app leu e traduziu | ⏳ |
| [**I6**](#i6) | Gabarito por dois professores (PaddleOCR-VL e Baberu OCR) sobre as capturas | ⏳ |
| [**I7**](#i7) | OCR com model_type = server, medido contra o gabarito | 🔍 |
| [**I8**](#i8) | comic-text-detector no lugar do DBNet em ocr_composite.py | 🔍 |
| [**I14**](#i14) | OCR só na faixa que entrou na tela, em vez da tela inteira | 🔍 |

### Frente 2 — P2

| ID | Resumo | Status |
| --- | --- | --- |
| — | *(nada em aberto)* | — |

### Frente 3 — P3

| ID | Resumo | Status |
| --- | --- | --- |
| — | *(nada em aberto)* | — |

### Frente 4 — P4

| ID | Resumo | Status |
| --- | --- | --- |
| **A15** | O contexto de tradução só existe no tier LLM, e na ordem de chegada | ⚠️ |
| **A16** | A ordem padrão dos tiers põe o tradutor mais literal (NMT) na frente; a correção (I9) espera o A19 | ⚠️ |
| [**I9**](#i9) | Google gratuito como tradutor principal: tiers = [cloud, nmt] | ⏳ |
| [**I10**](#i10) | TranslateGemma 4B offline, com os balões anteriores como contexto | ⏳ |

### Frente 5 — P5

| ID | Resumo | Status |
| --- | --- | --- |
| **A17** | Seis comandos em teclas de função globais, uma por comando | ⚠️ |
| [**I11**](#i11) | Alt+1 liga/desliga, Alt+2 oculta/mostra, Alt+3 seleciona a área | ⏳ |

### Sem frente definida

| ID | Resumo | Status |
| --- | --- | --- |
| **A7** | Não há gate de estabilidade: o overlay desenha a primeira leitura que chegar | ⚠️ |
| **A10** | O tradutor roda em CPU por incompatibilidade de versão de cuBLAS; correção conhecida e cara | ⚠️ |
| **A11** | A geração seguinte do OCR não é alcançável na versão atual do rapidocr; reavaliar ao subir de versão | ⚠️ |
| **A18** | A área selecionada vive só na memória do processo | ⚠️ |
| **A19** | Com a nuvem na frente, cada rodada paga os retries do rate limit antes de cair no NMT | ⚠️ |
| [**S3**](#s3) | Gate de estabilidade: exigir duas leituras iguais antes de desenhar | 💤 |
| [**I12**](#i12) | Persistir a área selecionada entre sessões | ⏳ |

---

## 1. Resolve problema — via Ideia (I#)

| ID | Resumo | Resolve (P#) | A# | Esforço | Risco | Ganho esperado | Custo-benefício | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **I2** | Modo --image: o pipeline lê de um arquivo, sem a tela participar | P3 | — | Médio | Baixo | Alto | Excelente | ✅ Concluído |
| **I3** | Modo de leitura (F6): as caixas acompanham a rolagem | P2 | — | Alto | Médio | Alto | Bom | ✅ Concluído |
| **I5** | Coletor de capturas: --collect grava o que o OCR recebeu e o que o app leu e traduziu | P1 | — | Baixo | Baixo | Alto | Excelente | ⏳ Pendente |
| **I6** | Gabarito por dois professores (PaddleOCR-VL e Baberu OCR) sobre as capturas | P1 | — | Alto | Médio | Alto | Bom | ⏳ Pendente |
| **I9** | Google gratuito como tradutor principal: tiers = [cloud, nmt] | P4 | A16 | Baixo | Baixo | Alto | Excelente | ⏳ Pendente |
| **I10** | TranslateGemma 4B offline, com os balões anteriores como contexto | P4 | A15 | Alto | Médio | Alto | Incerto | ⏳ Pendente |
| **I11** | Alt+1 liga/desliga, Alt+2 oculta/mostra, Alt+3 seleciona a área | P5 | A17 | Médio | Baixo | Médio | Bom | ⏳ Pendente |
| **I13** | Registro de balões: posição na tira, casamento por posição e contexto em ordem de leitura | P1, P4 | A12, A13, A14 | Alto | Médio | Alto | Bom | ✅ Concluído |

<a id="i2"></a>
**I2 — Modo `--image`: o pipeline lê de um arquivo, sem a tela participar.** Resolve P3.

`translatorocr/backends/capture_still.py` (novo): `StillCapture` implementa `CaptureBackend` servindo uma viewport sobre a imagem carregada, com `origin` fixa em (0, 0) — assim os bboxes que saem do pipeline já ficam em coordenada da viewport, que é o que o visualizador desenha e o que o rastreio translada. `translatorocr/ui/viewer.py` (novo): janela comum que desenha a viewport e as caixas **no próprio widget**, e cuja roda do mouse move a viewport virtual. `registry.build_pipeline` e `PipelineWorker` passaram a aceitar um backend de captura pronto; no `App`, o visualizador entra no lugar do overlay por duck typing (mesma interface), então o resto do app não sabe em que modo está.

Decisão tomada durante a implementação: a primeira versão abria a imagem numa janela e deixava o app **fotografar a tela** por cima, o que exercitaria também captura, DPI e os flags Win32 do overlay. Foi descartado a pedido — qualquer janela que passe na frente invalida o teste e prende a máquina. O modo atual não cobre esses três; ficam para a conferência ocasional com o app de verdade e para o `--debug-dump`, que foi mantido justamente por ser a única coisa que mostra o que a captura enxergou.

<a id="i3"></a>
**I3 — Modo de leitura (F6): as caixas acompanham a rolagem.** Resolve P2.

`core/tracker.py` (puro, testável sem GPU nem Qt): `prepare` reduz o quadro a 1/4 e converte para cinza; `estimate_shift` mede o deslocamento por correlação de fase e devolve junto resposta e textura; `shift_blocks` translada as caixas e descarta o que saiu; `merge_tracked` junta a leitura nova com o que sobreviveu à rolagem, com uma exceção que é a razão do modo existir — se o balão novo está cortado e o antigo, no mesmo lugar, foi lido inteiro, vale o antigo. `core/scroll.py` roda o laço a ~16 fps numa thread própria e distingue três situações: nada mudou (conta para "parou"), mudou e é rolagem (translada), mudou e não é rolagem (limpa).

Medições que fixaram os defaults: correlação de fase recupera o deslocamento exato até ~400 px (40% da altura da viewport), com resposta caindo de 0.97 em 60 px para 0.41 em 400 px e 0.01 quando falha; custa 8 ms a 1/4 contra 92 ms em resolução cheia; captura MSS de tela cheia leva 22 ms.

Duas armadilhas pagas aqui. `cv2.phaseCorrelate` **escreve nos arrays que recebe** (aplica a janela de Hanning no lugar), o que corrompia o quadro guardado para a comparação seguinte — resolvido medindo a textura antes e passando cópias. E a resposta da correlação sozinha não basta: uma área totalmente lisa devolve "não andou nada" com resposta 0.99, confiante e errada, o que congelaria as caixas enquanto a página rola; por isso existe o piso de textura.

Pré-requisito que virou parte do item: o overlay precisou sair da captura, senão o laço mediria a rolagem contra as próprias caixas paradas e o OCR releria a tradução em português. Ver o card correspondente.

Não resolve: zoom e troca de página não são translação, e nesses casos o modo limpa em vez de arrastar caixa para o lugar errado.

<a id="i5"></a>
**I5 — Coletor de capturas: --collect grava o que o OCR recebeu e o que o app leu e traduziu.** Resolve P1 no sentido de torná-lo medível com amostra grande, não de corrigi-lo.

Plano: opção `--collect` no `__main__.py`; em `App._on_ready`, a cada rodada do pipeline (a parada da rolagem), grava em `eval/captures/<data>/` a imagem que o OCR recebeu, em webp, mais um JSON com as leituras e traduções do app e o registro de balões (I13). Pula a gravação quando o quadro é quase igual ao anterior (a mesma comparação reduzida do `core/tracker.py`). `eval/captures/` entra no `.gitignore`.

Condição de disparo: depois do registro de balões, que fornece o contexto que o coletor grava.

<a id="i6"></a>
**I6 — Gabarito por dois professores (PaddleOCR-VL e Baberu OCR) sobre as capturas.** Resolve P1 no sentido de dar uma régua com centenas de balões no lugar de ~21.

Plano: `scripts/label_captures.py` como script uv isolado, com dependências inline, para o peso dos modelos não entrar no venv do app. O detector de balão que já existe acha as regiões; cada professor lê cada recorte; os dois concordando (após normalizar caixa e espaço) viram gabarito, os que discordam vão para uma página HTML local de revisão com o recorte e as duas leituras. Grava `labels.json` ao lado das capturas. Conferir na implementação se os dois cabem nos 6 GB de VRAM; se o Baberu não servir, o substituto é um Qwen-VL quantizado.

Condição de disparo: capturas coletadas (I5).

<a id="i9"></a>
**I9 — Google gratuito como tradutor principal: tiers = [cloud, nmt].** Resolve P4 no tier; o contexto entre frases é I10/I13.

Plano: `TranslationConfig.tiers` passa a `["cloud", "nmt"]`, com o opus-mt de reserva offline. Foi aplicado e revertido na mesma sessão: o endpoint gratuito entrou em rate limit (A19) e, com a nuvem na frente, cada rodada esgota as 3 tentativas com backoff antes de ceder ao NMT (12.4 s para 5 blocos, 45.6 s para 25). Antes de reaplicar, o `ChainTranslator` precisa lembrar que a nuvem falhou: depois de um rate limit, vai direto ao NMT por alguns minutos e não grava no cache o que veio do fallback, para a nuvem refazer quando voltar. A `_KEY_VERSION` do cache sobe junto com a troca, porque a chave não distingue o tier e as entradas antigas são do NMT. README, diagrama, banner do console e docstrings de `chain.py` e `translate_cloud.py` acompanham a ordem.

Condição de disparo: o tratamento de A19 pronto, e uma medição de latência com a nuvem respondendo (que não pôde ser feita com o IP bloqueado).

<a id="i10"></a>
**I10 — TranslateGemma 4B offline, com os balões anteriores como contexto.** Resolve P4 e ataca A15 pela raiz: o contexto vem do registro (I13), na ordem de leitura.

Plano: `scripts/eval_translation.py` sorteia ~50 balões das capturas e monta, numa página HTML local, o placar às cegas entre Google, TranslateGemma e opus-mt; as escolhas são gravadas. O modelo roda pelo `llama-cpp-python` do grupo `llm` já existente (GGUF Q4_K_M, ~2,5 GB). Se ganhar ou empatar com o Google, entra como tier com atualização no lugar: a tradução rápida aparece na hora e a do modelo a substitui na mesma caixa, mecanismo que o LLM atual já usa.

Condição de disparo: registro de balões (I13) e capturas (I5) prontos.

<a id="i11"></a>
**I11 — Alt+1 liga/desliga, Alt+2 oculta/mostra, Alt+3 seleciona a área.** Resolve P5.

Plano: `HotkeyConfig` já aceita modificador e dígito em `ui/hotkey.py`. Alt+1 liga e desliga a tradução, e o modo leitura vira o modo único; Alt+2 é o ocultar/mostrar atual; Alt+3 seleciona a área, com a borda aparecendo e sumindo sozinha, e o F7 sai. O F8 e o F10 ficam só na bandeja. Console e README atualizados.

Condição de disparo: depois do OCR medido, para não misturar mudança de uso com mudança de leitura.

<a id="i13"></a>
**I13 — Registro de balões: posição na tira, casamento por posição e contexto em ordem de leitura.** Resolve P1 (a leitura deixa de piscar entre paradas) e prepara P4 (o contexto de tradução existe, mas nenhum tier o consome ainda).

`core/ledger.py` (novo, puro, com lock): `BlockLedger` guarda `Entry` por trecho (`Segment`). A posição é o y da tela menos o deslocamento acumulado, mais a `base` do trecho. O `Pipeline` abre uma `Reading` antes de capturar (`begin`), casa os blocos já passados pelo gate com o registro (`reconcile`) e só manda ao tradutor o que sobra; depois grava o traduzido (`record`). A entrada guardada vale quando tem tradução e o texto é o mesmo, ou quando é inteira e não duvidosa; cede à leitura nova quando estava cortada pela borda ou duvidosa diante de uma leitura limpa. `lost` abre trecho novo; na leitura seguinte, texto igual ao de um trecho antigo no mesmo deslocamento (dois textos, ou um com 12 caracteres ou mais) reancora o antigo. `restore` devolve ao `App._on_scrolled` os balões inteiros do trecho que voltaram à viewport, e eles são redesenhados sem OCR. `context` entrega os últimos 6 balões em ordem de leitura, atravessando os trechos. O registro recomeça quando o título da janela em primeiro plano muda (`ui/foreground.py`, lido a cada leitura) ou passam 600 s sem leitura; `LedgerConfig` reúne os três números. Uma leitura que atravessa um `lost` ou um recomeço não é registrada.

Medido com OCR real sobre duas páginas de `eval/pages`, em cinco paradas de rolagem mais uma volta ao topo: a parada no mesmo lugar traduziu 0 de 5 blocos; as paradas com rolagem traduziram só o que entrou (1 ou 2 blocos por parada). Em 6 paradas por página, o tradutor foi chamado 3 vezes em cada uma (6 no total, contra 12) e recebeu 7 de 25 blocos lidos numa página e 8 de 27 na outra; o único balão cuja tradução mudou entre paradas foi um que estava cortado na borda e depois foi lido inteiro; ao voltar ao topo o registro redesenhou 5 e 6 balões antes de qualquer OCR, e a parada seguinte traduziu 0.

Limites: a leitura ainda roda o OCR na tela inteira a cada parada (I14); o contexto fica sem consumidor até o I10; uma entrada inteira cujo texto difere por completo da leitura nova na mesma posição ainda vale, porque o desenho confia na posição.

---
## 2. Resolve problema — via Síntese (S#)

| ID | Resumo | Resolve (P#) | A# | Esforço | Risco | Ganho esperado | Custo-benefício | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **S2** | Eval cobra recall em toda vista, usando a posição gravada de cada balão | P1, P3 | A5, A6 | Baixo | Baixo | Alto | Excelente | ✅ Concluído |

<a id="s2"></a>
**S2 — Recall cobrado em toda vista de tela.** Resolve P1 no sentido de torná-lo reproduzível e medível, não de corrigi-lo.

`scripts/eval_pages.py`: o JSON de cada página ganhou `boxes`, a posição de cada balão, gerada por `--fit-boxes` (roda o pipeline na página inteira e casa cada bloco com o texto esperado). Um tipo `View` passou a carregar escala, deslocamento e o retângulo do conteúdo, e responde por balão se ele está inteiro, cortado ou fora da vista; o recall é cobrado só sobre os inteiros. Balão cortado é classificado por posição, e não só pela marca `partial` do app, porque na vista simulada o conteúdo começa abaixo de uma faixa de cromo do navegador — o balão é cortado pelo conteúdo sem encostar na borda da imagem. Entrou também uma vista com a página ampliada a 1.3x, já que navegador ampliando é caso real, e `console.setup()` no início do `main()`.

Na primeira execução depois da mudança apareceram falhas que antes passavam verdes: um balão de uma palavra só ausente em 5 das 10 vistas de tela de uma página, e um balão curto lido errado na vista ampliada.

---
## 3. Nice-to-have

| ID | Resumo | A# | Esforço | Risco | Ganho esperado | Custo-benefício | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **S3** | Gate de estabilidade: exigir duas leituras iguais antes de desenhar | A7 | Baixo | Baixo | Baixo | Baixo | 💤 Registrado, sem prioridade |
| **I12** | Persistir a área selecionada entre sessões | A18 | Baixo | Baixo | Baixo | Bom | ⏳ Pendente |

<a id="s3"></a>
**S3 - Exigir leitura repetida antes de desenhar.** Nao endereca nenhum P#: o caso que resolve e texto animado letra por letra, que e jogo, e o foco hoje e manga.

Plano: no modo de leitura, `App._on_ready` passa a comparar o `source` de cada bloco novo com o da rodada anterior na mesma posicao (o casamento por sobreposicao ja existe em `core/tracker.merge_tracked`) e so promove para desenhado o bloco cujo texto saiu igual duas vezes seguidas; enquanto nao sair, mantem o que ja estava. Como o pipeline so roda quando a rolagem para, isso custa uma segunda passada por parada - o gatilho seria um `settled` extra em vez de `mark_read` imediato, ou um `settle_frames` dobrado so quando o gate estiver ligado.

Condicao de disparo: alguem voltar a usar o app em jogo. Enquanto o uso for manga, o custo (dobrar a latencia de cada parada) nao se paga.

<a id="i12"></a>
**I12 — Persistir a área selecionada entre sessões.** Não endereça nenhum P#: é conveniência.

Plano: gravar a `Region` escolhida num arquivo JSON pequeno ao selecionar, e lê-lo em `App.__init__` para preencher `_selected_region`. Um clique sem arrastar (volta à tela cheia) apaga o arquivo.

Condição de disparo: junto da etapa das teclas (I11).

---
## 4. Descartada

| ID | Resumo | A# | Status |
| --- | --- | --- | --- |
| **I1** | Trocar o motor de OCR por outro modelo | — | 🚫 Descartado |
| **I4** | Capturar só a janela do navegador em vez da tela inteira | — | 🚫 Descartado |

<a id="i1"></a>
**I1 — Trocar o motor de OCR: medido e pior.** Medido contra o vizinho imediato dentro do mesmo pacote (a geracao anterior do mesmo detector+reconhecedor): nas tres paginas inteiras ele le 17/21 baloes exatos contra 19/21 do atual, perde um balao numa pagina e inventa letra em outra. Alem disso a troca nao toca no estagio que falha: o reconhecedor atual le o texto certo quando recebe o recorte da regiao (A2), e quem nao produz caixa e o detector de linha. Trocar de modelo mudaria o reconhecedor, nao o DBNet.

Reavaliar so se aparecer um pacote que exponha um detector de linha diferente, nao um reconhecedor diferente.

<a id="i4"></a>
**I4 — Capturar só a janela: desnecessário e mais caro.** Tres argumentos, em ordem de peso. Primeiro, nao e necessario: medido nesta maquina, SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE) tira o overlay da captura (de 15.7% da area para 0.0%) mantendo a translucidez e o click-through, entao o problema que a ideia resolveria ja esta resolvido de graca. Segundo, a variante barata nao funciona: BitBlt sobre o DC de uma janela le a mesma area composta da tela, entao o overlay continuaria na foto. Terceiro, a variante que funciona e cara: PrintWindow com PW_RENDERFULLCONTENT costuma voltar preto em navegador acelerado por GPU, e Windows.Graphics.Capture exige dependencia WinRT nova mais uma UI para escolher a janela, trocando "traduz o que estiver na tela" por "traduz aquela janela".

Reavaliar se a exclusao de captura falhar em alguma maquina: e o plano B natural.

---
## 5. Incerta / exploratória

| ID | Resumo | Conexão | Status |
| --- | --- | --- | --- |
| **S1** | Desacoplar a segunda passada de OCR da geometria do mosaico | P1; A2, A3, A4, A9; I6, I8 | 🔍 Em avaliação |
| **I7** | OCR com model_type = server, medido contra o gabarito | P1; A2, A9 | 🔍 Em avaliação |
| **I8** | comic-text-detector no lugar do DBNet em ocr_composite.py | P1; A2, A3, A9 | 🔍 Em avaliação |
| **I14** | OCR só na faixa que entrou na tela, em vez da tela inteira | P1; A14 | 🔍 Em avaliação |

<a id="s1"></a>
**S1 — o que falta definir:** Falta escolher o mecanismo. O que já foi medido e **não** serviu: (a) igualar a largura de todos os recortes antes de empilhar — recupera um balão curto a 65% e elimina o lixo que ele gerava, mas faz um balão que estava certo na página inteira passar a sair com letra trocada, empatando no total de vistas com falha; (b) fixar a largura do mosaico em 736 px para o DBNet não reescalar nada — piorou de 8 para 12 vistas com falha, porque a ampliação necessária vira borrão; (c) reconhecer cada região suspeita numa chamada isolada, dando a cada uma a ampliação de ~9x que ela teria sozinha — recupera dois casos que falhavam mas devolve leitura vazia em outros, e custa 137–529 ms contra ~150 ms do mosaico.

Três coisas precisam ser decididas antes de isto virar Pendente: qual mecanismo de desacoplamento (isolar por chamada, agrupar recortes por faixa de tamanho, ou outro); como arbitrar entre a primeira leitura e a segunda sem depender da confiança do reconhecedor (A4), já que hoje uma leitura confiante e errada ganha de uma correta; e qual orçamento de tempo é aceitável, dado que o desenho atual existe justamente para não pagar uma chamada por região (A1).

Condição de disparo: o gabarito (I6) e o teste do comic-text-detector (I8). Se o detector achar os balões curtos, esta síntese é descartada; se não, o gabarito dá a amostra que faltava para medir o mecanismo escolhido sem o número oscilar por conta de uma página só.

<a id="i7"></a>
**I7 — OCR com model_type = server, medido contra o gabarito.** Falta o gabarito (I6) para o número valer: com ~21 balões o resultado oscila. O experimento em si é uma linha de configuração (`OCRConfig.model_type`); o que falta é decidir o critério de aceite (recall, exatidão e CER do baseline, com tamanho da amostra) e o custo de VRAM e de tempo que se aceita pagar.

<a id="i8"></a>
**I8 — comic-text-detector no lugar do DBNet em ocr_composite.py.** Falta medir se ele acha os balões curtos e as linhas com til que o DBNet perde (A2, A9), e se acha sem depender da geometria do mosaico (A3). Falta também decidir o formato de integração: o modelo é um detector, então o reconhecedor do RapidOCR precisaria receber as caixas dele, e `ocr_composite.py` já lida com atribuição por região. Se der certo, a segunda passada em mosaico sai e S1 é descartada; se não, vira Descartada com a medição.

<a id="i14"></a>
**I14 — OCR só na faixa que entrou na tela, em vez da tela inteira.** Falta definir o tratamento do balão cortado na fronteira da faixa: ou a faixa ganha uma margem que cobre um balão inteiro, ou o balão de fronteira é relido pela tela toda. Falta também medir o ganho de GPU, que depende de a rolagem típica ser curta. Depende do registro de balões (I13).
