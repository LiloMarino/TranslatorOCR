"""Comparação às cegas de tradutores sobre os balões das capturas reais.

    uv run scripts/eval_translation.py --round 2 --candidates opus-mt,gemma-ctx
    uv run scripts/eval_translation.py --round 2 --serve    # reabre a votação da rodada
    uv run scripts/eval_translation.py --round 2 --score    # placar e latência
    uv run scripts/eval_translation.py --round 2 --fresh    # sorteia de novo, zerando votos

Os balões vêm de `eval/captures/` (gravadas pelo `--collect`): só os novos de cada leitura
do pipeline, inteiros na tela e com as falas anteriores gravadas, sem repetir texto. Todos
os candidatos recebem a mesma leitura do OCR, com os erros que ela tiver, porque é isso
que o tradutor recebe no app. Cada rodada sorteia só balões que nenhuma outra rodada
usou, então os placares de rodadas diferentes são amostras independentes.

Candidatos:
- `opus-mt`: o NMT offline do app, com o mesmo pré-processamento de caixa e frase.
- `gemma`: TranslateGemma 4B no formato oficial, uma fala por pedido.
- `gemma-ctx`: o mesmo modelo, com as falas anteriores como turnos da conversa, cada uma
  já respondida com a tradução que o `gemma` deu a ela. É o histórico que o registro de
  balões teria no app, e o template oficial aceita turnos alternados.

A página mostra o recorte do balão, as falas anteriores e as traduções em ordem
sorteada por balão, sem dizer de quem é cada uma; o servidor local é quem guarda o mapa
e grava cada voto em `eval/translation/<rodada>/votes.json` na hora. Tudo em
`eval/translation/` fica fora do versionamento.

Sem cobertura de teste: ferramenta de medida, não pipeline de produção.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import json
import random
import statistics
import sys
import threading
import time
import webbrowser
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from translatorocr.assets import TRANSLATEGEMMA, TRANSLATEGEMMA_PATH
from translatorocr.backends.translate_gemma import GemmaTranslator
from translatorocr.backends.translate_nmt import NMTTranslator
from translatorocr.config import RefineConfig, TranslationConfig

ROOT = Path(__file__).resolve().parent.parent
CAPTURES = ROOT / "eval" / "captures"
OUT = ROOT / "eval" / "translation"
SAMPLE_NAME = "ab.json"
VOTES_NAME = "votes.json"

CANDIDATES = ("opus-mt", "gemma", "gemma-ctx")
VERDICTS = ("tie", "bad")
CROP_MARGIN = 24


@dataclass
class Sample:
    id: str
    image: str
    bbox: list[int]
    source: str
    context: list[str]


def used_ids(round_dir: Path) -> set[str]:
    """Balões já sorteados pelas outras rodadas."""
    used: set[str] = set()
    for path in OUT.glob(f"*/{SAMPLE_NAME}"):
        if path.parent != round_dir:
            used |= {item["id"] for item in json.loads(path.read_text(encoding="utf-8"))["items"]}
    return used


def load_pool() -> list[Sample]:
    """Balões elegíveis de todas as capturas, um por texto distinto."""
    pool: dict[str, Sample] = {}
    for path in sorted(CAPTURES.glob("*/*.json")):
        if path.name == "labels.json":
            continue
        blocks = json.loads(path.read_text(encoding="utf-8"))["blocks"]
        for i, block in enumerate(blocks):
            key = " ".join(block["source"].lower().split())
            if not block["new"] or block["partial"] or not block["context"] or key in pool:
                continue
            pool[key] = Sample(
                id=f"{path.parent.name}/{path.stem}#{i}",
                image=str(path.with_suffix(".webp").relative_to(ROOT)),
                bbox=block["bbox"],
                source=block["source"],
                context=block["context"],
            )
    return list(pool.values())


class Gemma:
    """O tradutor do app, mais a tradução sem contexto memorizada para montar históricos."""

    def __init__(self) -> None:
        if not TRANSLATEGEMMA[0].present():
            raise SystemExit(
                f"TranslateGemma não encontrado em {TRANSLATEGEMMA_PATH}. "
                "Rode `uv run scripts/fetch_models.py translategemma`."
            )
        self._translator = GemmaTranslator(RefineConfig(), cache=None)
        self._memo: dict[str, str] = {}

    def translate(self, text: str, history: list[tuple[str, str]]) -> str:
        return self._translator.translate(text, history) or ""

    def official(self, text: str) -> str:
        """Tradução sem contexto, memorizada: as falas de contexto se repetem entre balões."""
        if text not in self._memo:
            self._memo[text] = self.translate(text, [])
        return self._memo[text]


def timed(fn: Any, *args: Any) -> tuple[str, float]:
    started = time.perf_counter()
    out = fn(*args)
    return out, (time.perf_counter() - started) * 1000


def generate(round_dir: Path, candidates: list[str], n: int, seed: int) -> None:
    used = used_ids(round_dir)
    pool = [sample for sample in load_pool() if sample.id not in used]
    if not pool:
        raise SystemExit(
            f"Nenhum balão elegível em {CAPTURES} fora das outras rodadas. "
            "Grave mais telas com `--collect`."
        )
    samples = random.Random(seed).sample(pool, min(n, len(pool)))
    print(f"{len(samples)} balões sorteados de {len(pool)} elegíveis ({len(used)} já usados)")

    nmt = NMTTranslator(TranslationConfig(), cache=None)
    # A carga já aquece a GPU: a primeira medida não paga a subida dos kernels.
    gemma = Gemma()

    def run(name: str, sample: Sample) -> tuple[str, float]:
        if name == "opus-mt":
            return timed(lambda: nmt.translate([sample.source], "en", "pt")[0] or "")
        if name == "gemma":
            return timed(gemma.translate, sample.source, [])
        # O histórico é traduzido antes, fora do cronômetro: no app ele já estaria no
        # registro de balões.
        history = [(line, gemma.official(line)) for line in sample.context]
        return timed(gemma.translate, sample.source, history)

    rng = random.Random(seed + 1)
    items = []
    for k, sample in enumerate(samples, 1):
        outputs: dict[str, str] = {}
        latency: dict[str, float] = {}
        for name in candidates:
            outputs[name], latency[name] = run(name, sample)
        order = list(candidates)
        rng.shuffle(order)
        items.append({**asdict(sample), "outputs": outputs, "latency_ms": latency, "order": order})
        print(f"\r  {k}/{len(samples)}", end="", flush=True)
    print()

    round_dir.mkdir(parents=True, exist_ok=True)
    payload = {"candidates": candidates, "seed": seed, "pool": len(pool), "items": items}
    (round_dir / SAMPLE_NAME).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (round_dir / VOTES_NAME).write_text("{}\n", encoding="utf-8")


def crop_uri(image: str, bbox: list[int]) -> str:
    img = cv2.imread(str(ROOT / image))
    h, w = img.shape[:2]
    x1, y1, x2, y2 = bbox
    crop = img[
        max(0, y1 - CROP_MARGIN) : min(h, y2 + CROP_MARGIN),
        max(0, x1 - CROP_MARGIN) : min(w, x2 + CROP_MARGIN),
    ]
    _, data = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return "data:image/jpeg;base64," + base64.b64encode(data.tobytes()).decode()


def identical(item: dict[str, Any]) -> bool:
    """Todas as traduções iguais: empate certo, que não vai à votação."""
    return len(set(item["outputs"].values())) == 1


def render_page(sample: dict[str, Any]) -> str:
    # A página só vê as traduções na ordem sorteada; quem é quem fica no servidor.
    items = [
        {
            "id": item["id"],
            "img": crop_uri(item["image"], item["bbox"]),
            "context": item["context"],
            "source": item["source"],
            "options": [item["outputs"][name] for name in item["order"]],
        }
        for item in sample["items"]
        if not identical(item)
    ]
    return PAGE.replace("__ITEMS__", json.dumps(items, ensure_ascii=False))


def read_votes(round_dir: Path) -> dict[str, str]:
    path = round_dir / VOTES_NAME
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_sample(round_dir: Path) -> dict[str, Any]:
    path = round_dir / SAMPLE_NAME
    if not path.is_file():
        raise SystemExit(f"A rodada {round_dir.name} ainda não foi sorteada ({path}).")
    return json.loads(path.read_text(encoding="utf-8"))


def serve(round_dir: Path, port: int) -> None:
    sample = read_sample(round_dir)
    orders = {item["id"]: item["order"] for item in sample["items"]}
    page = render_page(sample).encode()
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, body: bytes, kind: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/votes":
                # O voto volta para a página como posição, que é tudo o que ela conhece.
                votes = read_votes(round_dir)
                picks = {
                    vid: v if v in VERDICTS else orders[vid].index(v)
                    for vid, v in votes.items()
                    if vid in orders
                }
                self._send(json.dumps(picks).encode(), "application/json")
            else:
                self._send(page, "text/html; charset=utf-8")

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            vid, pick = body["id"], body["pick"]
            with lock:
                votes = read_votes(round_dir)
                votes[vid] = pick if pick in VERDICTS else orders[vid][int(pick)]
                (round_dir / VOTES_NAME).write_text(
                    json.dumps(votes, indent=2) + "\n", encoding="utf-8"
                )
            self._send(b"{}", "application/json")

        def log_message(self, format: str, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Votação em {url} (Ctrl+C encerra; cada voto já fica gravado)")
    webbrowser.open(url)
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()


def score(round_dir: Path) -> None:
    sample = read_sample(round_dir)
    candidates: list[str] = sample["candidates"]
    votes = read_votes(round_dir)
    items = {item["id"]: item for item in sample["items"]}
    same = sum(identical(item) for item in items.values())
    print(
        f"Rodada {round_dir.name}: {len(items)} balões sorteados de {sample['pool']} "
        f"elegíveis; {same} com todas as traduções iguais ficaram fora da votação"
    )
    print(f"Votos: {len(votes)} de {len(items) - same}")

    # Um voto numa tradução vale para todo candidato que deu a mesma frase: o botão
    # escolhido entre duas frases idênticas é sorteio, não preferência.
    wins = dict.fromkeys(candidates, 0)
    verdicts = dict.fromkeys(VERDICTS, 0)
    # Vitórias que cada um teria se fossem todos iguais: 1/k por balão de k frases distintas.
    expected = dict.fromkeys(candidates, 0.0)
    for vid, verdict in votes.items():
        if verdict in VERDICTS:
            verdicts[verdict] += 1
            continue
        outputs = items[vid]["outputs"]
        distinct = len(set(outputs.values()))
        for name in candidates:
            expected[name] += 1 / distinct
            if outputs[name] == outputs[verdict]:
                wins[name] += 1
    decided = len(votes) - sum(verdicts.values())
    print(f"Balões com vencedora: {decided}")
    for name in candidates:
        print(f"  {name:<12} {wins[name]:>3}  (por acaso: ~{expected[name]:.1f})")
    print(f"  {'empate':<12} {verdicts['tie']:>3}")
    print(f"  {'todas ruins':<12} {verdicts['bad']:>3}")
    print("Latência por balão, mediana e pior caso:")
    for name in candidates:
        values = [item["latency_ms"][name] for item in items.values()]
        print(f"  {name:<12} {statistics.median(values):>6.0f} ms  máx {max(values):.0f} ms")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval_translation", description=__doc__)
    parser.add_argument("--round", required=True, help="nome da rodada (pasta em eval/translation)")
    parser.add_argument(
        "--candidates",
        default=",".join(CANDIDATES),
        help=f"separados por vírgula, ao sortear (default: {','.join(CANDIDATES)})",
    )
    parser.add_argument("-n", type=int, default=50, help="balões a sortear (default 50)")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--port", type=int, default=8765)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--serve", action="store_true", help="reabre a votação da rodada")
    mode.add_argument("--score", action="store_true", help="mostra o placar da rodada")
    mode.add_argument("--fresh", action="store_true", help="sorteia de novo, zerando os votos")
    args = parser.parse_args(argv)

    round_dir = OUT / args.round
    if args.score:
        score(round_dir)
        return 0
    if not args.serve:
        candidates = args.candidates.split(",")
        unknown = set(candidates) - set(CANDIDATES)
        if unknown or len(candidates) < 2:
            parser.error(f"--candidates: dois ou mais de {', '.join(CANDIDATES)}")
        if read_votes(round_dir) and not args.fresh:
            raise SystemExit(
                f"A rodada {args.round} já tem votos. Use --serve para continuar, ou --fresh "
                "para sortear de novo e descartá-los."
            )
        generate(round_dir, candidates, args.n, args.seed)
    serve(round_dir, args.port)
    return 0


PAGE = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tradução às cegas</title>
<style>
:root { --bg: #f6f6f4; --card: #fff; --fg: #1d1d1b; --dim: #77756f; --line: #dddbd4;
        --pick: #2f6fdb; --pick-bg: #e6eefc; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #17171a; --card: #222226; --fg: #ececea; --dim: #9a9892; --line: #3a3a40;
          --pick: #7aa7ff; --pick-bg: #26324a; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg);
       font: 16px/1.45 system-ui, sans-serif; }
main { max-width: 760px; margin: 0 auto; padding: 16px; }
header { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
h1 { font-size: 18px; margin: 0; }
.dim { color: var(--dim); font-size: 14px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px;
        padding: 16px; margin-top: 12px; }
.card img { max-width: 100%; max-height: 320px; display: block; margin: 0 auto 12px; }
.context { border-left: 3px solid var(--line); padding-left: 10px; margin-bottom: 10px; }
.source { font-weight: 600; margin-bottom: 14px; }
button { font: inherit; color: inherit; background: var(--card); cursor: pointer;
         border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; }
.option { display: flex; gap: 10px; width: 100%; text-align: left; margin-top: 8px; }
.option kbd, .verdicts kbd { color: var(--dim); }
.picked { border-color: var(--pick); background: var(--pick-bg); }
.verdicts, nav { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
nav { justify-content: space-between; }
</style>
</head>
<body>
<main>
  <header>
    <h1>Qual tradução ficou melhor?</h1>
    <span class="dim" id="progress"></span>
  </header>
  <p class="dim">Teclas: os números escolhem; E marca empate; R marca todas ruins;
     setas navegam. Cada voto é gravado na hora.</p>
  <div class="card" id="card"></div>
  <nav>
    <button id="prev">&larr; Anterior</button>
    <button id="next">Próximo &rarr;</button>
  </nav>
</main>
<script>
const ITEMS = __ITEMS__;
let votes = {};
let index = 0;

function el(tag, attrs, text) {
  const node = document.createElement(tag);
  Object.assign(node, attrs || {});
  if (text !== undefined) node.textContent = text;
  return node;
}

function render() {
  const item = ITEMS[index];
  const card = document.getElementById("card");
  card.replaceChildren();
  card.append(el("img", { src: item.img, alt: "Recorte do balão" }));
  if (item.context.length) {
    const ctx = el("div", { className: "context dim" });
    ctx.append(el("div", {}, "Falas anteriores:"));
    item.context.forEach(line => ctx.append(el("div", {}, line)));
    card.append(ctx);
  }
  card.append(el("div", { className: "source" }, item.source));
  item.options.forEach((text, i) => {
    const button = el("button", { className: "option" + (votes[item.id] === i ? " picked" : "") });
    button.append(el("kbd", {}, String(i + 1)), el("span", {}, text));
    button.onclick = () => vote(i);
    card.append(button);
  });
  const verdicts = el("div", { className: "verdicts" });
  [["tie", "E", "Empate"], ["bad", "R", "Todas ruins"]].forEach(([key, kbd, label]) => {
    const button = el("button", { className: votes[item.id] === key ? "picked" : "" });
    button.append(el("kbd", {}, kbd + " "), el("span", {}, label));
    button.onclick = () => vote(key);
    verdicts.append(button);
  });
  card.append(verdicts);
  const done = Object.keys(votes).length;
  document.getElementById("progress").textContent =
    `balão ${index + 1} de ${ITEMS.length} · ${done} votados`;
}

async function vote(pick) {
  const item = ITEMS[index];
  await fetch("/vote", { method: "POST", body: JSON.stringify({ id: item.id, pick }) });
  votes[item.id] = pick;
  if (index < ITEMS.length - 1) index++;
  render();
}

function go(step) {
  index = Math.min(ITEMS.length - 1, Math.max(0, index + step));
  render();
}

document.getElementById("prev").onclick = () => go(-1);
document.getElementById("next").onclick = () => go(1);
document.addEventListener("keydown", event => {
  const key = event.key.toLowerCase();
  const option = Number(key) - 1;
  if (Number.isInteger(option) && option >= 0 && option < ITEMS[index].options.length) vote(option);
  else if (key === "e") vote("tie");
  else if (key === "r") vote("bad");
  else if (key === "arrowleft") go(-1);
  else if (key === "arrowright") go(1);
});

fetch("/votes").then(r => r.json()).then(saved => {
  votes = saved;
  // Retoma no primeiro balão ainda sem voto.
  const first = ITEMS.findIndex(item => !(item.id in votes));
  index = first === -1 ? 0 : first;
  render();
});
</script>
</body>
</html>
"""

if __name__ == "__main__":
    raise SystemExit(main())
