<!-- MANTIDO POR scripts/roadmap.py (skill problem-analysis-roadmap) -- entradas chegam só pelo comando `archive`. -->

# Arquivo morto — Roadmap — leitura de página (OCR) e sua medição

> Itens encerrados que saíram de [OCR_ANALYSIS.md](OCR_ANALYSIS.md) e do roadmap pelo comando `archive`, com o bloco da análise e o card do kanban como estavam: ideias e sínteses concluídas ou descartadas, achados resolvidos ou descartados, problemas que o usuário deu por fechados. O argumento de cada descarte mora aqui: uma ideia nova é procurada neste arquivo antes de ser proposta.

### A5 · arquivado em 2026-11-04

*Glossário:* O eval não cobrava recall nas vistas de tela (resolvido via S2) · ✅

**A5 — O eval não cobrava recall nas vistas de tela**
`scripts/eval_pages.py`. Só a página inteira cobrava "achou todos os balões"; nas vistas de tela o script apontava apenas lixo e duplicata, porque não tinha como distinguir "o OCR perdeu o balão" de "o balão está fora da viewport". Consequência: uma regressão de leitura em escala de tela passava como verde.
✅ **Resolvido via S2 — o JSON de cada página passou a guardar a posição de cada balão, e o script cobra os que cabem inteiros na vista.**

### A6 · arquivado em 2026-11-04

*Glossário:* O eval estourava com UnicodeEncodeError com a saída redirecionada (resolvido via S2) · ✅

**A6 — O eval estourava com a saída redirecionada**
`scripts/eval_pages.py` imprimia seta e acentos sem preparar o console; em cp1252 isso levanta `UnicodeEncodeError` e derruba a execução no meio.
✅ **Resolvido via S2 — passou a chamar `ui/console.setup()`, o mesmo tratamento do app.**

### A12 · arquivado em 2026-11-04

*Glossário:* A leitura nova substituía a antiga mesmo quando a antiga estava certa (resolvido via I13) · ✅

**A12 — A leitura nova substitui a antiga mesmo quando a antiga estava certa**
Na junção do que sobreviveu à rolagem com o que acabou de ser lido, a leitura nova manda; a única exceção é o balão novo cortado pela borda diante de um antigo lido inteiro. Um balão antigo lido certo, relido agora com uma letra trocada, vira a leitura trocada, e a tradução já desenhada muda junto.
✅ **Resolvido via I13 — o registro mantém a primeira leitura inteira de cada balão, e a tela depois de cada leitura é montada a partir dele.**

### A13 · arquivado em 2026-11-04

*Glossário:* O cache de tradução só acerta com o texto idêntico; a posição agora passa na frente (resolvido via I13) · ✅

**A13 — O cache de tradução só acerta com o texto idêntico**
`backends/cache.py:make_key`. A chave é o hash do texto com espaços colapsados, e só isso. Uma leitura de OCR que difere em uma letra é um miss, e o mesmo balão é traduzido de novo (e pode sair diferente).
✅ **Resolvido via I13 — a posição passa na frente do cache, então uma leitura com letra diferente não dispara nova tradução. A chave do cache segue sendo o texto.**

### A14 · arquivado em 2026-11-04

*Glossário:* O balão que saía da tela era descartado e nada guardava o que já foi lido (resolvido via I13) · ✅

**A14 — O balão que sai da tela é descartado, e nada guarda o que já foi lido**
`core/tracker.py:shift_blocks`. Ao rolar, a caixa que deixa a viewport é removida da lista e some do app. Rolar de volta obriga a ler e traduzir tudo de novo, e nenhum tradutor tem como saber quais foram as falas anteriores da página.
✅ **Resolvido via I13 — o registro guarda os balões que saíram da tela e os redesenha ao rolar de volta.**

### A15 · arquivado em 2026-11-04

*Glossário:* O contexto de tradução só existia no tier LLM, e na ordem de chegada (resolvido via I10) · ✅

**A15 — O contexto de tradução só existia no tier LLM, e na ordem de chegada**
`backends/translate_nmt.py`. O opus-mt traduz frase por frase e não vê a fala vizinha. O tier LLM que existia guardava as últimas traduções na ordem em que chegavam ao tradutor, não na ordem de leitura da página.
✅ **Resolvido via I10 — o TranslateGemma recebe os balões anteriores do registro (I13), na ordem de leitura. O opus-mt segue sem contexto, como primeira versão que aparece na hora.**

### A16 · arquivado em 2026-11-04

*Glossário:* O tradutor mais literal era o único que respondia (resolvido via I10) · ✅

**A16 — A ordem padrão dos tiers punha o tradutor mais literal na frente**
`config.py:TranslationConfig`. O opus-mt era o tradutor que de fato respondia: a nuvem atrás dele nunca era usada, e na frente dele foi bloqueada (ver I9).
✅ **Resolvido via I10 — o opus-mt continua aparecendo primeiro, pela latência, e o TranslateGemma substitui a tradução na mesma caixa quando termina.**

### A17 · arquivado em 2026-11-04

*Glossário:* Seis comandos em teclas de função globais, uma por comando · ✅

**A17 — Seis comandos em teclas de função globais, uma por comando**
`config.py:HotkeyConfig`, `__main__.py` (lista `commands`). Seis teclas de função registradas com `RegisterHotKey`, que consome a tecla no sistema inteiro: o navegador com a página em foco perdia a barra de endereço e a tela cheia.
✅ **Resolvido via I11 — três teclas, F8, F9 e F4, que o navegador não usa para nada que a leitura precise.**

### A18 · arquivado em 2026-11-04

*Glossário:* A área selecionada vive só na memória do processo · ✅

**A18 — A área selecionada vive só na memória do processo**
`__main__.py:App._selected_region`. Ao fechar o app, a área escolhida com a seleção se perdia e a próxima sessão começava na tela cheia.
✅ **Resolvido via I12 — a área fica em `area.json` e volta ao abrir, na tela que a contém.**

### A19 · arquivado em 2026-11-04

*Glossário:* Com a nuvem na frente, cada rodada pagava os retries antes de cair no NMT (encerrado com a remoção da nuvem) · ✅

**A19 — Com a nuvem na frente, cada rodada pagava os retries antes de cair no NMT**
O endpoint gratuito do Google bloqueava por rate limit, e cada rodada esgotava as tentativas com backoff antes de entregar ao NMT (12.4 s para 5 blocos).
✅ **Encerrado: o código da nuvem foi removido junto com o descarte de I9.**

### A20 · arquivado em 2026-11-04

*Glossário:* A nuvem não tinha timeout de rede (encerrado com a remoção da nuvem) · ✅

**A20 — A nuvem não tinha timeout de rede**
`TranslationConfig.timeout` não era lido, e o cliente chamava `requests.get` sem timeout.
✅ **Encerrado: o código da nuvem foi removido junto com o descarte de I9.**

### A22 · arquivado em 2026-11-04

*Glossário:* O classificador de ângulo do RapidOCR desvirava linha curta que estava certa (desligado) · ✅

**A22 — O classificador de ângulo do RapidOCR desvirava linha curta que estava certa**
`backends/ocr_rapid.py:_build_params`. O RapidOCR liga por padrão um classificador que decide se cada recorte de linha está de cabeça para baixo e, se achar que está, gira 180° antes de ler. Em linha curta, ou com "?!" no começo ou no fim, ele errava o palpite: a interjeição saía como as mesmas letras de trás para frente e de ponta-cabeça, e uma palavra de duas letras virava símbolo. Era a maior fonte de erro em balão de fala. Medido com `scripts/eval_captures.py` em 199 telas: desligado, os balões foram de 192 para 210 exatos de 210 (21 regiões ganhas, nenhuma perdida) e o texto solto de 11 para 14 de 31. Nas páginas curadas (`eval_pages.py`, 3 páginas em 33 vistas), as vistas com falha foram de 8 para 0. Texto de mangá chega sempre de pé, então o classificador não tinha nada a ganhar.
✅ **Resolvido — `Global.use_cls` desligado em `_build_params`.**

### S1 · arquivado em 2026-11-04

*Kanban:* Desacoplar a segunda passada de OCR da geometria do mosaico · 4. Descartada · 🚫 Descartado · A# A2, A3, A4, A9

### S1 — O que parece erro de modelo é o estágio de detecção de linha, e a cobertura dele é instável por construção

**Confiança:** alta — cada elo foi medido separadamente.

Cruza A1, A2, A3, A4, P1 e I1.

A queixa de P1 ("o OCR não dá conta") aponta naturalmente para o reconhecedor, e foi essa a leitura que gerou I1. A medição desfaz essa atribuição em três passos. Primeiro, o detector de balão acha a região em toda escala testada, e o reconhecedor lê o texto certo quando recebe aquele recorte (A2): nenhum dos dois é o elo fraco. Segundo, quem não produz nada é o DBNet, o detector de linha que vem dentro do RapidOCR, para balão curto. Terceiro, trocar o modelo não toca nesse estágio — medido, o vizinho imediato dentro do mesmo pacote lê **pior** (I1).

A segunda passada em mosaico existe justamente para cobrir A2, e funciona em resolução nativa. O que a torna não confiável em página reduzida é A3: como todos os recortes suspeitos vão para a mesma imagem e o DBNet dimensiona pelo lado menor dela, a ampliação que cada recorte recebe depende de quem mais está no mosaico. Isso explica a característica mais incômoda de P1 — a inconsistência. Não é que um balão seja difícil; é que a leitura dele muda conforme os *outros* balões suspeitos daquele quadro. A4 fecha o ciclo: quando o mosaico devolve uma leitura confiante e errada, ela ganha da primeira leitura correta.

**Correção candidata:** desacoplar a ampliação de cada recorte da geometria do mosaico, e arbitrar entre as duas leituras por algo melhor que a confiança do reconhecedor. Duas tentativas foram medidas e revertidas (igualar as larguras dos recortes; fixar a largura do mosaico em 736), e uma terceira (reconhecer cada região suspeita numa chamada isolada) recupera casos que falhavam mas devolve leitura vazia em outros. 

**Desfecho:** descartada por falta do que corrigir. As falhas que sustentavam esta cadeia foram medidas com o classificador de ângulo ligado, e parte do "letra trocada" era ele (A22). Desligado, as páginas curadas foram de 8 para 0 vistas com falha e o gabarito das capturas (I6) para 210 de 210 balões exatos. O acoplamento de A3 continua no código, mas não produz falha medida em nenhuma das duas réguas. Reabre se aparecer falha atribuível ao mosaico. O mosaico em si fica: sem ele, uma vista curada passa a ter um bloco de lixo.

**S1 — Descartado.** 🚫 Descartada por falta do que corrigir. As falhas que sustentavam o desacoplamento do mosaico foram medidas com o classificador de ângulo do RapidOCR ligado, e parte do "letra trocada" era ele (A22). Desligado, as páginas curadas (`eval_pages.py`, 3 páginas em 33 vistas) foram de 8 para 0 vistas com falha, e o gabarito das capturas (I6) para 210 de 210 balões exatos. O acoplamento de A3 continua no código, mas não produz falha medida em nenhuma das duas réguas. Reabre se aparecer falha atribuível ao mosaico. O mosaico em si fica: sem ele, uma vista curada passa a ter um bloco de lixo, e o comic-text-detector, que poderia substituí-lo, não acha os balões de uma palavra só (I8).

### S2 · arquivado em 2026-11-04

*Kanban:* Eval cobra recall em toda vista, usando a posição gravada de cada balão · 2. Resolve problema — via Síntese (S#) · ✅ Concluído · resolve P1, P3 · A# A5, A6

### S2 — A instabilidade era invisível porque a medição não cobrava o caso em que ela aparece

**Confiança:** alta — a lacuna foi confirmada ao fechá-la: falhas reais apareceram na primeira execução seguinte.

Cruza A5, A6, P1 e P3.

O eval rodava cada página inteira e em vistas de tela, mas só a página inteira cobrava recall (A5). Como a segunda passada só é confiável em resolução nativa (S1), o único regime medido de verdade era justamente aquele em que o problema **não** aparece. O resultado é que o projeto acreditava estar em 7/7 enquanto, na escala em que o usuário de fato lê, balões sumiam — e P1 não tinha como ser reproduzido por ninguém a não ser abrindo o navegador, que é exatamente o atrito de P3. A6 agravava: quando a saída era redirecionada, o script morria no meio e nem o número parcial saía.

**Correção candidata:** gravar a posição de cada balão junto do texto esperado, para o script saber quais cabem inteiros em cada vista e cobrar recall em todas elas; e preparar o console como o app faz.
Implementada.

**S2 — Recall cobrado em toda vista de tela.** Resolve P1 no sentido de torná-lo reproduzível e medível, não de corrigi-lo.

`scripts/eval_pages.py`: o JSON de cada página ganhou `boxes`, a posição de cada balão, gerada por `--fit-boxes` (roda o pipeline na página inteira e casa cada bloco com o texto esperado). Um tipo `View` passou a carregar escala, deslocamento e o retângulo do conteúdo, e responde por balão se ele está inteiro, cortado ou fora da vista; o recall é cobrado só sobre os inteiros. Balão cortado é classificado por posição, e não só pela marca `partial` do app, porque na vista simulada o conteúdo começa abaixo de uma faixa de cromo do navegador — o balão é cortado pelo conteúdo sem encostar na borda da imagem. Entrou também uma vista com a página ampliada a 1.3x, já que navegador ampliando é caso real, e `console.setup()` no início do `main()`.

Na primeira execução depois da mudança apareceram falhas que antes passavam verdes: um balão de uma palavra só ausente em 5 das 10 vistas de tela de uma página, e um balão curto lido errado na vista ampliada.

### I1 · arquivado em 2026-11-04

*Kanban:* Trocar o motor de OCR por outro modelo · 4. Descartada · 🚫 Descartado

**I1. Trocar o motor de OCR** *(origem: própria)*
Diante de P1, a hipótese natural: o reconhecedor não é bom o bastante e vale trocar por outro. Pesada como candidata e medida contra o vizinho mais óbvio dentro do mesmo pacote.
Endossada como hipótese, **rejeitada pela medição** — ver item no ROADMAP.

**I1 — Trocar o motor de OCR: medido e pior.** Medido contra o vizinho imediato dentro do mesmo pacote (a geracao anterior do mesmo detector+reconhecedor): nas tres paginas inteiras ele le 17/21 baloes exatos contra 19/21 do atual, perde um balao numa pagina e inventa letra em outra. Alem disso a troca nao toca no estagio que falha: o reconhecedor atual le o texto certo quando recebe o recorte da regiao (A2), e quem nao produz caixa e o detector de linha. Trocar de modelo mudaria o reconhecedor, nao o DBNet.

Reavaliar so se aparecer um pacote que exponha um detector de linha diferente, nao um reconhecedor diferente.

### I2 · arquivado em 2026-11-04

*Kanban:* Modo --image: o pipeline lê de um arquivo, sem a tela participar · 1. Resolve problema — via Ideia (I#) · ✅ Concluído · resolve P3

**I2. Rodar o app contra uma imagem em vez da tela** *(origem: própria)*
Poder apontar o app para uma página salva e ver leitura, tradução e caixas, sem depender do que está na tela e sem prender a máquina. Nasceu do incômodo de validar abrindo a imagem numa janela e deixando o app fotografá-la por cima — se outra janela passa na frente, o teste mente.
Endossada. Implementada — ver ROADMAP.

**I2 — Modo `--image`: o pipeline lê de um arquivo, sem a tela participar.** Resolve P3.

`translatorocr/backends/capture_still.py` (novo): `StillCapture` implementa `CaptureBackend` servindo uma viewport sobre a imagem carregada, com `origin` fixa em (0, 0) — assim os bboxes que saem do pipeline já ficam em coordenada da viewport, que é o que o visualizador desenha e o que o rastreio translada. `translatorocr/ui/viewer.py` (novo): janela comum que desenha a viewport e as caixas **no próprio widget**, e cuja roda do mouse move a viewport virtual. `registry.build_pipeline` e `PipelineWorker` passaram a aceitar um backend de captura pronto; no `App`, o visualizador entra no lugar do overlay por duck typing (mesma interface), então o resto do app não sabe em que modo está.

Decisão tomada durante a implementação: a primeira versão abria a imagem numa janela e deixava o app **fotografar a tela** por cima, o que exercitaria também captura, DPI e os flags Win32 do overlay. Foi descartado a pedido — qualquer janela que passe na frente invalida o teste e prende a máquina. O modo atual não cobre esses três; ficam para a conferência ocasional com o app de verdade e para o `--debug-dump`, que foi mantido justamente por ser a única coisa que mostra o que a captura enxergou.

### I3 · arquivado em 2026-11-04

*Kanban:* Modo de leitura: as caixas acompanham a rolagem · 1. Resolve problema — via Ideia (I#) · ✅ Concluído · resolve P2

**I3. Acompanhar a rolagem em vez de traduzir um quadro só** *(origem: própria)*
Como o app já captura a intervalos curtos, dá para perceber que um balão subiu e mover a caixa traduzida junto, em vez de reconhecer tudo de novo. Balões que já foram traduzidos não são retraduzidos enquanto se rola; os que entram são lidos quando a rolagem para, e um que estava cortado é relido inteiro quando aparece todo.
Endossada. Implementada — ver ROADMAP.

**I3 — Modo de leitura: as caixas acompanham a rolagem.** Resolve P2.

`core/tracker.py` (puro, testável sem GPU nem Qt): `prepare` reduz o quadro a 1/4 e converte para cinza; `estimate_shift` mede o deslocamento por correlação de fase e devolve junto resposta e textura; `shift_blocks` translada as caixas e descarta o que saiu. Depois de cada leitura, a tela é o que ela achou mais o que o registro de balões (I13) guarda e ela não cobriu — é o registro que mantém o balão lido inteiro quando a leitura nova vem cortada pela borda. `core/scroll.py` roda o laço a ~16 fps numa thread própria e distingue três situações: nada mudou (conta para "parou"), mudou e é rolagem (translada), mudou e não é rolagem (limpa).

Medições que fixaram os defaults: correlação de fase recupera o deslocamento exato até ~400 px (40% da altura da viewport), com resposta caindo de 0.97 em 60 px para 0.41 em 400 px e 0.01 quando falha; custa 8 ms a 1/4 contra 92 ms em resolução cheia; captura MSS de tela cheia leva 22 ms.

Quatro armadilhas pagas aqui. `cv2.phaseCorrelate` **escreve nos arrays que recebe** (aplica a janela de Hanning no lugar), o que corrompia o quadro guardado para a comparação seguinte — resolvido medindo a textura antes e passando cópias. E a resposta da correlação sozinha não basta: uma área totalmente lisa devolve "não andou nada" com resposta 0.99, confiante e errada, o que congelaria as caixas enquanto a página rola; por isso existe o piso de textura. A correlação é cíclica: rolando rápido, um salto perto de meia altura volta com o sinal trocado e resposta alta, e as caixas e o registro pulavam uma tela inteira para o lado errado (os balões fantasmas que acompanham a rolagem); `ScrollConfig.max_dy` (0.35 da altura) recusa esses saltos, medido sem nenhuma medida errada aceita em regiões de 600 e 1000 px, contra 10 com 0.40 na de 600. E o `mss` guardado em `threading.local` era recriado a cada quadro, porque cada slot da `QThread` chega com estado de thread novo, e nunca fechado, até o limite de 10 mil objetos GDI do Windows; o `MSSCapture` agora guarda o seu num atributo e o reusa.

A parada só dispara uma leitura se houve movimento desde a anterior: `settled` consome a marca de movimento, e uma parada que chega durante uma leitura (ou uma falha) vira leitura assim que ela termina.

Pré-requisito que virou parte do item: o overlay precisou sair da captura, senão o laço mediria a rolagem contra as próprias caixas paradas e o OCR releria a tradução em português. Ver o card correspondente.

Não resolve: zoom e troca de página não são translação, e nesses casos o modo limpa em vez de arrastar caixa para o lugar errado.

### I4 · arquivado em 2026-11-04

*Kanban:* Capturar só a janela do navegador em vez da tela inteira · 4. Descartada · 🚫 Descartado

**I4. Capturar só a janela do navegador, em vez da tela inteira** *(origem: própria)*
Se a captura pegasse apenas a janela alvo, o overlay do próprio app não entraria no quadro e o problema de "o app lê a própria tradução" desapareceria.
Endossada como candidata, **rejeitada** — ver argumento no ROADMAP.

**I4 — Capturar só a janela: desnecessário e mais caro.** Tres argumentos, em ordem de peso. Primeiro, nao e necessario: medido nesta maquina, SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE) tira o overlay da captura (de 15.7% da area para 0.0%) mantendo a translucidez e o click-through, entao o problema que a ideia resolveria ja esta resolvido de graca. Segundo, a variante barata nao funciona: BitBlt sobre o DC de uma janela le a mesma area composta da tela, entao o overlay continuaria na foto. Terceiro, a variante que funciona e cara: PrintWindow com PW_RENDERFULLCONTENT costuma voltar preto em navegador acelerado por GPU, e Windows.Graphics.Capture exige dependencia WinRT nova mais uma UI para escolher a janela, trocando "traduz o que estiver na tela" por "traduz aquela janela".

Reavaliar se a exclusao de captura falhar em alguma maquina: e o plano B natural.

### I5 · arquivado em 2026-11-04

*Kanban:* Coletor de capturas: --collect grava o que o OCR recebeu e o que o app leu e traduziu · 1. Resolve problema — via Ideia (I#) · ✅ Concluído · resolve P1

**I5. Coletor de capturas** *(origem: própria)*
Uma opção `--collect` que, a cada rodada do pipeline, grava a imagem que o OCR recebeu e as leituras e traduções do app, pulando quadros quase iguais. É o que transforma o uso real em amostra, em vez das três páginas curadas de hoje.
Endossada. Implementada — ver ROADMAP.

**I5 — Coletor de capturas: --collect grava o que o OCR recebeu e o que o app leu e traduziu.** Dá amostra real, no recorte que o app recebe, para I6, I7, I8 e I10.

`core/collector.py` (novo): `CaptureCollector.save` grava `eval/captures/<data>/<hora>.webp` e um `.json` ao lado, com o bbox de cada balão em coordenada da imagem, texto, tradução, confiança, `needs_review`, `partial`, `new` (traduzido nesta rodada) e `context` (as falas anteriores em ordem de leitura, vindas de `BlockLedger.context`, só nos balões novos). Tela com diferença média de cinza abaixo de 2.0 para a última gravada é pulada. Falha de disco vira aviso e a leitura segue. Entrou em `Pipeline.run`, e não em `App._on_ready` como planejado, porque a imagem entregue ao OCR só existe ali. A pasta fica separada de `eval/pages/` e fora do versionamento.

Medido com OCR real numa página de `eval/pages`, em 4 paradas: 3 telas gravadas (a parada no mesmo lugar foi pulada), ~65 KB por tela, ~0.1 s por gravação, com contexto de 0 a 6 falas. A gravação roda na thread do worker antes de o resultado ir para a tela, então soma esse 0.1 s à latência, só com `--collect`.

### I6 · arquivado em 2026-11-04

*Kanban:* Gabarito por dois leitores (Baberu OCR e Qwen2.5-VL) sobre as capturas · 1. Resolve problema — via Ideia (I#) · ✅ Concluído · resolve P1

**I6. Gabarito por dois professores** *(origem: própria)*
Em vez de rotular à mão, dois modelos lentos e de famílias diferentes leem cada balão das capturas; onde concordam vira gabarito, onde discordam o usuário escolhe num clique. Roda uma vez, sem pressa.
Endossada. Implementada — ver ROADMAP.

**I6 — Gabarito por dois leitores (Baberu OCR e Qwen2.5-VL) sobre as capturas.** Resolve P1 no sentido de dar uma régua com centenas de balões no lugar de ~21.

`scripts/label_captures.py` roda o detector de balão sobre cada tela de `eval/captures/<data>/`, e dois leitores leem cada região: Baberu OCR e Qwen2.5-VL-3B. Quando as duas leituras são iguais depois de normalizar caixa, pontuação e espaço, a região vira gabarito. Quando diferem, vai para uma página HTML local, onde o usuário escolhe ou corrige. Região que encosta na borda da tela fica marcada como cortada e não é lida. Tudo vai para `labels.json`, ao lado das capturas.

Resultado em 199 telas: 307 regiões, das quais 54 cortadas pela borda e 253 lidas. Das 253, os dois leitores concordaram em 224 (89%), 11 eram vazias, 17 foram revisadas à mão e 1 foi rejeitada. Pendentes: 0.

A régua é `scripts/eval_captures.py`: passa cada tela pelo OCR, agrupamento e portão do app e casa os blocos com as regiões do gabarito. Por região mede achado (algum bloco caiu nela), exato (texto igual ao do gabarito depois de normalizar caixa e pontuação) e CER (fração de caracteres errados: 0.05 é um erro a cada 20 letras; região não achada conta 1.0). `--save` e `--against` comparam duas rodadas região a região. Linha de base do app, 241 regiões com texto (151 textos distintos, porque o mesmo balão aparece em várias telas da rolagem): balões de fala, 210 de 210 achados e 210 de 210 exatos; texto solto (quase sempre onomatopeia), 30 de 31 achados, 14 de 31 exatos, CER médio 0.231. Nenhum bloco caiu fora de região com texto. Antes de desligar o classificador de ângulo (A22), que foi a primeira coisa que a régua achou, os balões estavam em 192 de 210.

Limite: o inglês do Baberu foi destilado do PaddleOCR-VL, então os dois leitores não são de todo independentes. O Qwen-VL é de outra família, e é ele que segura a concordância. E as regiões vêm do detector de balão do próprio app, então balão que ele não acha não aparece na régua.

### I7 · arquivado em 2026-11-04

*Kanban:* OCR com model_type = server, medido contra o gabarito · 4. Descartada · 🚫 Descartado · A# A2, A9

**I7. OCR com o modelo `server`** *(origem: própria)*
Trocar o par de modelos do RapidOCR pelo maior, só mudando a configuração, e medir contra o gabarito.
Descartada pela medição: o PP-OCRv5 só tem `server` em chinês, o reconhecedor chinês junta palavras, e o detector `server` piora o balão de fala a 2,5 vezes o custo. Números no ROADMAP.

**I7 — Descartado.** 🚫 Medido com `scripts/eval_captures.py` em 199 telas, 210 regiões de balão de fala e 31 de texto solto, contra a linha de base `mobile` (192 de 210 balões exatos, 222 ms por tela). O PP-OCRv5 do RapidOCR só tem modelo `server` em chinês: o reconhecedor `server` em inglês não existe, e o chinês lê as letras certas mas tira o espaço entre palavras curtas, 144 de 210 balões exatos, inútil para o tradutor. O detector `server` sozinho sobe as onomatopeias (11 para 18 de 31 exatas), mas nos balões, que são o que se lê, cai de 192 para 188 exatos: some palavra curta e uma ou outra linha sai lida de cabeça para baixo. E custa 553 ms por tela, 2,5 vezes o `mobile`. Os dois juntos: 170 de 210, 739 ms. Nenhuma combinação melhora o balão de fala, e todas custam mais.

### I8 · arquivado em 2026-11-04

*Kanban:* comic-text-detector no lugar do DBNet em ocr_composite.py · 4. Descartada · 🚫 Descartado · A# A2, A3, A9

**I8. Detector de linha treinado em mangá no lugar do DBNet** *(origem: própria)*
O `comic-text-detector` ocuparia o estágio que falha em A2, A3 e A9. Se achar os balões curtos, a segunda passada em mosaico deixa de ser necessária. A diferença para I1 é que o alvo é o detector de linha, não o reconhecedor.
Descartada pela medição: não acha os balões de uma palavra só, que era a condição, e no melhor ajuste só empatou com o DBNet. O que ele ganhava vinha de não passar pelo classificador de ângulo, e esse ganho virou A22. Números no ROADMAP.

**I8 — Descartado.** 🚫 Medido com `scripts/eval_captures.py` em 199 telas (210 regiões de balão de fala, 31 de texto solto), com o modelo de `manga-image-translator` em ONNX no lugar do DBNet e o reconhecedor do RapidOCR lendo os recortes de linha numa chamada só. Com o pós-processamento padrão do DBNet, as caixas saíam justas demais e as linhas curtas eram jogadas fora: 81 de 210 balões exatos. No melhor de três ajustes, sem a segunda passada, foi a 196 de 210, contra 192 da base de então. Mas não achou nenhum dos balões de uma palavra só, que era a condição para tirar o mosaico, e trocou a ordem das linhas em dois balões. Com o mosaico junto, 193 de 210. O ganho dele vinha de outro lugar: o caminho dele não passava pelo classificador de ângulo, e era esse classificador que estragava as linhas curtas (A22). Com o classificador desligado, o DBNet chega a 210 de 210, e o comic-text-detector não tem mais o que ganhar. Pesa contra ele também a licença dos pesos, GPL-3.0.

### I9 · arquivado em 2026-11-04

*Kanban:* Google gratuito como tradutor principal: tiers = [cloud, nmt] · 4. Descartada · 🚫 Descartado · A# A16, A19

**I9. Google gratuito como tradutor principal** *(origem: própria)*
Inverter a ordem dos tiers para `["cloud", "nmt"]`: a nuvem traduz e o opus-mt fica de reserva offline.
Endossada e implementada, depois **descartada**: o IP foi bloqueado já no primeiro pedido, e o uso que o usuário quer é ilimitado. O código da nuvem saiu e a tradução ficou 100% local — ver ROADMAP.

**I9 — Descartado.** 🚫 Chegou a ser implementada, mas o endpoint gratuito do Google bloqueou o IP já no primeiro pedido (429), e o usuário quer uso ilimitado, sem depender de cota de terceiro. A nuvem não tinha como entregar isso, nem com a pausa de A19. O código da nuvem foi removido, e a tradução ficou 100% local: o opus-mt na frente e o TranslateGemma como segunda passada (I10).

### I10 · arquivado em 2026-11-04

*Kanban:* TranslateGemma 4B como segunda passada, com os balões anteriores como contexto · 1. Resolve problema — via Ideia (I#) · ✅ Concluído · resolve P4 · A# A15, A16

**I10. TranslateGemma 4B como tradutor offline com contexto** *(origem: própria)*
Um modelo de tradução local que recebe como contexto os últimos balões em ordem de leitura. Com a nuvem descartada, o teste às cegas passou a ser contra o opus-mt, e o modelo entrou como segunda passada: o opus-mt aparece na hora e o TranslateGemma substitui quando termina.
Endossada. Implementada — ver ROADMAP.

**I10 — TranslateGemma 4B como segunda passada, com os balões anteriores como contexto.** Resolve P4 e ataca A15 pela raiz: o contexto vem do registro (I13), na ordem de leitura.

Com a nuvem descartada (I9), a comparação às cegas de `scripts/eval_translation.py` ficou entre o opus-mt e o TranslateGemma com contexto, em 89 balões das capturas. Erro grave (sentido trocado ou perdido): opus-mt 11 de 89 (12%), TranslateGemma com contexto 8 de 89 (9%). O custo foi o tempo: 2.6 s por balão contra 0.13 s.

Por isso o modelo entrou como segunda passada, sem tirar o opus-mt da frente. `backends/translate_gemma.py` (`GemmaTranslator`) roda o GGUF pelo `llama-cpp-python` com um prompt cru e guarda o resultado no cache sob o backend `gemma`. Só balão novo com 2 palavras ou mais entra na fila de refino do `Pipeline`. O worker refina um balão por volta do laço (`QTimer.singleShot(0)`), então uma captura nova passa na frente da fila. O contexto vem do registro (I13): os balões anteriores, em ordem de leitura. Quando um refino termina, o registro redesenha a caixa com o texto novo.

Verificado com o app real sobre uma página de `eval/pages`: a fila intercala com as capturas, o contexto se acumula e a caixa continua alinhada depois de rolar. Pico de VRAM: 5.56 de 6.14 GB na GTX 1660 SUPER, com detector, OCR e os dois tradutores carregados.

Limites: a lentidão e a fila em ordem de chegada (A21). O `llama-cpp-python` fica no grupo opcional `llm`, porque não há wheel CUDA para Windows e a instalação compila. Sem o grupo, o app segue só com o opus-mt e avisa no console como instalar.

### I11 · arquivado em 2026-11-04

*Kanban:* F8 liga/desliga, F9 oculta/mostra, F4 seleciona a área · 1. Resolve problema — via Ideia (I#) · ✅ Concluído · resolve P5 · A# A17

**I11. Três teclas juntas: F8, F9, F4** *(origem: própria)*
F8 liga e desliga a tradução (o modo leitura vira o único), F9 oculta e mostra, F4 seleciona a área. O resto fica na bandeja. A primeira versão usava Alt+1/2/3, mas soltar o Alt abria o menu do Firefox.
Endossada. Implementada — ver ROADMAP.

**I11 — F8 liga/desliga, F9 oculta/mostra, F4 seleciona a área.** Resolve P5 e A17.

`HotkeyConfig` ficou com três teclas: F8, F9 e F4. A primeira versão usava Alt+1/2/3, mas soltar o Alt abria o menu do Firefox. O modo leitura virou o modo único: F8 liga a tradução, e a primeira leitura sai sem precisar rolar. "Traduzir uma vez" e "Sair" ficaram só na bandeja, com `Command.key` opcional, e o clique simples no ícone liga e desliga a tradução. O F7 saiu: a borda da área aparece por 3 s ao selecionar e ao ligar a tradução, e some sozinha. Trocar a área com a tradução ligada agora dispara uma leitura, porque o rastreio só pedia leitura depois de movimento.

Verificado com o app real: as três teclas registradas no Windows, menu e ajuda do console certos, borda presente logo depois de selecionar e ausente depois de 3.4 s, e leitura disparada ao ligar sobre uma página de `eval/pages`.

### I12 · arquivado em 2026-11-04

*Kanban:* Persistir a área selecionada entre sessões · 3. Nice-to-have · ✅ Concluído · A# A18

**I12. Persistir a área selecionada** *(origem: própria)*
Gravar a área num arquivo pequeno e restaurá-la ao abrir.
Endossada. Implementada — ver ROADMAP.

**I12 — Persistir a área selecionada entre sessões.** Resolve A18.

`ui/area_store.py` (novo) grava a área em `area.json`, fora do versionamento, e a restaura ao abrir. Arquivo ausente ou corrompido vale como tela cheia. Área fora da tela atual também, mas o arquivo fica, para voltar quando o app abrir no monitor dela. O clique sem arrastar apaga o arquivo. No `--image` a área não se aplica. Verificado com o app real: área restaurada ao abrir, regravada ao selecionar e apagada ao voltar à tela cheia.

### I13 · arquivado em 2026-11-04

*Kanban:* Registro de balões: posição na tira, casamento por posição e contexto em ordem de leitura · 1. Resolve problema — via Ideia (I#) · ✅ Concluído · resolve P1, P4 · A# A12, A13, A14

**I13. Registro de balões: o histórico da tira** *(origem: própria)*
Cada balão lido ganha uma posição na tira (y na tela menos a rolagem acumulada), válida dentro de um trecho que termina quando o rastreio se perde. Balão já traduzido e lido inteiro não é retraduzido nem muda de texto; rolar de volta redesenha do registro, sem OCR; e o registro entrega os últimos balões em ordem de leitura como contexto de tradução, que só zera quando o título da janela em primeiro plano muda ou passam ~10 minutos sem leitura.
Endossada. Implementada — ver ROADMAP.

**I13 — Registro de balões: posição na tira, casamento por posição e contexto em ordem de leitura.** Resolve P1 (a leitura deixa de piscar entre paradas) e serve P4: é dele que sai o contexto da segunda passada (I10).

`core/ledger.py` (novo, puro, com lock): `BlockLedger` guarda `Entry` por trecho (`Segment`). A posição é o y da tela menos o deslocamento acumulado, mais a `base` do trecho. O `Pipeline` abre uma `Reading` antes de capturar (`begin`), casa os blocos já passados pelo gate com o registro (`reconcile`) e só manda ao tradutor o que sobra; depois grava o traduzido (`record`). A entrada guardada vale quando tem tradução e o texto é o mesmo, ou quando é inteira e não duvidosa; cede à leitura nova quando estava cortada pela borda ou duvidosa diante de uma leitura limpa. `lost` abre trecho novo; na leitura seguinte, texto igual ao de um trecho antigo no mesmo deslocamento (dois textos, ou um com 12 caracteres ou mais) reancora o antigo. `restore` devolve ao `App._on_scrolled` os balões inteiros do trecho que voltaram à viewport, e eles são redesenhados sem OCR. `context` entrega os últimos 6 balões em ordem de leitura, atravessando os trechos. O registro recomeça quando o título da janela em primeiro plano muda (`ui/foreground.py`, lido a cada leitura) ou passam 600 s sem leitura; `LedgerConfig` reúne os três números. Uma leitura que atravessa um `lost` ou um recomeço não é registrada. A entrada que cabe inteira na área capturada e que a leitura não achou conta uma falta; com `LedgerConfig.max_misses` (2) seguidas ela sai do registro, e um acerto zera a conta — é o que tira da tela o balão que não tem texto embaixo. Depois de cada leitura o `App._on_ready` monta a tela com o que ela achou mais o `restore` do registro, então a tela e o registro concordam sobre quais balões valem.

Medido com OCR real sobre duas páginas de `eval/pages`, em cinco paradas de rolagem mais uma volta ao topo: a parada no mesmo lugar traduziu 0 de 5 blocos; as paradas com rolagem traduziram só o que entrou (1 ou 2 blocos por parada). Em 6 paradas por página, o tradutor foi chamado 3 vezes em cada uma (6 no total, contra 12) e recebeu 7 de 25 blocos lidos numa página e 8 de 27 na outra; o único balão cuja tradução mudou entre paradas foi um que estava cortado na borda e depois foi lido inteiro; ao voltar ao topo o registro redesenhou 5 e 6 balões antes de qualquer OCR, e a parada seguinte traduziu 0.

Limites: a leitura ainda roda o OCR na tela inteira a cada parada (I14); uma entrada inteira cujo texto difere por completo da leitura nova na mesma posição ainda vale, porque o desenho confia na posição.
