# Análise — leitura de página (OCR) e sua medição

> Companion: [ROADMAP.md](ROADMAP.md) — aqui mora o **porquê** (achados, problemas, ideias, sínteses); lá mora o **o que fazer** (kanban dos itens implementáveis). Os dois usam os mesmos IDs e devem sempre concordar sobre a decisão vigente de cada item.
>
> **Legenda:** `A#` achado de leitura de código/medição · `P#` problema relatado · `I#` ideia pesada como candidata · `S#` síntese causal.
>
> **Última mudança (2026-11-04):** a régua do gabarito achou o classificador de ângulo desvirando linha curta (A22); desligado, os balões foram a 210 de 210 exatos, e S1, I7 (modelo `server`) e I8 (comic-text-detector) foram descartados pela medição.

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

**A7 — Não há gate de estabilidade: o overlay desenha a primeira leitura que chegar**
Vinha registrado como limitação no README. Para mangá parado não incomoda, mas para texto que aparece letra por letra (jogo) a leitura sai no meio da animação. Exigir N leituras iguais consecutivas só era possível com um quadro anterior para comparar — o que passou a existir com o modo de leitura.
⚠️ **Confirmado. Deixou de estar bloqueado; ver card no ROADMAP.**

**A8 — O detector é treinado em mangá/HQ e rende menos fora dessa distribuição**
Numa tela de IDE ele dispara `text_free` em quase toda a interface: o ganho medido foi de 102 para 45 blocos, vindo de agrupar melhor e não de descartar UI (só 1 linha caiu fora de todas as regiões). Numa página de mangá aberta no navegador, texto de interface em volta ainda pode virar bloco.
ℹ️ **Restrição do modelo, não resolvível por construção. Conviver: a seleção de área restringe a captura à página.**

**A9 — Palavra curta com til decorativo sai errada em resolução nativa**
Uma palavra de três letras seguida de til é lida com os glifos trocados, com confiança baixa; o gate marca o bloco e ele sai com borda âmbar. Nas escalas reduzidas de leitura em tela sai certa, o que é o inverso do padrão de A2/A3 e sugere que a segunda passada acerta quando a região é pequena e erra quando ela é grande o bastante para o DBNet já ter produzido uma caixa ruim.
⚠️ **Confirmado. Mesma frente de A2/A3 — depende do mecanismo que S1 escolher.**

**A10 — O tradutor roda em CPU por incompatibilidade de versão de cuBLAS**
Vinha registrado como armadilha no `CLAUDE.md`. O `ctranslate2.dll` carrega `cublas64_12.dll` por nome, sem procurar em `site-packages/nvidia/`, e este venv tem CUDA 13 (veio junto do `onnxruntime-gpu`). Em CPU o NMT mede 0.82 s para 50 blocos, contra 11.4 s da nuvem, então não é gargalo hoje. Ligar a GPU exigiria o wheel `nvidia-cublas-cu12` (~553 MB) mais um `os.add_dll_directory` manual antes do import, e disputaria VRAM com o OCR. O issue de CUDA 13 no CTranslate2 está aberto desde nov/2025.
⚠️ **Confirmado, com correção conhecida e sem justificativa para pagá-la agora.**

**A11 — A geração seguinte do OCR não é alcançável na versão atual do pacote**
Vinha registrado como comentário em `ocr_rapid.py`. Os pesos da geração seguinte estão no catálogo do `rapidocr` 3.9.2, mas não são alcançáveis: o enum de idioma do reconhecedor não tem o membro correspondente e a resolução de modelo rejeita a string crua. Verificado em 2026-09. Importa porque uma geração nova poderia trazer um **detector de linha** diferente, que é exatamente o estágio que falha em A2 — ao contrário de trocar de reconhecedor, que foi medido e não ajuda (I1).
⚠️ **Confirmado. Reavaliar quando o pacote subir de versão.**

**A21 — A segunda passada é dezenas de vezes mais lenta que o opus-mt, numa fila que só anda em ordem de chegada**
`backends/translate_gemma.py`, `core/pipeline.py` (fila de refino). Medido: 2.6 s por balão no A/B, 33.5 s para 19 balões no `benchmark_llm.py` (~1.8 s cada) e 0.4 a 0.7 s por balão no app, contra 0.13 s do opus-mt. A fila é FIFO e processa um balão por volta do laço do worker: rolando rápido, ela ainda refina balões que já saíram da tela enquanto os novos esperam. Ao carregar, o llama.cpp avisa que a GTX 1660 SUPER não tem tensor cores e que o caminho de kernel compilado é o subótimo; o build já é CUDA (`llama_supports_gpu_offload()` verdadeiro, llama-cpp-python 0.3.35).
⚠️ **Confirmado pela medição. O atraso aparece só ao rolar rápido; parado, a fila esvazia em segundos.**

---

## Problemas (P#)

**P1. Lendo mangá no navegador, balões somem ou saem com letra trocada ⭐**
O usuário abre a página e o resultado vem ruim: alguns balões não aparecem traduzidos, outros aparecem com palavra errada. A impressão dele é de que "o OCR não está dando conta". Não é consistente — o mesmo balão pode sair certo numa hora e sumir em outra.

**P2. Balão encostado na borda da tela sai traduzido pela metade**
Quando o balão está cortado pela viewport, a tradução mostrada corresponde só ao pedaço visível, e não há indicação de que falta texto.

**P3. Não dá para verificar se está funcionando sem ocupar a tela real**
Testar exigia deixar a página aberta e não mexer na máquina; qualquer janela que passasse na frente entrava na captura e invalidava o teste.

**P4. A tradução sai literal, sem entender a frase ⭐**
Expressão idiomática chega traduzida palavra por palavra, e uma fala que continua a anterior é traduzida como se começasse do nada. O usuário compara com um aplicativo de celular e a tradução de lá lê melhor. A origem é só inglês e a restrição é dura: tudo grátis, sem API paga.

**P5. Teclas demais, espalhadas, e que tiram teclas do navegador**
O app pede seis teclas de função diferentes, longe umas das outras, e duas delas (F6 e F11) param de funcionar no navegador enquanto o app está aberto. Para uso corrente bastam poucas teclas, juntas.

---

## Ideias (I#)

**I14. OCR só na faixa que entrou na tela** *(origem: própria)*
Com o registro de balões, a parte da tela que já foi lida não precisa passar de novo pelo OCR. Economiza GPU, mas um balão cortado na fronteira da faixa precisa de tratamento que ainda não foi desenhado.
Endossada como direção; sem mecanismo fechado.

**I15. Recompilar o llama-cpp-python para GPU sem tensor cores** *(origem: própria)*
O próprio llama.cpp indica o caminho para a GTX 1660 SUPER (A21): compilar com `CMAKE_CUDA_ARCHITECTURES=61-virtual;80-virtual` e `GGML_CUDA_FORCE_MMQ`, o que usa na Turing os kernels da geração anterior, feitos para GPU sem tensor cores. Se a segunda passada ficar mais rápida, a fila de A21 esvazia antes e o contexto da tradução chega mais cedo.
Endossada como experimento; o resultado decide — ver ROADMAP.

---

## Síntese (S#)

### S3 — O gate de estabilidade deixou de estar bloqueado

**Confiança:** média — o pré-requisito técnico existe e está medido; o ganho é suposto, porque o caso de uso que ele atende não está sendo exercitado.

Cruza A7 e I3.

A7 registrava que não dá para exigir leituras repetidas sem um quadro anterior com que comparar, e por isso o gate de estabilidade dependia do modo de leitura entrar primeiro. Esse bloqueio caiu: o laço de `core/scroll.py` já mantém o quadro anterior, já sabe distinguir "nada mudou" de "mudou e não é rolagem", e já tem um conceito de "parou" (`settle_frames`). O que falta é só consumir isso.

Não endereça nenhum `P#`: a queixa que o gate resolveria é de texto animado letra por letra, que é caso de jogo, e o foco declarado do projeto hoje é mangá.

**Correção candidata:** no modo de leitura, exigir que o texto de um bloco saia igual em duas leituras consecutivas antes de desenhar, em vez de desenhar a primeira que chegar.
Registrada sem prioridade.
