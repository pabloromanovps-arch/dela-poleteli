#!/usr/bin/env python3
"""Видео или ссылка -> заготовка заметки в references/cases/<имя>.md.

Что делает: контактный лист кадров (ffmpeg), расшифровка речи (faster-whisper, если стоит),
черновик заметки со статусом ВИДЕЛ. Сам ролик остаётся в references/_inbox/ (в git не попадает).

  python tools/video_notes.py путь/к/ролику.mp4 --name gef26
  python tools/video_notes.py https://... --name case_x      # нужен yt-dlp, только для личного разбора
"""
import argparse, json, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "references" / "_inbox"
CASES = ROOT / "references" / "cases"


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def fetch(src):
    if Path(src).exists():
        return Path(src)
    if not shutil.which("yt-dlp"):
        sys.exit("Для ссылок нужен yt-dlp (pip install yt-dlp) или скачайте файл вручную.")
    INBOX.mkdir(parents=True, exist_ok=True)
    out = INBOX / "%(title).60s.%(ext)s"
    r = sh(["yt-dlp", "-f", "mp4/best", "-o", str(out), "--print", "after_move:filepath", src])
    if r.returncode:
        sys.exit(r.stderr[-500:])
    return Path(r.stdout.strip().splitlines()[-1])


def probe(video):
    r = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height,r_frame_rate",
            "-of", "json", str(video)])
    d = json.loads(r.stdout)
    st = [s for s in d.get("streams", []) if "width" in s]
    return float(d["format"]["duration"]), st[0]["width"], st[0]["height"]


def sheet(video, out, dur, w, h, step):
    cols = 6
    n = max(1, int(dur / step))
    rows = -(-n // cols)
    tw = 320 if w >= h else 200
    th = int(tw * h / w)
    sh(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf",
        f"fps=1/{step},scale={tw}:{th},tile={cols}x{rows}", "-frames:v", "1", str(out)])


def transcribe(video):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    segs, _ = WhisperModel("small", compute_type="int8").transcribe(str(video), vad_filter=True)
    return [(s.start, s.text.strip()) for s in segs]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--name", required=True)
    ap.add_argument("--step", type=float, default=2.0, help="секунд между кадрами листа")
    a = ap.parse_args()
    if not shutil.which("ffmpeg"):
        sys.exit("Нужен ffmpeg в PATH.")
    video = fetch(a.source)
    dur, w, h = probe(video)
    CASES.mkdir(parents=True, exist_ok=True)
    png = CASES / f"{a.name}_sheet.png"
    sheet(video, png, dur, w, h, a.step)
    tr = transcribe(video)
    lines = [f"# Кейс: {a.name}", "",
             f"Источник: {a.source}", f"Файл: {video.name} ({dur:.1f} с, {w}×{h})",
             f"Статус референса: ВИДЕЛ (кадры раз в {a.step:g} с, лист `{png.name}`)"
             + ("; речь расшифрована" if tr else "; речь НЕ расшифрована (нет faster-whisper)"), "",
             "## Что увидел (заполнить по листу)", "- ", "",
             "## Что берём / что не берём", "- берём: ", "- не берём: ", ""]
    if tr:
        lines += ["## Расшифровка речи"] + [f"- [{t:5.1f} с] {x}" for t, x in tr] + [""]
    (CASES / f"{a.name}.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"готово: {CASES / (a.name + '.md')} и {png}")


if __name__ == "__main__":
    main()
