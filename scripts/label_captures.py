"""Gabarito de OCR das capturas reais, lido por dois modelos que erram em lugares diferentes.

    uv run scripts/label_captures.py              # lê o que falta e abre a revisão
    uv run scripts/label_captures.py --limit 5    # lê só 5 capturas novas (para testar)
    uv run scripts/label_captures.py --serve      # só reabre a revisão
    uv run scripts/label_captures.py --status     # quantos balões em cada estado

Em cada captura de `eval/captures/<data>/` (gravadas pelo `--collect`), o detector de
balão do app acha as regiões de texto, e dois leitores leem cada recorte: o Baberu OCR,
treinado em balão de mangá, e o Qwen2.5-VL, de outra família. Aprenderam de fontes
diferentes, então quando os dois dão a mesma leitura ela vira gabarito sem revisão.
Quando discordam, o caso vai para uma página local onde você escolhe a leitura certa,
digita a sua ou descarta a região. A comparação usa o mesmo `normalize` de quem mede
(`textmatch.py`), então pontuação e caixa não geram revisão.

Os modelos vêm por `uv run scripts/fetch_models.py baberu qwen-vl` e rodam no grupo
`llm` (`uv sync --group llm`).

O gabarito mede a **leitura**, não a detecção: as regiões vêm do mesmo detector que o
app usa, então um balão que ele não acha não entra em nenhum dos dois lados. Região rente
à borda da captura fica registrada sem leitura (`partial`): é o balão cortado pela
viewport, que o app relê inteiro quando a rolagem o traz.

Grava `eval/captures/<data>/labels.json` a cada captura lida, e retoma de onde parou. Um
caso revisado vale para toda região com o mesmo par de leituras: o mesmo balão aparece em
várias capturas seguidas da rolagem.

Sem cobertura de teste: ferramenta de medida, não pipeline de produção.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import json
import random
import sys
import threading
import unicodedata
import webbrowser
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from textmatch import normalize

from translatorocr.assets import BABERU, QWEN_VL
from translatorocr.backends._ort import preload_cuda_dlls, session_providers
from translatorocr.backends.detect_bubble import TEXT_KINDS, BubbleDetector
from translatorocr.backends.ocr_composite import merge_overlapping, touches_edge
from translatorocr.config import DetectorConfig

ROOT = Path(__file__).resolve().parent.parent
CAPTURES = ROOT / "eval" / "captures"
LABELS_NAME = "labels.json"
READERS = ("baberu", "qwen-vl")
CROP_MARGIN = 24

# Estados de uma região. Só `agreed` e `reviewed` têm `text`, e só eles entram na medida.
PARTIAL, AGREED, EMPTY, PENDING, REVIEWED, REJECTED = (
    "partial",
    "agreed",
    "empty",
    "pending",
    "reviewed",
    "rejected",
)
IN_REVIEW = {PENDING, REVIEWED, REJECTED}

QWEN_PROMPT = "Transcribe the text in this image exactly as written. Output only the text."

# Pré-processamento do DINOv2 que o Baberu usa: o recorte inteiro vai a 224x224.
BABERU_SIDE = 224
BABERU_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
BABERU_STD = np.array([0.229, 0.224, 0.225], np.float32)
BABERU_PAST = [f"past_k{i}" for i in range(6)] + [f"past_v{i}" for i in range(6)]
BABERU_BOS, BABERU_EOS = 1, 2
BABERU_SPECIAL = 4


def require(assets: list[Any], group: str) -> None:
    if not all(asset.present() for asset in assets):
        raise SystemExit(f"Modelo ausente. Rode `uv run scripts/fetch_models.py {group}`.")


class Baberu:
    """O `onnx_infer.py` publicado com o modelo, mesma decodificação: gulosa, penalidade
    de repetição 1.2, e teto de 12 repetições seguidas de letra ou dígito e 16 de símbolo.
    É essa decodificação que produz os números do model card."""

    def __init__(self) -> None:
        import onnxruntime as ort

        require(BABERU, "baberu")
        paths = {Path(asset.local).name: asset.path for asset in BABERU}
        providers = session_providers(True)

        def session(name: str) -> Any:
            return ort.InferenceSession(str(paths[name]), providers=providers)

        self._vision = session("vision_fp16.onnx")
        self._prefill = session("decoder_prefill_int8.onnx")
        self._step = session("decoder_step_int8.onnx")
        charset = json.loads(paths["vocab.json"].read_text(encoding="utf-8"))
        self._chars = {i + BABERU_SPECIAL: ch for i, ch in enumerate(charset)}
        self._content = {
            i + BABERU_SPECIAL
            for i, ch in enumerate(charset)
            if len(ch) == 1 and ch not in "ーｰ〜~" and unicodedata.category(ch)[0] in "LN"
        }

    def read(self, bgr: np.ndarray) -> str:
        rgb = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        resized = rgb.resize((BABERU_SIDE, BABERU_SIDE), Image.Resampling.BICUBIC)
        pixels = (np.asarray(resized, np.float32) / 255.0 - BABERU_MEAN) / BABERU_STD
        vision = self._vision.run(
            ["vision_embeds"], {"pixel_values": pixels.transpose(2, 0, 1)[None]}
        )[0]
        out = self._prefill.run(
            None, {"vision_embeds": vision, "input_ids": np.array([[BABERU_BOS]], np.int64)}
        )
        logits, past = out[0][0, -1].astype(np.float64), out[1:]
        seen, tokens, position = {BABERU_BOS}, [], vision.shape[1] + 1
        for _ in range(256):
            for token in seen:
                logits[token] = logits[token] * 1.2 if logits[token] < 0 else logits[token] / 1.2
            if tokens:
                last = tokens[-1]
                cap = 12 if last in self._content else 16 if last >= BABERU_SPECIAL else 0
                run = next((k for k, t in enumerate(reversed(tokens)) if t != last), len(tokens))
                if cap and run >= cap:
                    logits[last] = -np.inf
            token = int(np.argmax(logits))
            if token == BABERU_EOS:
                break
            tokens.append(token)
            seen.add(token)
            feed = {
                "input_ids": np.array([[token]], np.int64),
                "position_ids": np.array([[position]], np.int64),
                **dict(zip(BABERU_PAST, past, strict=True)),
            }
            out = self._step.run(None, feed)
            logits, past = out[0][0, -1].astype(np.float64), out[1:]
            position += 1
        return "".join(self._chars.get(t, "") for t in tokens)


class QwenVL:
    def __init__(self) -> None:
        import llama_cpp
        from llama_cpp._utils import suppress_stdout_stderr
        from llama_cpp.llama_chat_format import Qwen25VLChatHandler

        self._quiet = suppress_stdout_stderr
        require(QWEN_VL, "qwen-vl")
        model, projector = (asset.path for asset in QWEN_VL)
        handler = Qwen25VLChatHandler(clip_model_path=str(projector), verbose=False)
        # Any: llama_cpp não é dependência do grupo padrão, e o pyright roda sem ele.
        self._llm: Any = llama_cpp.Llama(
            str(model), chat_handler=handler, n_ctx=4096, n_gpu_layers=-1, verbose=False
        )

    def read(self, bgr: np.ndarray) -> str:
        _, data = cv2.imencode(".png", bgr)
        uri = "data:image/png;base64," + base64.b64encode(data.tobytes()).decode()
        content = [
            {"type": "image_url", "image_url": {"url": uri}},
            {"type": "text", "text": QWEN_PROMPT},
        ]
        # O mtmd escreve o prompt de cada imagem no stderr, ignorando o `verbose=False`.
        with self._quiet(disable=False):
            result = self._llm.create_chat_completion(
                messages=[{"role": "user", "content": content}], temperature=0, max_tokens=256
            )
        return (result["choices"][0]["message"]["content"] or "").strip()

    def close(self) -> None:
        self._llm.close()


def collapse(text: str) -> str:
    return " ".join(text.split())


def judge(readings: dict[str, str]) -> tuple[str, str | None]:
    """Estado e gabarito de uma região recém-lida."""
    keys = {normalize(text) for text in readings.values()}
    if len(keys) > 1:
        return PENDING, None
    if not keys.pop():
        return EMPTY, None
    return AGREED, collapse(readings[READERS[0]])


def review_key(readings: dict[str, str]) -> str:
    return "\n".join(normalize(readings[name]) for name in READERS)


def load_labels(folder: Path) -> dict[str, Any]:
    path = folder / LABELS_NAME
    if not path.is_file():
        return {"readers": list(READERS), "images": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_labels(folder: Path, labels: dict[str, Any]) -> None:
    # Grava ao lado e troca: interromper a leitura no meio não corrompe o que já foi lido.
    path = folder / LABELS_NAME
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(labels, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def folders() -> list[Path]:
    return sorted(p for p in CAPTURES.iterdir() if p.is_dir()) if CAPTURES.is_dir() else []


def read_all(limit: int | None) -> None:
    labels = {folder: load_labels(folder) for folder in folders()}
    todo = [
        (folder, image)
        for folder, data in labels.items()
        for image in sorted(folder.glob("*.webp"))
        if image.stem not in data["images"]
    ][:limit]
    if not todo:
        print("Todas as capturas já foram lidas.")
        return
    print(f"{len(todo)} capturas para ler")

    preload_cuda_dlls()
    cfg = DetectorConfig()
    detector = BubbleDetector(cfg)
    baberu = Baberu()
    qwen = QwenVL()
    try:
        for k, (folder, path) in enumerate(todo, 1):
            image = cv2.imread(str(path))
            height, width = image.shape[:2]
            found = [d for d in detector.detect(image) if d.kind in TEXT_KINDS]
            records = []
            for region in merge_overlapping(found, cfg.region_merge):
                record: dict[str, Any] = {"bbox": list(region.bbox), "kind": region.kind}
                if touches_edge(region.bbox, width, height, cfg.edge_margin):
                    records.append({**record, "status": PARTIAL, "text": None})
                    continue
                x1, y1, x2, y2 = region.bbox
                crop = image[y1:y2, x1:x2]
                readings = {"baberu": baberu.read(crop), "qwen-vl": qwen.read(crop)}
                state, text = judge(readings)
                records.append({**record, "readings": readings, "status": state, "text": text})
            labels[folder]["images"][path.stem] = records
            save_labels(folder, labels[folder])
            print(f"\r  {k}/{len(todo)}", end="", flush=True)
        print()
    finally:
        qwen.close()


def status() -> None:
    counts: Counter[str] = Counter()
    pending: set[str] = set()
    for folder in folders():
        for records in load_labels(folder)["images"].values():
            for record in records:
                counts[record["status"]] += 1
                if record["status"] == PENDING:
                    pending.add(review_key(record["readings"]))
    read = sum(counts.values()) - counts[PARTIAL]
    if not read:
        print("Nenhuma região lida ainda.")
        return
    print(f"Regiões lidas: {read} (mais {counts[PARTIAL]} cortadas pela borda, sem leitura)")
    labels = {
        AGREED: "os dois leram igual",
        EMPTY: "os dois não leram palavra nenhuma",
        PENDING: "discordaram, esperando revisão",
        REVIEWED: "discordaram, revisadas",
        REJECTED: "descartadas na revisão",
    }
    for key, label in labels.items():
        print(f"  {counts[key]:>5}  {counts[key] / read:>4.0%}  {label}")
    print(f"Casos distintos esperando revisão: {len(pending)}")


def crop_uri(path: Path, bbox: list[int]) -> str:
    img = cv2.imread(str(path))
    h, w = img.shape[:2]
    x1, y1, x2, y2 = bbox
    crop = img[
        max(0, y1 - CROP_MARGIN) : min(h, y2 + CROP_MARGIN),
        max(0, x1 - CROP_MARGIN) : min(w, x2 + CROP_MARGIN),
    ]
    _, data = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return "data:image/jpeg;base64," + base64.b64encode(data.tobytes()).decode()


def review_items(labels: dict[Path, dict[str, Any]]) -> list[dict[str, Any]]:
    """Um caso por par distinto de leituras, mostrado com o recorte da primeira região."""
    cases: dict[str, dict[str, Any]] = {}
    for folder, data in labels.items():
        for stem, records in data["images"].items():
            for record in records:
                if record["status"] not in IN_REVIEW:
                    continue
                key = review_key(record["readings"])
                if key in cases:
                    cases[key]["count"] += 1
                    continue
                options = [record["readings"][name] for name in READERS]
                # A ordem sorteada por caso esconde qual leitor deu cada leitura.
                random.Random(key).shuffle(options)
                cases[key] = {
                    "key": key,
                    "img": crop_uri(folder / f"{stem}.webp", record["bbox"]),
                    "count": 1,
                    "options": options,
                    "status": record["status"],
                    "text": record["text"],
                }
    return list(cases.values())


def serve(port: int) -> None:
    labels = {folder: load_labels(folder) for folder in folders()}
    items = review_items(labels)
    if not items:
        print("Nenhum caso para revisar.")
        return
    page = PAGE.replace("__ITEMS__", json.dumps(items, ensure_ascii=False)).encode()
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, body: bytes, kind: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            self._send(page, "text/html; charset=utf-8")

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            text = collapse(body["text"]) if body["text"] is not None else None
            with lock:
                for folder, data in labels.items():
                    touched = False
                    for records in data["images"].values():
                        for record in records:
                            if (
                                record["status"] in IN_REVIEW
                                and review_key(record["readings"]) == body["key"]
                            ):
                                record["status"] = REVIEWED if text else REJECTED
                                record["text"] = text or None
                                touched = True
                    if touched:
                        save_labels(folder, data)
            self._send(b"{}", "application/json")

        def log_message(self, format: str, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Revisão em {url} (Ctrl+C encerra; cada decisão já fica gravada)")
    webbrowser.open(url)
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="label_captures", description=__doc__)
    parser.add_argument("--limit", type=int, help="lê no máximo tantas capturas novas")
    parser.add_argument("--port", type=int, default=8766)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--serve", action="store_true", help="só reabre a revisão")
    mode.add_argument("--status", action="store_true", help="quantas regiões em cada estado")
    args = parser.parse_args(argv)

    if args.status:
        status()
        return 0
    if not args.serve:
        read_all(args.limit)
        status()
    serve(args.port)
    return 0


PAGE = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Revisão de OCR</title>
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
.card img { max-width: 100%; max-height: 360px; display: block; margin: 0 auto 12px; }
button, input { font: inherit; color: inherit; background: var(--card);
                border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; }
button { cursor: pointer; }
.option { display: flex; gap: 10px; width: 100%; text-align: left; margin-top: 8px;
          white-space: pre-line; }
kbd { color: var(--dim); }
.picked { border-color: var(--pick); background: var(--pick-bg); }
.edit { display: flex; gap: 8px; margin-top: 12px; }
.edit input { flex: 1; min-width: 0; }
.actions, nav { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
nav { justify-content: space-between; }
</style>
</head>
<body>
<main>
  <header>
    <h1>Qual leitura está certa?</h1>
    <span class="dim" id="progress"></span>
  </header>
  <p class="dim">Teclas: 1 e 2 escolhem; D abre a digitação (Enter grava); X descarta a
     região (sem fala, ou ilegível); setas navegam. Cada decisão é gravada na hora.</p>
  <div class="card" id="card"></div>
  <nav>
    <button id="prev">&larr; Anterior</button>
    <button id="next">Próximo &rarr;</button>
  </nav>
</main>
<script>
const ITEMS = __ITEMS__;
let index = Math.max(0, ITEMS.findIndex(item => item.status === "pending"));

function el(tag, attrs, text) {
  const node = document.createElement(tag);
  Object.assign(node, attrs || {});
  if (text !== undefined) node.textContent = text;
  return node;
}

const collapse = text => text.split(/\\s+/).filter(Boolean).join(" ");

function render() {
  const item = ITEMS[index];
  const card = document.getElementById("card");
  card.replaceChildren();
  card.append(el("img", { src: item.img, alt: "Recorte da região" }));
  if (item.count > 1) {
    card.append(el("p", { className: "dim" }, `Aparece em ${item.count} capturas.`));
  }
  item.options.forEach((text, i) => {
    const picked = item.status === "reviewed" && item.text === collapse(text);
    const button = el("button", { className: "option" + (picked ? " picked" : "") });
    button.append(el("kbd", {}, String(i + 1)), el("span", {}, text || "(nada lido)"));
    button.onclick = () => decide(collapse(text));
    card.append(button);
  });
  const typed = item.status === "reviewed" && !item.options.some(o => collapse(o) === item.text);
  const edit = el("form", { className: "edit" });
  const input = el("input", { id: "typed", value: typed ? item.text : collapse(item.options[0]),
                              placeholder: "Leitura certa" });
  if (typed) input.classList.add("picked");
  edit.append(input, el("button", { type: "submit" }, "Gravar"));
  edit.onsubmit = event => { event.preventDefault(); if (input.value.trim()) decide(input.value); };
  card.append(edit);
  const actions = el("div", { className: "actions" });
  const reject = el("button", { className: item.status === "rejected" ? "picked" : "" });
  reject.append(el("kbd", {}, "X "), el("span", {}, "Descartar região"));
  reject.onclick = () => decide(null);
  actions.append(reject);
  card.append(actions);
  const done = ITEMS.filter(i => i.status !== "pending").length;
  document.getElementById("progress").textContent =
    `caso ${index + 1} de ${ITEMS.length} · ${done} decididos`;
}

async function decide(text) {
  const item = ITEMS[index];
  await fetch("/review", { method: "POST", body: JSON.stringify({ key: item.key, text }) });
  item.text = text === null ? null : collapse(text);
  item.status = text === null ? "rejected" : "reviewed";
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
  if (event.target.tagName === "INPUT") return;
  const key = event.key.toLowerCase();
  const option = Number(key) - 1;
  if (Number.isInteger(option) && option >= 0 && option < ITEMS[index].options.length) {
    decide(collapse(ITEMS[index].options[option]));
  } else if (key === "d") {
    event.preventDefault();
    document.getElementById("typed").focus();
  } else if (key === "x") decide(null);
  else if (key === "arrowleft") go(-1);
  else if (key === "arrowright") go(1);
});

render();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    raise SystemExit(main())
