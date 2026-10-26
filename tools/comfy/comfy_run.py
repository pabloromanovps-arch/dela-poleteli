#!/usr/bin/env python3
"""Пакетная генерация через ComfyUI (локальный сервер) из таблицы. Только стандартная библиотека.

Как подготовить:
  1. В ComfyUI соберите рабочий workflow и сохраните «Save (API Format)» -> workflow_api.json
  2. Опишите, какие входы менять, в map.json: {"колонка_csv": ["node_id", "input_name"], ...}
  3. Таблица data/*.csv: одна строка = одна генерация (колонки из map + id)
Запуск:
  python tools/comfy/comfy_run.py --workflow workflow_api.json --map map.json --csv data/scenes.csv --out ai/renders
Опции: --server http://127.0.0.1:8188  --seed-col seed  --dry-run  --log ai/prompts/library.yaml

СТАТУС: протокол HTTP-API ComfyUI (/prompt, /history, /view) реализован по документации и проверен
только на имитации сервера, на настоящем ComfyUI не запускался.
"""
import argparse, copy, csv, json, sys, time, urllib.parse, urllib.request
from datetime import datetime
from pathlib import Path


def http(method, url, data=None):
    req = urllib.request.Request(url, method=method,
                                 data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def apply_row(wf, mapping, row):
    w = copy.deepcopy(wf)
    for col, (node, inp) in mapping.items():
        if col in row and row[col] != "":
            v = row[col]
            old = w[str(node)]["inputs"].get(inp)
            if isinstance(old, bool):
                v = v.lower() in ("1", "true", "yes", "да")
            elif isinstance(old, int):
                v = int(float(v))
            elif isinstance(old, float):
                v = float(v)
            w[str(node)]["inputs"][inp] = v
    return w


def run_one(server, wf, timeout):
    pid = json.loads(http("POST", f"{server}/prompt", {"prompt": wf, "client_id": "dela-poleteli"}))["prompt_id"]
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = json.loads(http("GET", f"{server}/history/{pid}"))
        if pid in h:
            files = []
            for out in h[pid].get("outputs", {}).values():
                for key in ("images", "gifs", "videos"):
                    files += out.get(key, [])
            return pid, files
        time.sleep(2)
    raise TimeoutError(f"prompt {pid}: нет результата за {timeout} с")


def download(server, f, dest):
    q = urllib.parse.urlencode({"filename": f["filename"], "subfolder": f.get("subfolder", ""),
                                "type": f.get("type", "output")})
    dest.write_bytes(http("GET", f"{server}/view?{q}"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", default="ai/renders")
    ap.add_argument("--server", default="http://127.0.0.1:8188")
    ap.add_argument("--seed-col", default="seed")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--log", default="ai/prompts/library.yaml")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    wf = json.loads(Path(a.workflow).read_text(encoding="utf-8"))
    mapping = json.loads(Path(a.map).read_text(encoding="utf-8"))
    rows = list(csv.DictReader(open(a.csv, encoding="utf-8")))
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    log = []
    for i, row in enumerate(rows, 1):
        rid = row.get("id") or f"{i:03d}"
        w = apply_row(wf, mapping, row)
        if a.dry_run:
            print(f"[{rid}] ok (dry-run)")
            continue
        try:
            pid, files = run_one(a.server, w, a.timeout)
        except Exception as e:
            print(f"[{rid}] ОШИБКА: {e}", file=sys.stderr)
            continue
        saved = []
        for n, f in enumerate(files):
            dest = out / f"{rid}_{n}{Path(f['filename']).suffix}"
            download(a.server, f, dest)
            saved.append(dest.name)
        print(f"[{rid}] {len(saved)} файл(ов): {', '.join(saved)}")
        log.append({"id": rid, "time": datetime.now().isoformat(timespec="seconds"),
                    "workflow": a.workflow, "row": row, "files": saved, "prompt_id": pid})
    if log:
        lp = Path(a.log); lp.parent.mkdir(parents=True, exist_ok=True)
        with open(lp, "a", encoding="utf-8") as f:
            for e in log:
                f.write("- " + json.dumps(e, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
