#!/usr/bin/env python3
"""Контактный лист для ревью: кадры видео (через ffmpeg) или папка изображений → одна PNG-сетка.

  python tools/contact_sheet.py render.mov --every 1 --out 07_review/sheet_v01.png
  python tools/contact_sheet.py renders/players/ --out 07_review/players.png   # по одному кадру с каждого файла
"""
import argparse
import os
import subprocess
import tempfile

from PIL import Image, ImageDraw

IMG = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr", ".bmp")
VID = (".mov", ".mp4", ".mxf", ".avi", ".mkv")


def grab(video, t, dst):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", video, "-frames:v", "1", dst], check=True)
    return dst


def duration(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def collect(src, every, tmp):
    """Возвращает [(подпись, путь к кадру)]."""
    if os.path.isdir(src):
        items = []
        for name in sorted(os.listdir(src)):
            path = os.path.join(src, name)
            ext = os.path.splitext(name)[1].lower()
            if ext in IMG:
                items.append((name, path))
            elif ext in VID:
                d = duration(path)
                items.append((name, grab(path, d * 0.6, os.path.join(tmp, name + ".png"))))
        return items
    d = duration(src)
    t, items = 0.0, []
    while t < d:
        items.append((f"{t:6.2f}s", grab(src, t, os.path.join(tmp, f"{len(items):05d}.png"))))
        t += every
    return items


def sheet(items, cols, thumb_w, out):
    thumbs = []
    for label, path in items:
        im = Image.open(path).convert("RGB")
        im.thumbnail((thumb_w, thumb_w * 4))
        thumbs.append((label, im))
    th = max(im.height for _, im in thumbs)
    rows = (len(thumbs) + cols - 1) // cols
    pad, lab = 8, 22
    canvas = Image.new("RGB", (cols * (thumb_w + pad) + pad, rows * (th + lab + pad) + pad), (18, 18, 20))
    draw = ImageDraw.Draw(canvas)
    for i, (label, im) in enumerate(thumbs):
        x = pad + (i % cols) * (thumb_w + pad)
        y = pad + (i // cols) * (th + lab + pad)
        canvas.paste(im, (x, y))
        draw.text((x, y + th + 4), label, fill=(220, 220, 220))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    canvas.save(out)
    print(f"Контактный лист: {len(thumbs)} кадров → {out}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("src")
    p.add_argument("--every", type=float, default=1.0, help="шаг, секунды (для видео)")
    p.add_argument("--cols", type=int, default=6)
    p.add_argument("--thumb", type=int, default=480, help="ширина миниатюры, px")
    p.add_argument("--out", required=True)
    a = p.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        sheet(collect(a.src, a.every, tmp), a.cols, a.thumb, a.out)


if __name__ == "__main__":
    main()
