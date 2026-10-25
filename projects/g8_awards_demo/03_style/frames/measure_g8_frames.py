#!/usr/bin/env python3
"""Замеры кадров направления B: бэндинг 8 бит и читаемость резного имени (пишет measure_g8.txt)."""
import copy, os, sys
import numpy as np
from scipy import ndimage as ndi
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_g8_frames as M

def lum(a):
    return (a[..., :3].astype(np.float32) @ np.array([.2126, .7152, .0722], np.float32))

def legib(sc, img):
    """Майкельсон: штрих имени vs кольцо плиты вокруг (в яркости sRGB), в 1/4 и в 1/16"""
    L = lum(img); res = []
    for grp in sc.carv:
        for r in grp:
            if r["cap"] < 150: continue
            m = r["mask"] > .5
            ring = ndi.binary_dilation(m, iterations=7) & ~ndi.binary_dilation(m, iterations=2)
            a, b = L[m].mean(), L[ring].mean()
            # 1/16: усреднение по 4x4 перед сравнением
            L4 = ndi.uniform_filter(L, 4)
            a4, b4 = L4[m].mean(), L4[ring].mean()
            res.append((r["text"], a, b, abs(a - b) / (a + b + 1e-6), abs(a4 - b4) / (a4 + b4 + 1e-6)))
    return res

def band(img8, y0, y1, x0, x1):
    """средняя длина самой длинной серии одинаковых значений вдоль строки в гладком градиенте"""
    L = img8[y0:y1, x0:x1, 1].astype(int)
    runs = []
    for row in L:
        d = np.flatnonzero(np.diff(row) != 0)
        if len(d) < 2: continue
        runs.append(np.diff(d).max())
    return float(np.mean(runs)), float(np.max(runs))

out = []
for name, spec in M.FRAMES.items():
    spec["_name"] = name
    sc, img8, _ = M.render(spec)
    out.append("== %s" % name)
    for t, a, b, c, c4 in legib(sc, img8):
        out.append("  имя %-10s штрих %5.1f кольцо %5.1f  Майкельсон 1/4: %.2f  1/16: %.2f" % (t, a, b, c, c4))
# эксперимент: угол света и читаемость (b2: 35 против 9; b5: 9 против 35)
for name, ang in (("b2_artists", 9), ("b5_award", 35), ("b3_hosts", None)):
    spec = copy.deepcopy(M.FRAMES[name]); spec["build"] = M.FRAMES[name]["build"]; spec["_name"] = name
    if ang:
        for l in spec["lamps"]:
            l["z"] = (l["z"] / np.tan(np.deg2rad(l["angle"]))) * np.tan(np.deg2rad(ang)) if False else l["z"]
            d = l["z"] / np.tan(np.deg2rad(l["angle"])); l["angle"] = ang; l["z"] = d * np.tan(np.deg2rad(ang))
        sc, img8, _ = M.render(spec)
        out.append("== эксперимент %s при угле %d° (та же позиция лампы)" % (name, ang))
        for t, a, b, c, c4 in legib(sc, img8):
            out.append("  имя %-10s Майкельсон 1/4: %.2f  1/16: %.2f" % (t, c, c4))
# бэндинг: дизеринг вкл/выкл на b2, гладкий спад пятна (стена над фризом, x 1100-1500 пикс 1/4, y 80-250)
spec = M.FRAMES["b2_artists"]; spec["_name"] = "b2_artists"
for dith in (False, True):
    sc, img8, _ = M.render(spec, sim_dither=dith)
    out.append("бэндинг b2 стена над фризом, дизеринг=%s: средняя/макс. длина серии одинаковых значений (px 1/4) = %.1f / %.0f" % ((dith,) + band(img8, 90, 260, 1050, 1750)))
    out.append("   то же, нижняя полоса под фризом: %.1f / %.0f" % band(img8, 600, 690, 1000, 1900))
open(os.path.join(HERE, "measure_g8.txt"), "w", encoding="utf-8").write("\n".join(out))
print("\n".join(out))
