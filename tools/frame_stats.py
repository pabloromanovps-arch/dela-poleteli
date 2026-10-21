#!/usr/bin/env python3
"""Объективные замеры кадра для дизайн-контроля.

  python tools/frame_stats.py frame.png [--screen uhd_16x9] [--palette "#0C0C0E,#C9A227"]

Яркость по зонам (верх/центр/низ трети), тёплые/холодные пиксели, пересветы/провалы,
доли заданных цветов палитры (ближайший цвет), разрешение против профиля экрана.
"""
import argparse
import os

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("frame")
    p.add_argument("--screen")
    p.add_argument("--palette", help="HEX через запятую — доли пикселей по ближайшему цвету")
    a = p.parse_args()

    im = np.asarray(Image.open(a.frame).convert("RGB")).astype(np.float32)
    h, w, _ = im.shape
    lum = im @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    print(f"Размер: {w}×{h}")
    if a.screen:
        import yaml
        scr = yaml.safe_load(open(os.path.join(ROOT, "screens", a.screen + ".yaml"), encoding="utf-8"))
        cw, ch = scr["canvas"]["width"], scr["canvas"]["height"]
        print(f"Профиль {a.screen}: {cw}×{ch} — {'совпадает' if (w, h) == (cw, ch) else 'НЕ совпадает'}")

    thirds = np.array_split(lum, 3, axis=0)
    print("Яркость по третям (0–255): верх {:.0f} · центр {:.0f} · низ {:.0f}".format(*[t.mean() for t in thirds]))
    print(f"Средняя яркость {lum.mean():.0f}; пересвет (>250) {np.mean(lum > 250) * 100:.1f}%; "
          f"провал (<5) {np.mean(lum < 5) * 100:.1f}%")

    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    lit = lum > 20  # тёмные пиксели в оценку температуры не берём
    warm = np.mean((r - b > 15)[lit]) * 100 if lit.any() else 0
    cool = np.mean((b - r > 15)[lit]) * 100 if lit.any() else 0
    print(f"Температура (по пикселям ярче 20): тёплых {warm:.1f}% · холодных {cool:.1f}% · нейтральных {100 - warm - cool:.1f}%")

    if a.palette:
        cols = [c.strip().lstrip("#") for c in a.palette.split(",")]
        ref = np.array([[int(c[i:i + 2], 16) for i in (0, 2, 4)] for c in cols], dtype=np.float32)
        flat = im.reshape(-1, 3)[::7]  # подвыборка для скорости
        nearest = np.argmin(((flat[:, None, :] - ref[None]) ** 2).sum(-1), axis=1)
        shares = np.bincount(nearest, minlength=len(cols)) / len(nearest) * 100
        print("Палитра (доля пикселей по ближайшему цвету): " +
              " · ".join(f"#{c.upper()} {s:.0f}%" for c, s in zip(cols, shares)))


if __name__ == "__main__":
    main()
