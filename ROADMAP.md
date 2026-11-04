<!-- ARQUIVO GERADO POR scripts/roadmap.py (skill problem-analysis-roadmap) -- NÃO EDITAR À MÃO. -->

> ⚠️ **Este arquivo é gerado automaticamente — não edite manualmente.** Toda mudança (inserir/mover/concluir/descartar/remover um card, cadastrar ou atualizar um achado/problema, o cabeçalho) passa por `scripts/roadmap.py` (ver `SKILL.md`); uma edição direta aqui é sobrescrita sem aviso na próxima regeneração.

# Roadmap — leitura de página (OCR) e sua medição

> Kanban de tracking, segue a metodologia da skill `problem-analysis-roadmap`. Companion: [OCR_ANALYSIS.md](OCR_ANALYSIS.md) — lá está o "porquê" (achados de código, problemas, ideias, síntese causal); aqui fica só o "o quê fazer e em que estado está".
>
> **Regra de sincronização:** os dois documentos usam os mesmos IDs (`A#`, `P#`, `I#`, `S#`) e devem sempre concordar sobre a decisão vigente de cada item.
>
> **Última mudança (2026-11-04):** Régua eval_captures.py com a linha de base do app (I6); modelo server do RapidOCR medido e descartado (I7).

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
| [**S1**](#s1) | Desacoplar a segunda passada de OCR da geometria do mosaico | 🔍 |
| [**S3**](#s3) | Gate de estabilidade: exigir duas leituras iguais antes de desenhar | 💤 |
| [**I8**](#i8) | comic-text-detector no lugar do DBNet em ocr_composite.py | 🔍 |
| [**I14**](#i14) | OCR só na faixa que entrou na tela, em vez da tela inteira | 🔍 |
| [**I15**](#i15) | Recompilar o llama-cpp-python para GPU sem tensor cores (MMQ, arquiteturas 61/80 virtuais) | 💤 |

<details>
<summary><strong>Resolvido / descartado / informativo (26 itens — clique pra expandir)</strong></summary>

| ID | Resumo | Status |
| --- | --- | --- |
| **A1** | O reconhecedor roda uma vez na imagem cheia; as regiões do detector só atribuem e filtram | ℹ️ |
| **A5** | O eval não cobrava recall nas vistas de tela (resolvido via S2) | ✅ |
| **A6** | O eval estourava com UnicodeEncodeError com a saída redirecionada (resolvido via S2) | ✅ |
| **A8** | O detector é treinado em mangá/HQ e rende menos fora dessa distribuição | ℹ️ |
| **A12** | A leitura nova substituía a antiga mesmo quando a antiga estava certa (resolvido via I13) | ✅ |
| **A13** | O cache de tradução só acerta com o texto idêntico; a posição agora passa na frente (resolvido via I13) | ✅ |
| **A14** | O balão que saía da tela era descartado e nada guardava o que já foi lido (resolvido via I13) | ✅ |
| **A15** | O contexto de tradução só existia no tier LLM, e na ordem de chegada (resolvido via I10) | ✅ |
| **A16** | O tradutor mais literal era o único que respondia (resolvido via I10) | ✅ |
| **A17** | Seis comandos em teclas de função globais, uma por comando | ✅ |
| **A18** | A área selecionada vive só na memória do processo | ✅ |
| **A19** | Com a nuvem na frente, cada rodada pagava os retries antes de cair no NMT (encerrado com a remoção da nuvem) | ✅ |
| **A20** | A nuvem não tinha timeout de rede (encerrado com a remoção da nuvem) | ✅ |
| [**S2**](#s2) | Eval cobra recall em toda vista, usando a posição gravada de cada balão | ✅ |
| [**I1**](#i1) | Trocar o motor de OCR por outro modelo | 🚫 |
| [**I2**](#i2) | Modo --image: o pipeline lê de um arquivo, sem a tela participar | ✅ |
| [**I3**](#i3) | Modo de leitura: as caixas acompanham a rolagem | ✅ |
| [**I4**](#i4) | Capturar só a janela do navegador em vez da tela inteira | 🚫 |
| [**I5**](#i5) | Coletor de capturas: --collect grava o que o OCR recebeu e o que o app leu e traduziu | ✅ |
| [**I6**](#i6) | Gabarito por dois leitores (Baberu OCR e Qwen2.5-VL) sobre as capturas | ✅ |
| [**I7**](#i7) | OCR com model_type = server, medido contra o gabarito | 🚫 |
| [**I9**](#i9) | Google gratuito como tradutor principal: tiers = [cloud, nmt] | 🚫 |
| [**I10**](#i10) | TranslateGemma 4B como segunda passada, com os balões anteriores como contexto | ✅ |
| [**I11**](#i11) | F8 liga/desliga, F9 oculta/mostra, F4 seleciona a área | ✅ |
| [**I12**](#i12) | Persistir a área selecionada entre sessões | ✅ |
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
| — | *(nada em aberto)* | — |

### Frente 5 — P5

| ID | Resumo | Status |
| --- | --- | --- |
| — | *(nada em aberto)* | — |

### Sem frente definida

| ID | Resumo | Status |
| --- | --- | --- |
| **A7** | Não há gate de estabilidade: o overlay desenha a primeira leitura que chegar | ⚠️ |
| **A10** | O tradutor roda em CPU por incompatibilidade de versão de cuBLAS; correção conhecida e cara | ⚠️ |
| **A11** | A geração seguinte do OCR não é alcançável na versão atual do rapidocr; reavaliar ao subir de versão | ⚠️ |
| **A21** | A segunda passada é dezenas de vezes mais lenta que o opus-mt, numa fila FIFO; a GPU não tem tensor cores | ⚠️ |
| [**S3**](#s3) | Gate de estabilidade: exigir duas leituras iguais antes de desenhar | 💤 |
| [**I15**](#i15) | Recompilar o llama-cpp-python para GPU sem tensor cores (MMQ, arquiteturas 61/80 virtuais) | 💤 |

---

## 1. Resolve problema — via Ideia (I#)

| ID | Resumo | Resolve (P#) | A# | Esforço | Risco | Ganho esperado | Custo-benefício | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **I2** | Modo --image: o pipeline lê de um arquivo, sem a tela participar | P3 | — | Médio | Baixo | Alto | Excelente | ✅ Concluído |
| **I3** | Modo de leitura: as caixas acompanham a rolagem | P2 | — | Alto | Médio | Alto | Bom | ✅ Concluído |
| **I5** | Coletor de capturas: --collect grava o que o OCR recebeu e o que o app leu e traduziu | P1 | — | Baixo | Baixo | Alto | Excelente | ✅ Concluído |
| **I6** | Gabarito por dois leitores (Baberu OCR e Qwen2.5-VL) sobre as capturas | P1 | — | Alto | Médio | Alto | Bom | ✅ Concluído |
| **I10** | TranslateGemma 4B como segunda passada, com os balões anteriores como contexto | P4 | A15, A16 | Alto | Médio | Médio | Bom | ✅ Concluído |
| **I11** | F8 liga/desliga, F9 oculta/mostra, F4 seleciona a área | P5 | A17 | Médio | Baixo | Médio | Bom | ✅ Concluído |
| **I13** | Registro de balões: posição na tira, casamento por posição e contexto em ordem de leitura | P1, P4 | A12, A13, A14 | Alto | Médio | Alto | Bom | ✅ Concluído |

<a id="i2"></a>
**I2 — Modo `--image`: o pipeline lê de um arquivo, sem a tela participar.** Resolve P3.

`translatorocr/backends/capture_still.py` (novo): `StillCapture` implementa `CaptureBackend` servindo uma viewport sobre a imagem carregada, com `origin` fixa em (0, 0) — assim os bboxes que saem do pipeline já ficam em coordenada da viewport, que é o que o visualizador desenha e o que o rastreio translada. `translatorocr/ui/viewer.py` (novo): janela comum que desenha a viewport e as caixas **no próprio widget**, e cuja roda do mouse move a viewport virtual. `registry.build_pipeline` e `PipelineWorker` passaram a aceitar um backend de captura pronto; no `App`, o visualizador entra no lugar do overlay por duck typing (mesma interface), então o resto do app não sabe em que modo está.

Decisão tomada durante a implementação: a primeira versão abria a imagem numa janela e deixava o app **fotografar a tela** por cima, o que exercitaria também captura, DPI e os flags Win32 do overlay. Foi descartado a pedido — qualquer janela que passe na frente invalida o teste e prende a máquina. O modo atual não cobre esses três; ficam para a conferência ocasional com o app de verdade e para o `--debug-dump`, que foi mantido justamente por ser a única coisa que mostra o que a captura enxergou.

<a id="i3"></a>
**I3 — Modo de leitura: as caixas acompanham a rolagem.** Resolve P2.

`core/tracker.py` (puro, testável sem GPU nem Qt): `prepare` reduz o quadro a 1/4 e converte para cinza; `estimate_shift` mede o deslocamento por correlação de fase e devolve junto resposta e textura; `shift_blocks` translada as caixas e descarta o que saiu. Depois de cada leitura, a tela é o que ela achou mais o que o registro de balões (I13) guarda e ela não cobriu — é o registro que mantém o balão lido inteiro quando a leitura nova vem cortada pela borda. `core/scroll.py` roda o laço a ~16 fps numa thread própria e distingue três situações: nada mudou (conta para "parou"), mudou e é rolagem (translada), mudou e não é rolagem (limpa).

Medições que fixaram os defaults: correlação de fase recupera o deslocamento exato até ~400 px (40% da altura da viewport), com resposta caindo de 0.97 em 60 px para 0.41 em 400 px e 0.01 quando falha; custa 8 ms a 1/4 contra 92 ms em resolução cheia; captura MSS de tela cheia leva 22 ms.

Quatro armadilhas pagas aqui. `cv2.phaseCorrelate` **escreve nos arrays que recebe** (aplica a janela de Hanning no lugar), o que corrompia o quadro guardado para a comparação seguinte — resolvido medindo a textura antes e passando cópias. E a resposta da correlação sozinha não basta: uma área totalmente lisa devolve "não andou nada" com resposta 0.99, confiante e errada, o que congelaria as caixas enquanto a página rola; por isso existe o piso de textura. A correlação é cíclica: rolando rápido, um salto perto de meia altura volta com o sinal trocado e resposta alta, e as caixas e o registro pulavam uma tela inteira para o lado errado (os balões fantasmas que acompanham a rolagem); `ScrollConfig.max_dy` (0.35 da altura) recusa esses saltos, medido sem nenhuma medida errada aceita em regiões de 600 e 1000 px, contra 10 com 0.40 na de 600. E o `mss` guardado em `threading.local` era recriado a cada quadro, porque cada slot da `QThread` chega com estado de thread novo, e nunca fechado, até o limite de 10 mil objetos GDI do Windows; o `MSSCapture` agora guarda o seu num atributo e o reusa.

A parada só dispara uma leitura se houve movimento desde a anterior: `settled` consome a marca de movimento, e uma parada que chega durante uma leitura (ou uma falha) vira leitura assim que ela termina.

Pré-requisito que virou parte do item: o overlay precisou sair da captura, senão o laço mediria a rolagem contra as próprias caixas paradas e o OCR releria a tradução em português. Ver o card correspondente.

Não resolve: zoom e troca de página não são translação, e nesses casos o modo limpa em vez de arrastar caixa para o lugar errado.

<a id="i5"></a>
**I5 — Coletor de capturas: --collect grava o que o OCR recebeu e o que o app leu e traduziu.** Dá amostra real, no recorte que o app recebe, para I6, I7, I8 e I10.

`core/collector.py` (novo): `CaptureCollector.save` grava `eval/captures/<data>/<hora>.webp` e um `.json` ao lado, com o bbox de cada balão em coordenada da imagem, texto, tradução, confiança, `needs_review`, `partial`, `new` (traduzido nesta rodada) e `context` (as falas anteriores em ordem de leitura, vindas de `BlockLedger.context`, só nos balões novos). Tela com diferença média de cinza abaixo de 2.0 para a última gravada é pulada. Falha de disco vira aviso e a leitura segue. Entrou em `Pipeline.run`, e não em `App._on_ready` como planejado, porque a imagem entregue ao OCR só existe ali. A pasta fica separada de `eval/pages/` e fora do versionamento.

Medido com OCR real numa página de `eval/pages`, em 4 paradas: 3 telas gravadas (a parada no mesmo lugar foi pulada), ~65 KB por tela, ~0.1 s por gravação, com contexto de 0 a 6 falas. A gravação roda na thread do worker antes de o resultado ir para a tela, então soma esse 0.1 s à latência, só com `--collect`.

<a id="i6"></a>
**I6 — Gabarito por dois leitores (Baberu OCR e Qwen2.5-VL) sobre as capturas.** Resolve P1 no sentido de dar uma régua com centenas de balões no lugar de ~21.

`scripts/label_captures.py` roda o detector de balão sobre cada tela de `eval/captures/<data>/`, e dois leitores leem cada região: Baberu OCR e Qwen2.5-VL-3B. Quando as duas leituras são iguais depois de normalizar caixa, pontuação e espaço, a região vira gabarito. Quando diferem, vai para uma página HTML local, onde o usuário escolhe ou corrige. Região que encosta na borda da tela fica marcada como cortada e não é lida. Tudo vai para `labels.json`, ao lado das capturas.

Resultado em 199 telas: 307 regiões, das quais 54 cortadas pela borda e 253 lidas. Das 253, os dois leitores concordaram em 224 (89%), 11 eram vazias, 17 foram revisadas à mão e 1 foi rejeitada. Pendentes: 0.

A régua é `scripts/eval_captures.py`: passa cada tela pelo OCR, agrupamento e portão do app e casa os blocos com as regiões do gabarito. Por região mede achado (algum bloco caiu nela), exato (texto igual ao do gabarito depois de normalizar caixa e pontuação) e CER (fração de caracteres errados: 0.05 é um erro a cada 20 letras; região não achada conta 1.0). `--save` e `--against` comparam duas rodadas região a região. Linha de base do app (`mobile`), 241 regiões com texto (151 textos distintos, porque o mesmo balão aparece em várias telas da rolagem), 222 ms de OCR por tela: balões de fala, 209 de 210 achados, 192 de 210 exatos, CER médio 0.024; texto solto (quase sempre onomatopeia), 29 de 31 achados, 11 de 31 exatos, CER médio 0.341. Nenhum bloco caiu fora de região com texto.

Limite: o inglês do Baberu foi destilado do PaddleOCR-VL, então os dois leitores não são de todo independentes. O Qwen-VL é de outra família, e é ele que segura a concordância. E as regiões vêm do detector de balão do próprio app, então balão que ele não acha não aparece na régua.

<a id="i10"></a>
**I10 — TranslateGemma 4B como segunda passada, com os balões anteriores como contexto.** Resolve P4 e ataca A15 pela raiz: o contexto vem do registro (I13), na ordem de leitura.

Com a nuvem descartada (I9), a comparação às cegas de `scripts/eval_translation.py` ficou entre o opus-mt e o TranslateGemma com contexto, em 89 balões das capturas. Erro grave (sentido trocado ou perdido): opus-mt 11 de 89 (12%), TranslateGemma com contexto 8 de 89 (9%). O custo foi o tempo: 2.6 s por balão contra 0.13 s.

Por isso o modelo entrou como segunda passada, sem tirar o opus-mt da frente. `backends/translate_gemma.py` (`GemmaTranslator`) roda o GGUF pelo `llama-cpp-python` com um prompt cru e guarda o resultado no cache sob o backend `gemma`. Só balão novo com 2 palavras ou mais entra na fila de refino do `Pipeline`. O worker refina um balão por volta do laço (`QTimer.singleShot(0)`), então uma captura nova passa na frente da fila. O contexto vem do registro (I13): os balões anteriores, em ordem de leitura. Quando um refino termina, o registro redesenha a caixa com o texto novo.

Verificado com o app real sobre uma página de `eval/pages`: a fila intercala com as capturas, o contexto se acumula e a caixa continua alinhada depois de rolar. Pico de VRAM: 5.56 de 6.14 GB na GTX 1660 SUPER, com detector, OCR e os dois tradutores carregados.

Limites: a lentidão e a fila em ordem de chegada (A21). O `llama-cpp-python` fica no grupo opcional `llm`, porque não há wheel CUDA para Windows e a instalação compila. Sem o grupo, o app segue só com o opus-mt e avisa no console como instalar.

<a id="i11"></a>
**I11 — F8 liga/desliga, F9 oculta/mostra, F4 seleciona a área.** Resolve P5 e A17.

`HotkeyConfig` ficou com três teclas: F8, F9 e F4. A primeira versão usava Alt+1/2/3, mas soltar o Alt abria o menu do Firefox. O modo leitura virou o modo único: F8 liga a tradução, e a primeira leitura sai sem precisar rolar. "Traduzir uma vez" e "Sair" ficaram só na bandeja, com `Command.key` opcional, e o clique simples no ícone liga e desliga a tradução. O F7 saiu: a borda da área aparece por 3 s ao selecionar e ao ligar a tradução, e some sozinha. Trocar a área com a tradução ligada agora dispara uma leitura, porque o rastreio só pedia leitura depois de movimento.

Verificado com o app real: as três teclas registradas no Windows, menu e ajuda do console certos, borda presente logo depois de selecionar e ausente depois de 3.4 s, e leitura disparada ao ligar sobre uma página de `eval/pages`.

<a id="i13"></a>
**I13 — Registro de balões: posição na tira, casamento por posição e contexto em ordem de leitura.** Resolve P1 (a leitura deixa de piscar entre paradas) e serve P4: é dele que sai o contexto da segunda passada (I10).

`core/ledger.py` (novo, puro, com lock): `BlockLedger` guarda `Entry` por trecho (`Segment`). A posição é o y da tela menos o deslocamento acumulado, mais a `base` do trecho. O `Pipeline` abre uma `Reading` antes de capturar (`begin`), casa os blocos já passados pelo gate com o registro (`reconcile`) e só manda ao tradutor o que sobra; depois grava o traduzido (`record`). A entrada guardada vale quando tem tradução e o texto é o mesmo, ou quando é inteira e não duvidosa; cede à leitura nova quando estava cortada pela borda ou duvidosa diante de uma leitura limpa. `lost` abre trecho novo; na leitura seguinte, texto igual ao de um trecho antigo no mesmo deslocamento (dois textos, ou um com 12 caracteres ou mais) reancora o antigo. `restore` devolve ao `App._on_scrolled` os balões inteiros do trecho que voltaram à viewport, e eles são redesenhados sem OCR. `context` entrega os últimos 6 balões em ordem de leitura, atravessando os trechos. O registro recomeça quando o título da janela em primeiro plano muda (`ui/foreground.py`, lido a cada leitura) ou passam 600 s sem leitura; `LedgerConfig` reúne os três números. Uma leitura que atravessa um `lost` ou um recomeço não é registrada. A entrada que cabe inteira na área capturada e que a leitura não achou conta uma falta; com `LedgerConfig.max_misses` (2) seguidas ela sai do registro, e um acerto zera a conta — é o que tira da tela o balão que não tem texto embaixo. Depois de cada leitura o `App._on_ready` monta a tela com o que ela achou mais o `restore` do registro, então a tela e o registro concordam sobre quais balões valem.

Medido com OCR real sobre duas páginas de `eval/pages`, em cinco paradas de rolagem mais uma volta ao topo: a parada no mesmo lugar traduziu 0 de 5 blocos; as paradas com rolagem traduziram só o que entrou (1 ou 2 blocos por parada). Em 6 paradas por página, o tradutor foi chamado 3 vezes em cada uma (6 no total, contra 12) e recebeu 7 de 25 blocos lidos numa página e 8 de 27 na outra; o único balão cuja tradução mudou entre paradas foi um que estava cortado na borda e depois foi lido inteiro; ao voltar ao topo o registro redesenhou 5 e 6 balões antes de qualquer OCR, e a parada seguinte traduziu 0.

Limites: a leitura ainda roda o OCR na tela inteira a cada parada (I14); uma entrada inteira cujo texto difere por completo da leitura nova na mesma posição ainda vale, porque o desenho confia na posição.

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
| **I12** | Persistir a área selecionada entre sessões | A18 | Baixo | Baixo | Baixo | Bom | ✅ Concluído |
| **I15** | Recompilar o llama-cpp-python para GPU sem tensor cores (MMQ, arquiteturas 61/80 virtuais) | A21 | Baixo | Baixo | Incerto | Bom | 💤 Registrado, sem prioridade |

<a id="s3"></a>
**S3 - Exigir leitura repetida antes de desenhar.** Nao endereca nenhum P#: o caso que resolve e texto animado letra por letra, que e jogo, e o foco hoje e manga.

Plano: no modo de leitura, `App._on_ready` passa a comparar o `source` de cada bloco novo com o da rodada anterior na mesma posicao (o casamento por posicao ja existe em `BlockLedger._match`, e a `Entry` ja conta leituras seguidas em `misses`) e so promove para desenhado o bloco cujo texto saiu igual duas vezes seguidas; enquanto nao sair, mantem o que ja estava. Como o pipeline so roda quando a rolagem para, e `ScrollTracker.settled` so dispara uma vez por parada, isso custa uma segunda passada por parada - o gatilho seria pedir uma leitura extra ao fim da primeira, ou um `settle_frames` dobrado so quando o gate estiver ligado.

Condicao de disparo: alguem voltar a usar o app em jogo. Enquanto o uso for manga, o custo (dobrar a latencia de cada parada) nao se paga.

<a id="i12"></a>
**I12 — Persistir a área selecionada entre sessões.** Resolve A18.

`ui/area_store.py` (novo) grava a área em `area.json`, fora do versionamento, e a restaura ao abrir. Arquivo ausente ou corrompido vale como tela cheia. Área fora da tela atual também, mas o arquivo fica, para voltar quando o app abrir no monitor dela. O clique sem arrastar apaga o arquivo. No `--image` a área não se aplica. Verificado com o app real: área restaurada ao abrir, regravada ao selecionar e apagada ao voltar à tela cheia.

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

| ID | Resumo | A# | Status |
| --- | --- | --- | --- |
| **I1** | Trocar o motor de OCR por outro modelo | — | 🚫 Descartado |
| **I4** | Capturar só a janela do navegador em vez da tela inteira | — | 🚫 Descartado |
| **I9** | Google gratuito como tradutor principal: tiers = [cloud, nmt] | A16, A19 | 🚫 Descartado |
| **I7** | OCR com model_type = server, medido contra o gabarito | A2, A9 | 🚫 Descartado |

<a id="i1"></a>
**I1 — Trocar o motor de OCR: medido e pior.** Medido contra o vizinho imediato dentro do mesmo pacote (a geracao anterior do mesmo detector+reconhecedor): nas tres paginas inteiras ele le 17/21 baloes exatos contra 19/21 do atual, perde um balao numa pagina e inventa letra em outra. Alem disso a troca nao toca no estagio que falha: o reconhecedor atual le o texto certo quando recebe o recorte da regiao (A2), e quem nao produz caixa e o detector de linha. Trocar de modelo mudaria o reconhecedor, nao o DBNet.

Reavaliar so se aparecer um pacote que exponha um detector de linha diferente, nao um reconhecedor diferente.

<a id="i4"></a>
**I4 — Capturar só a janela: desnecessário e mais caro.** Tres argumentos, em ordem de peso. Primeiro, nao e necessario: medido nesta maquina, SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE) tira o overlay da captura (de 15.7% da area para 0.0%) mantendo a translucidez e o click-through, entao o problema que a ideia resolveria ja esta resolvido de graca. Segundo, a variante barata nao funciona: BitBlt sobre o DC de uma janela le a mesma area composta da tela, entao o overlay continuaria na foto. Terceiro, a variante que funciona e cara: PrintWindow com PW_RENDERFULLCONTENT costuma voltar preto em navegador acelerado por GPU, e Windows.Graphics.Capture exige dependencia WinRT nova mais uma UI para escolher a janela, trocando "traduz o que estiver na tela" por "traduz aquela janela".

Reavaliar se a exclusao de captura falhar em alguma maquina: e o plano B natural.

<a id="i9"></a>
**I9 — Descartado.** 🚫 Chegou a ser implementada, mas o endpoint gratuito do Google bloqueou o IP já no primeiro pedido (429), e o usuário quer uso ilimitado, sem depender de cota de terceiro. A nuvem não tinha como entregar isso, nem com a pausa de A19. O código da nuvem foi removido, e a tradução ficou 100% local: o opus-mt na frente e o TranslateGemma como segunda passada (I10).

<a id="i7"></a>
**I7 — Descartado.** 🚫 Medido com `scripts/eval_captures.py` em 199 telas, 210 regiões de balão de fala e 31 de texto solto, contra a linha de base `mobile` (192 de 210 balões exatos, 222 ms por tela). O PP-OCRv5 do RapidOCR só tem modelo `server` em chinês: o reconhecedor `server` em inglês não existe, e o chinês lê as letras certas mas tira o espaço entre palavras curtas, 144 de 210 balões exatos, inútil para o tradutor. O detector `server` sozinho sobe as onomatopeias (11 para 18 de 31 exatas), mas nos balões, que são o que se lê, cai de 192 para 188 exatos: some palavra curta e uma ou outra linha sai lida de cabeça para baixo. E custa 553 ms por tela, 2,5 vezes o `mobile`. Os dois juntos: 170 de 210, 739 ms. Nenhuma combinação melhora o balão de fala, e todas custam mais.

---
## 5. Incerta / exploratória

| ID | Resumo | Conexão | Status |
| --- | --- | --- | --- |
| **S1** | Desacoplar a segunda passada de OCR da geometria do mosaico | P1; A2, A3, A4, A9; I6, I8 | 🔍 Em avaliação |
| **I8** | comic-text-detector no lugar do DBNet em ocr_composite.py | P1; A2, A3, A9 | 🔍 Em avaliação |
| **I14** | OCR só na faixa que entrou na tela, em vez da tela inteira | P1; A14 | 🔍 Em avaliação |

<a id="s1"></a>
**S1 — o que falta definir:** Falta escolher o mecanismo. O que já foi medido e **não** serviu: (a) igualar a largura de todos os recortes antes de empilhar — recupera um balão curto a 65% e elimina o lixo que ele gerava, mas faz um balão que estava certo na página inteira passar a sair com letra trocada, empatando no total de vistas com falha; (b) fixar a largura do mosaico em 736 px para o DBNet não reescalar nada — piorou de 8 para 12 vistas com falha, porque a ampliação necessária vira borrão; (c) reconhecer cada região suspeita numa chamada isolada, dando a cada uma a ampliação de ~9x que ela teria sozinha — recupera dois casos que falhavam mas devolve leitura vazia em outros, e custa 137–529 ms contra ~150 ms do mosaico.

Três coisas precisam ser decididas antes de isto virar Pendente: qual mecanismo de desacoplamento (isolar por chamada, agrupar recortes por faixa de tamanho, ou outro); como arbitrar entre a primeira leitura e a segunda sem depender da confiança do reconhecedor (A4), já que hoje uma leitura confiante e errada ganha de uma correta; e qual orçamento de tempo é aceitável, dado que o desenho atual existe justamente para não pagar uma chamada por região (A1).

Condição de disparo: o gabarito (I6) e o teste do comic-text-detector (I8). Se o detector achar os balões curtos, esta síntese é descartada; se não, o gabarito dá a amostra que faltava para medir o mecanismo escolhido sem o número oscilar por conta de uma página só.

<a id="i8"></a>
**I8 — comic-text-detector no lugar do DBNet em ocr_composite.py.** Falta medir se ele acha os balões curtos e as linhas com til que o DBNet perde (A2, A9), e se acha sem depender da geometria do mosaico (A3). Falta também decidir o formato de integração: o modelo é um detector, então o reconhecedor do RapidOCR precisaria receber as caixas dele, e `ocr_composite.py` já lida com atribuição por região. Se der certo, a segunda passada em mosaico sai e S1 é descartada; se não, vira Descartada com a medição.

<a id="i14"></a>
**I14 — OCR só na faixa que entrou na tela, em vez da tela inteira.** Falta definir o tratamento do balão cortado na fronteira da faixa: ou a faixa ganha uma margem que cobre um balão inteiro, ou o balão de fronteira é relido pela tela toda. Falta também medir o ganho de GPU, que depende de a rolagem típica ser curta. Depende do registro de balões (I13).
