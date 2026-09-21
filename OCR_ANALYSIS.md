# Análise — leitura de página (OCR) e sua medição

> Companion: [ROADMAP.md](ROADMAP.md) — aqui mora o **porquê** (achados, problemas, ideias, sínteses); lá mora o **o que fazer** (kanban dos itens implementáveis). Os dois usam os mesmos IDs e devem sempre concordar sobre a decisão vigente de cada item.
>
> **Legenda:** `A#` achado de leitura de código/medição · `P#` problema relatado · `I#` ideia pesada como candidata · `S#` síntese causal.
>
> **Última mudança (2026-09-21):** primeira rodada. Catalogada a investigação de por que balões somem ou saem errados lendo mangá no navegador, com a causa raiz do acoplamento entre recortes na segunda passada de OCR (A3) e duas tentativas de correção medidas e revertidas.

## Contexto e escopo

Cobre o pipeline de leitura ponta a ponta — detector de balão, OCR, gate e tradução — com o centro de gravidade na leitura, que é de onde vêm as queixas. Achados que nasceram como "limitação conhecida" no README ou como armadilha no `CLAUDE.md` e que na verdade são coisas **em aberto** foram trazidos para cá (A7–A11); o que ficou naqueles arquivos é o que não tem o que rastrear: decisão de escopo, realidade da plataforma, e regra de "isto já foi medido, não refaça".

O que foi lido e medido: `translatorocr/backends/ocr_composite.py`, `ocr_rapid.py`, `detect_bubble.py`, `translate_nmt.py`, `core/gate.py`, `core/grouping.py` e `scripts/eval_pages.py`.

As medições vêm de três páginas reais de webtoon que ficam em `eval/pages/` — **locais, fora do versionamento**. Nada do conteúdo delas (texto, imagem) entra neste documento, nos testes ou no código: os balões são descritos pela forma ("um balão de uma palavra só", "uma palavra curta com til decorativo"), nunca pelo que dizem.

Cada página roda inteira e em 10 vistas de tela simuladas (escalas 1.3 a 0.5, no topo e no meio do scroll), num quadro 1920x1080.

---

## Análise de código (A#)

**A1 — O reconhecedor roda uma vez na imagem cheia; as regiões do detector só atribuem e filtram**
`ocr_composite.py`. O RapidOCR faz detecção de linha (DBNet) e reconhecimento na mesma chamada, sobre a imagem inteira; o detector de balão (RT-DETR) roda em paralelo e suas regiões servem para dizer a que balão cada linha pertence e para descartar o que caiu fora. Recortar por região e chamar o pipeline em cada uma custou 11x numa tela cheia, e chamar só o reconhecedor sobre uma região devolve lixo (ele espera recorte justo de **uma linha**).
ℹ️ **Restrição estrutural do desenho atual; é o que torna a segunda passada necessária em vez de opcional.**

**A2 — O DBNet não gera caixa para balão curto**
Medido nas três páginas: um balão de uma palavra só não recebe caixa de linha em **nenhuma** escala. O detector de balão acha a região sempre (score 0.78–0.85) e o reconhecedor lê o texto corretamente quando recebe aquele recorte. Ou seja, a falha está no estágio de detecção de linha, entre um detector que acerta e um reconhecedor que acerta.
⚠️ **Confirmado. É o que a segunda passada em mosaico existe para cobrir, e ela só cobre de forma confiável em resolução nativa.**

**A3 — A ampliação de um recorte no mosaico depende das dimensões do mosaico inteiro**
`ocr_composite.py:_read_mosaic`. Os recortes suspeitos são empilhados verticalmente numa imagem só e reconhecidos numa única chamada. Mas o DBNet amplia a entrada até o lado **menor** chegar a 736 px, e num mosaico empilhado esse lado é a **largura** — então a ampliação efetiva que cada recorte recebe é função do mosaico todo, não dele mesmo. Medido: mudar apenas o tamanho de um recorte fez outro, intocado, deixar de ser lido. Um recorte reconhecido **sozinho** recebe ampliação de ~9x e é lido certo; o mesmo recorte dentro de um mosaico largo quase não é ampliado e some.
⚠️ **Confirmado, sem correção fechada. É a causa raiz de a segunda passada acertar num quadro e falhar no seguinte com o mesmo conteúdo.**

**A4 — A escolha entre a primeira e a segunda leitura é por cobertura e confiança mínima**
`ocr_composite.py:_rank`. Ordena por (cobriu a região, menor confiança das linhas). Uma leitura do mosaico que sai confiante e errada ganha de uma primeira leitura correta — foi o que aconteceu ao mexer na geometria do mosaico: um balão que estava certo passou a sair com letra trocada. A confiança do reconhecedor não é um sinal bom o bastante para arbitrar entre duas leituras do mesmo texto.
⚠️ **Confirmado, sem correção proposta.**

**A5 — O eval não cobrava recall nas vistas de tela**
`scripts/eval_pages.py`. Só a página inteira cobrava "achou todos os balões"; nas vistas de tela o script apontava apenas lixo e duplicata, porque não tinha como distinguir "o OCR perdeu o balão" de "o balão está fora da viewport". Consequência: uma regressão de leitura em escala de tela passava como verde.
✅ **Resolvido via S2 — o JSON de cada página passou a guardar a posição de cada balão, e o script cobra os que cabem inteiros na vista.**

**A6 — O eval estourava com a saída redirecionada**
`scripts/eval_pages.py` imprimia seta e acentos sem preparar o console; em cp1252 isso levanta `UnicodeEncodeError` e derruba a execução no meio.
✅ **Resolvido via S2 — passou a chamar `ui/console.setup()`, o mesmo tratamento do app.**

**A7 — Não há gate de estabilidade: o overlay desenha a primeira leitura que chegar**
Vinha registrado como limitação no README. Para mangá parado não incomoda, mas para texto que aparece letra por letra (jogo) a leitura sai no meio da animação. Exigir N leituras iguais consecutivas só era possível com um quadro anterior para comparar — o que passou a existir com o modo de leitura.
⚠️ **Confirmado. Deixou de estar bloqueado; ver card no ROADMAP.**

**A8 — O detector é treinado em mangá/HQ e rende menos fora dessa distribuição**
Numa tela de IDE ele dispara `text_free` em quase toda a interface: o ganho medido foi de 102 para 45 blocos, vindo de agrupar melhor e não de descartar UI (só 1 linha caiu fora de todas as regiões). Numa página de mangá aberta no navegador, texto de interface em volta ainda pode virar bloco.
ℹ️ **Restrição do modelo, não resolvível por construção. Conviver: `F11` restringe a captura à área da página.**

**A9 — Palavra curta com til decorativo sai errada em resolução nativa**
Uma palavra de três letras seguida de til é lida com os glifos trocados, com confiança baixa; o gate marca o bloco e ele sai com borda âmbar. Nas escalas reduzidas de leitura em tela sai certa, o que é o inverso do padrão de A2/A3 e sugere que a segunda passada acerta quando a região é pequena e erra quando ela é grande o bastante para o DBNet já ter produzido uma caixa ruim.
⚠️ **Confirmado. Mesma frente de A2/A3 — depende do mecanismo que S1 escolher.**

**A10 — O tradutor roda em CPU por incompatibilidade de versão de cuBLAS**
Vinha registrado como armadilha no `CLAUDE.md`. O `ctranslate2.dll` carrega `cublas64_12.dll` por nome, sem procurar em `site-packages/nvidia/`, e este venv tem CUDA 13 (veio junto do `onnxruntime-gpu`). Em CPU o NMT mede 0.82 s para 50 blocos, contra 11.4 s da nuvem, então não é gargalo hoje. Ligar a GPU exigiria o wheel `nvidia-cublas-cu12` (~553 MB) mais um `os.add_dll_directory` manual antes do import, e disputaria VRAM com o OCR. O issue de CUDA 13 no CTranslate2 está aberto desde nov/2025.
⚠️ **Confirmado, com correção conhecida e sem justificativa para pagá-la agora.**

**A11 — A geração seguinte do OCR não é alcançável na versão atual do pacote**
Vinha registrado como comentário em `ocr_rapid.py`. Os pesos da geração seguinte estão no catálogo do `rapidocr` 3.9.2, mas não são alcançáveis: o enum de idioma do reconhecedor não tem o membro correspondente e a resolução de modelo rejeita a string crua. Verificado em 2026-09. Importa porque uma geração nova poderia trazer um **detector de linha** diferente, que é exatamente o estágio que falha em A2 — ao contrário de trocar de reconhecedor, que foi medido e não ajuda (I1).
⚠️ **Confirmado. Reavaliar quando o pacote subir de versão.**

---

## Problemas (P#)

**P1. Lendo mangá no navegador, balões somem ou saem com letra trocada ⭐**
O usuário abre a página e o resultado vem ruim: alguns balões não aparecem traduzidos, outros aparecem com palavra errada. A impressão dele é de que "o OCR não está dando conta". Não é consistente — o mesmo balão pode sair certo numa hora e sumir em outra.

**P2. Balão encostado na borda da tela sai traduzido pela metade**
Quando o balão está cortado pela viewport, a tradução mostrada corresponde só ao pedaço visível, e não há indicação de que falta texto.

**P3. Não dá para verificar se está funcionando sem ocupar a tela real**
Testar exigia deixar a página aberta e não mexer na máquina; qualquer janela que passasse na frente entrava na captura e invalidava o teste.

---

## Ideias (I#)

**I1. Trocar o motor de OCR** *(origem: própria)*
Diante de P1, a hipótese natural: o reconhecedor não é bom o bastante e vale trocar por outro. Pesada como candidata e medida contra o vizinho mais óbvio dentro do mesmo pacote.
Endossada como hipótese, **rejeitada pela medição** — ver item no ROADMAP.

**I2. Rodar o app contra uma imagem em vez da tela** *(origem: própria)*
Poder apontar o app para uma página salva e ver leitura, tradução e caixas, sem depender do que está na tela e sem prender a máquina. Nasceu do incômodo de validar abrindo a imagem numa janela e deixando o app fotografá-la por cima — se outra janela passa na frente, o teste mente.
Endossada. Implementada — ver ROADMAP.

**I3. Acompanhar a rolagem em vez de traduzir um quadro só** *(origem: própria)*
Como o app já captura a intervalos curtos, dá para perceber que um balão subiu e mover a caixa traduzida junto, em vez de reconhecer tudo de novo. Balões que já foram traduzidos não são retraduzidos enquanto se rola; os que entram são lidos quando a rolagem para, e um que estava cortado é relido inteiro quando aparece todo.
Endossada. Implementada — ver ROADMAP.

**I4. Capturar só a janela do navegador, em vez da tela inteira** *(origem: própria)*
Se a captura pegasse apenas a janela alvo, o overlay do próprio app não entraria no quadro e o problema de "o app lê a própria tradução" desapareceria.
Endossada como candidata, **rejeitada** — ver argumento no ROADMAP.

---

## Síntese (S#)

### S1 — O que parece erro de modelo é o estágio de detecção de linha, e a cobertura dele é instável por construção

**Confiança:** alta — cada elo foi medido separadamente.

Cruza A1, A2, A3, A4, P1 e I1.

A queixa de P1 ("o OCR não dá conta") aponta naturalmente para o reconhecedor, e foi essa a leitura que gerou I1. A medição desfaz essa atribuição em três passos. Primeiro, o detector de balão acha a região em toda escala testada, e o reconhecedor lê o texto certo quando recebe aquele recorte (A2): nenhum dos dois é o elo fraco. Segundo, quem não produz nada é o DBNet, o detector de linha que vem dentro do RapidOCR, para balão curto. Terceiro, trocar o modelo não toca nesse estágio — medido, o vizinho imediato dentro do mesmo pacote lê **pior** (I1).

A segunda passada em mosaico existe justamente para cobrir A2, e funciona em resolução nativa. O que a torna não confiável em página reduzida é A3: como todos os recortes suspeitos vão para a mesma imagem e o DBNet dimensiona pelo lado menor dela, a ampliação que cada recorte recebe depende de quem mais está no mosaico. Isso explica a característica mais incômoda de P1 — a inconsistência. Não é que um balão seja difícil; é que a leitura dele muda conforme os *outros* balões suspeitos daquele quadro. A4 fecha o ciclo: quando o mosaico devolve uma leitura confiante e errada, ela ganha da primeira leitura correta.

**Correção candidata:** desacoplar a ampliação de cada recorte da geometria do mosaico, e arbitrar entre as duas leituras por algo melhor que a confiança do reconhecedor. Duas tentativas foram medidas e revertidas (igualar as larguras dos recortes; fixar a largura do mosaico em 736), e uma terceira (reconhecer cada região suspeita numa chamada isolada) recupera casos que falhavam mas devolve leitura vazia em outros. Mecanismo ainda em aberto.

### S2 — A instabilidade era invisível porque a medição não cobrava o caso em que ela aparece

**Confiança:** alta — a lacuna foi confirmada ao fechá-la: falhas reais apareceram na primeira execução seguinte.

Cruza A5, A6, P1 e P3.

O eval rodava cada página inteira e em vistas de tela, mas só a página inteira cobrava recall (A5). Como a segunda passada só é confiável em resolução nativa (S1), o único regime medido de verdade era justamente aquele em que o problema **não** aparece. O resultado é que o projeto acreditava estar em 7/7 enquanto, na escala em que o usuário de fato lê, balões sumiam — e P1 não tinha como ser reproduzido por ninguém a não ser abrindo o navegador, que é exatamente o atrito de P3. A6 agravava: quando a saída era redirecionada, o script morria no meio e nem o número parcial saía.

**Correção candidata:** gravar a posição de cada balão junto do texto esperado, para o script saber quais cabem inteiros em cada vista e cobrar recall em todas elas; e preparar o console como o app faz.
Implementada.

### S3 — O gate de estabilidade deixou de estar bloqueado

**Confiança:** média — o pré-requisito técnico existe e está medido; o ganho é suposto, porque o caso de uso que ele atende não está sendo exercitado.

Cruza A7 e I3.

A7 registrava que não dá para exigir leituras repetidas sem um quadro anterior com que comparar, e por isso o gate de estabilidade dependia do modo de leitura entrar primeiro. Esse bloqueio caiu: o laço de `core/scroll.py` já mantém o quadro anterior, já sabe distinguir "nada mudou" de "mudou e não é rolagem", e já tem um conceito de "parou" (`settle_frames`). O que falta é só consumir isso.

Não endereça nenhum `P#`: a queixa que o gate resolveria é de texto animado letra por letra, que é caso de jogo, e o foco declarado do projeto hoje é mangá.

**Correção candidata:** no modo de leitura, exigir que o texto de um bloco saia igual em duas leituras consecutivas antes de desenhar, em vez de desenhar a primeira que chegar.
Registrada sem prioridade.
