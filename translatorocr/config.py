"""Constantes do app, num lugar só.

Não há arquivo de configuração: nenhum destes valores é algo que o usuário precise
ajustar para usar o app, e vários são medidos (ver os comentários). O pouco que é
escolha de uso — área de captura, monitor — se escolhe em runtime, pelas hotkeys ou
pelo ícone da bandeja. Os caminhos de modelo moram em `assets.py`, porque cada backend
está amarrado ao seu modelo e trocar o arquivo não funcionaria sem mudar código.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .assets import ROOT


@dataclass
class CaptureConfig:
    backend: str = "mss"
    # Índice de monitor no padrão do mss: 0 = desktop virtual inteiro, 1 = primário.
    monitor: int = 1
    # Fator de upscale antes do OCR. Medido em 2026-09: com PP-OCRv5 o upscale não
    # melhora acurácia (o recognizer já normaliza os crops para 48px de altura) e,
    # para valer de fato, exigiria subir `ocr.max_side_len` junto — o que custou 17x
    # mais tempo pelo mesmo resultado. Fica como knob, desligado por padrão.
    upscale: float = 1.0


@dataclass
class OCRConfig:
    use_gpu: bool = True
    # Falha alto se use_gpu foi pedido e o provider efetivo veio CPU. Sem isso o ORT
    # cai em CPU silenciosamente — a mesma classe de falha do torch+cpu que passou
    # despercebida na versão antiga.
    strict_gpu: bool = True
    # "en" mantém o charset do reconhecedor em ASCII, o que torna ideograma
    # irrepresentável na saída.
    lang: str = "en"
    model_type: str = "mobile"
    ocr_version: str = "PP-OCRv5"
    max_side_len: int = 2000
    text_score: float = 0.5


@dataclass
class GroupingConfig:
    # Duas linhas entram no mesmo bloco se o gap vertical entre elas for menor que
    # `line_gap_ratio` x altura mediana da linha, e se a sobreposição horizontal for
    # de pelo menos `min_h_overlap` da largura da mais estreita.
    line_gap_ratio: float = 1.0
    min_h_overlap: float = 0.35
    # Freio contra encadeamento transitivo: sem isso, uma coluna de linhas alinhadas
    # e igualmente espaçadas — uma sidebar de IDE, um índice — funde tudo num bloco
    # só, porque cada linha casa com a anterior. Um balão de fala raramente passa
    # de 8 linhas.
    max_lines_per_block: int = 8
    reading_order: str = "ltr"  # "ltr" | "rtl" — inverte o sentido horizontal da ordem de leitura
    # Banda de tolerância vertical, em fração da altura do bloco, para considerar
    # dois blocos como estando "na mesma linha" ao ordenar.
    row_band_ratio: float = 0.6


@dataclass
class DetectorConfig:
    """Detector de balão (RT-DETR-v2, Apache-2.0), rodando antes do reconhecedor.

    Desligar faz o reconhecedor voltar a rodar na imagem inteira, que é o comportamento
    do v1 — útil para comparar, e o fallback quando o modelo não foi baixado.
    """

    enabled: bool = True
    use_gpu: bool = True
    strict_gpu: bool = True
    # O modelo foi treinado em 640x640 e o preprocessor dele não preserva aspecto.
    # Mudar isto sem re-treinar degrada a detecção.
    input_size: int = 640
    score_threshold: float = 0.3
    # Fração da linha que precisa cair dentro de uma região para ser atribuída a ela.
    # Linha que não alcança isso em nenhuma região é descartada — é assim que a UI sai.
    min_line_overlap: float = 0.5
    # Segunda passada para regiões que o DBNet do RapidOCR perdeu ou leu mal (ver
    # `backends/ocr_composite.py`). Região sem linha, ou cuja pior linha ficou abaixo
    # disto, é reconhecida de novo num mosaico. Medido em páginas reais: recupera o
    # balão de uma palavra só que o DBNet não enxerga e a linha curta que ele recorta
    # mal (confiança ~0.6), por ~150 ms.
    fallback: bool = True
    fallback_confidence: float = 0.8
    # Também é refeita a região cujas linhas cobrem menos que isto da altura dela: é o
    # sinal de linha perdida (a primeira linha sumiu de um balão de quatro, e as três
    # que sobraram tinham confiança 1.0). Regiões completas mediram 0.91-1.07.
    min_coverage: float = 0.8
    # Margem **branca** em volta de cada recorte do mosaico. Margem tirada da própria
    # imagem foi medida e piora: puxa texto dos balões vizinhos que se sobrepõem.
    fallback_pad: int = 30
    # Duas regiões de texto que se sobrepõem nesta fração da menor viram uma só. O
    # detector às vezes devolve duas caixas para o mesmo balão, e sem isto o fallback
    # reconhecia o balão duas vezes.
    region_merge: float = 0.6
    # Região a menos disto da borda da captura está cortada pela viewport: o bloco é
    # marcado `needs_review` para a tradução parcial não parecer completa.
    edge_margin: int = 4


@dataclass
class ScrollConfig:
    """Modo de leitura: acompanha a rolagem em vez de traduzir um quadro só.

    A cada quadro mede-se quanto a página andou por correlação de fase e translada-se o
    que já está desenhado, em vez de reconhecer de novo. O pipeline só roda quando a
    rolagem para — é o que deixa a leitura fluida e, de quebra, resolve o balão cortado
    pela borda: quando ele aparece inteiro, é relido inteiro.
    """

    # ~16 fps. Medido nesta máquina: captura MSS de tela cheia 22 ms + correlação 8 ms,
    # então 60 ms deixa folga de sobra para o resto do laço.
    interval_ms: int = 60
    # A correlação roda na imagem reduzida: 8 ms a 1/4 contra 92 ms em resolução cheia,
    # com a mesma precisão (erro < 0.5 px num deslocamento de 60 px).
    downscale: float = 0.25
    # Resposta da correlação, que serve de confiança. Medido: 0.97 para 60 px, 0.88 para
    # 150 px, 0.41 para 400 px (o limite útil, 40% da altura da viewport) e 0.01 quando
    # o conteúdo mudou demais para ser translação. Zoom de 15% cai para 0.035.
    min_response: float = 0.30
    # Deslocamento horizontal acima disto não é rolagem vertical: é scroll lateral ou
    # mudança de layout, e translação vertical não descreve o que aconteceu.
    max_dx: float = 8.0
    # Piso de textura (desvio padrão do quadro reduzido). **Não é redundante com
    # `min_response`**: uma área totalmente lisa — o vão branco entre quadros de um
    # webtoon — devolve deslocamento zero com resposta 0.99, confiante e errada. Sem
    # este piso, as caixas congelariam enquanto a página rola.
    min_texture: float = 4.0
    # Diferença média de nível de cinza entre dois quadros abaixo da qual a tela conta
    # como parada. Separa "nada aconteceu" de "mudou e não foi rolagem" — a confiança do
    # deslocamento sozinha não separa, porque tela parada e lisa também reprova nela.
    min_change: float = 0.5
    # Quantos quadros parados disparam o pipeline (4 x 60 ms = ~1/4 de segundo).
    settle_frames: int = 4
    # Sobreposição mínima, como fração da menor caixa, para considerar que uma leitura
    # nova e uma antiga são o mesmo balão.
    merge_overlap: float = 0.5


@dataclass
class GateConfig:
    """Portão entre reconhecimento e tradução."""

    enabled: bool = True
    # Abaixo disto o bloco é marcado `needs_review` e desenhado com borda distinta.
    min_confidence: float = 0.6
    # Abaixo disto é descartado: não paga tradução e não vai para a tela.
    drop_below: float = 0.35
    max_symbol_ratio: float = 0.5
    min_chars: int = 2
    # Caractere impossível para o idioma (glifo alucinado, ex.: um alfa grego no lugar de um D) é
    # removido e o bloco segue marcado; só acima desta fração o bloco inteiro é tratado
    # como alucinação e descartado. Antes um único glifo derrubava o balão todo.
    max_invalid_ratio: float = 0.2


@dataclass
class TranslationConfig:
    source_lang: str = "auto"
    target_lang: str = "pt"
    cache_path: str = str(ROOT / "cache.sqlite")
    max_retries: int = 3
    backoff_base: float = 0.4
    timeout: float = 10.0
    # Tradução é I/O de rede, então paralelizar tem ganho quase linear. Medido: uma
    # tela cheia com 82 blocos levava 64s em série, 11s com 8 workers. Mas 8 já
    # provocou rate limit numa tela com 55 blocos, então o default é 4 — a rajada
    # importa mais que o volume para este endpoint.
    max_workers: int = 4
    # Ordem dos tiers. Cada um só recebe o que o anterior não conseguiu traduzir, o que
    # reusa a semântica de falha-por-item que TranslatorBackend já contratualiza. O NMT
    # é local (sem rede, sem cota) e mediu 0.8s para 50 balões, contra 11.4s da nuvem.
    tiers: list[str] = field(default_factory=lambda: ["nmt", "cloud"])
    # CPU de propósito: o ctranslate2 carrega `cublas64_12.dll` por nome e este venv tem
    # CUDA 13 (veio do onnxruntime-gpu). Ligar a GPU aqui exigiria o wheel
    # nvidia-cublas-cu12 de ~553 MB mais um os.add_dll_directory manual, para disputar
    # VRAM com o OCR. Em CPU a tradução ainda roda em paralelo com a inferência de GPU.
    nmt_compute_type: str = "int8"
    # Medido nesta máquina com 50 balões: beam 1 = 0.55s, beam 2 = 0.82s, beam 4 =
    # 1.27s (int8). Contra os 11.4s da nuvem, beam 2 sai de graça e traduz melhor.
    nmt_beam_size: int = 2
    nmt_threads: int = 0  # 0 deixa o ctranslate2 decidir


@dataclass
class LLMConfig:
    """Refino por LLM local, só nos blocos que o gate marcou `needs_review`
    (ver `backends/translate_llm.py`).

    Modelo: Qwen3-4B-Q4_K_M, escolhido por benchmark (`scripts/benchmark_llm.py`)
    contra o Qwen3-8B — qualidade equivalente em frases reais, mas ~3x mais rápido por
    bloco e com bem mais folga de VRAM.

    **Desligado por padrão**, medido em 2026-09 em páginas reais de mangá: em página
    limpa ele nunca aciona (todo bloco passa do gate com confiança >= 0.6) e, forçado a
    rodar, traduziu pior que o NMT — trocou sentido, errou concordância e repetiu a
    tradução do bloco anterior. Carregado, só ocupava ~2.5 GB de VRAM.
    """

    enabled: bool = False
    # -1 = offload total pra GPU. Testado com OCR+detector já carregados: 5.1GB de
    # pico numa placa de 6GB — reduza se um modelo de detector maior entrar depois.
    n_gpu_layers: int = -1
    n_ctx: int = 4096
    # Quantas traduções anteriores entram como contexto rolante no prompt — ajuda o
    # LLM a manter consistência de tom/nome entre falas do mesmo balão.
    context_window: int = 6
    # JSON simples {"nome original": "tradução"}. None = prompt não inclui glossário.
    glossary_path: str | None = None


@dataclass
class OverlayConfig:
    # Translucidez da janela inteira, não de cada cor: quem desenha a forma é a região
    # do Win32 (ver `ui/overlay.py`). O alpha por pixel do Qt teve que sair porque o
    # Windows recusa tirar da captura uma janela que o usa.
    window_alpha: int = 205
    box_color: tuple[int, int, int] = (0, 0, 0)
    text_color: tuple[int, int, int] = (245, 245, 245)
    outline_color: tuple[int, int, int] = (0, 0, 0)
    # Borda das caixas que o gate marcou como duvidosas (âmbar).
    review_color: tuple[int, int, int] = (230, 160, 30)
    corner_radius: int = 6
    padding: int = 6
    min_font_pt: int = 7
    max_font_pt: int = 42
    font_family: str = "Segoe UI"


@dataclass
class HotkeyConfig:
    # Nomes resolvidos em ui/hotkey.py. "capture" dispara o pipeline, "dismiss"
    # apaga o overlay — necessário porque a janela é transparente a input e nunca
    # recebe um Esc por conta própria.
    capture: str = "F8"
    dismiss: str = "F9"
    quit: str = "F10"
    # Todo backend de captura já aceita região opcional (mss/dxcam); estas duas são a
    # forma de escolher e conferir a região.
    select_area: str = "F11"
    # F12 era o default óbvio (ao lado de F8-F11), mas é comumente reservado por
    # outro programa no Windows (overlay de GPU, gravador de tela) — nesta máquina
    # `RegisterHotKey` recusou com erro 1409. F7 não colide com nada do app nem com
    # essas reservas comuns.
    show_region_outline: str = "F7"
    # Liga/desliga o modo de leitura, que acompanha a rolagem (ver `ScrollConfig`).
    scroll_mode: str = "F6"


@dataclass
class Config:
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    ocr: OCRConfig = field(default_factory=OCRConfig)
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    gate: GateConfig = field(default_factory=GateConfig)
    grouping: GroupingConfig = field(default_factory=GroupingConfig)
    scroll: ScrollConfig = field(default_factory=ScrollConfig)
    translation: TranslationConfig = field(default_factory=TranslationConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    hotkeys: HotkeyConfig = field(default_factory=HotkeyConfig)
    debug_dump: bool = False
