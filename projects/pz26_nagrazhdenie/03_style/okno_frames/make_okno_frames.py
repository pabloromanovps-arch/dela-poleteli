#!/usr/bin/env python3
"""Стайлфреймы «Просвет» K1/K2/K3 — рифлёное стекло, ночной фасад, окно.

Одна команда (из любой папки):
    python3 make_okno_frames.py                # всё: k1, k2, k3, лист, замеры
    python3 make_okno_frames.py --only k1 sheet
    python3 make_okno_frames.py --out /tmp/x   # другой каталог вывода

Холст проекта 7680x1536 (левый 1536 + центр 4608 + правый 1536; стыки x=1536 и 6144,
мёртвая зона ~12 px — ДОПУЩЕНИЕ профиля). Мастер рендерится в 3840x768 (масштаб 0.5),
превью 1920x384. Вся геометрия задана в координатах холста (CX), перевод S=0.5.
Работа в линейном свете (гамма 2.2). Без Blender: numpy/scipy/PIL.
Seed фиксирован — результат воспроизводим.
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import (gaussian_filter, gaussian_filter1d, uniform_filter1d,
                           distance_transform_edt)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
W, H = 3840, 768          # мастер
S = 0.5                   # холст -> мастер
SEAMS = (1536 * S, 6144 * S)  # x стыков в мастере: 768, 3072
DEAD = 6                  # мёртвая зона 12 px холста = 6 px мастера

# ---- палитра бренда (brands/pz_premiya/brand.yaml) и роли ------------------
def hexrgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255.0

C_DARK = hexrgb("#002935")      # цвет тьмы/тени
C_PRIMARY = hexrgb("#0B3139")
C_SECOND = hexrgb("#2F4A4B")    # стена фасада в свету (#2B4F52 бренда, чуть десатурирован)
C_TEXT = hexrgb("#EFE9DC")      # тёплый белый (чуть ниже F4EFE4, чтобы не пересветить)
WARM_LAMP = np.array([0.90, 0.64, 0.38], np.float32)   # ~2800 K, дисплейные значения
WARM_HOT = np.array([0.95, 0.82, 0.62], np.float32)    # ядро лампы ~3000 K
BRASS_LIGHT = np.array([0.93, 0.76, 0.50], np.float32)  # латунь только как блик

FONT_NAME = "/usr/share/fonts/opentype/inter/InterDisplay-Medium.otf"   # ВРЕМЕННЫЙ шрифт
FONT_BODY = "/usr/share/fonts/opentype/inter/Inter-Regular.otf"

# ---- параметры (в одном месте; их же пишет README) -------------------------
P = dict(
    rib_pitch=26.0,       # шаг рифления, мастер px (52 px холста)
    rib_jitter=0.07,      # разброс ширины ребра
    rib_amp_gain=1.9,     # A = gain*p/(2*pi): производная смещения 1-gain..1+gain
    rib_amp_jitter=0.10,
    disp=0.12,            # дисперсия: R -12 %, B +12 % амплитуды смещения
    blur_box=64,          # расфокус по вертикали: бокс (px мастера) ...
    blur_sigma=14.0,       # ... и гаусс
    grain=1.7,            # зерно, LSB
    peak_cap=0.93,        # потолок канала после roll-off (237/255)
    pre_sigma=9.0,
    pre_sigma_lit=2.0,        # горизонтальный предфильтр мира (мастер px): мелкая фактура фасада не штрихкодит
    seed=2611,
)

LIT_W, LIT_H = 48, 72            # окно лауреата в мастере (96x144 на холсте)
PITCH_X, PITCH_Y = 75.0, 96.0    # шаг фасада
ROW0 = 84.0
SECTOR_K = [4, 15, 20, 25, 30, 35, 46]       # центральная ось сектора (номер оси)
SECTOR_F = [1, 2, 1, 2, 1, 2, 1]             # верхний этаж пары (этажи f и f+2)
SECTOR_HOLE = [(1, 2), (0, 0), (1, 0), (0, 2), (1, 1), (0, 1), (1, 2)]  # (ряд, колонка) без огня


# ============================================================================
# утилиты
# ============================================================================
def s2l(x):
    return np.power(np.clip(x, 0, None), 2.2)


def l2s(x):
    return np.power(np.clip(x, 0, None), 1 / 2.2)


def smooth_noise(shape, sigma, seed):
    rs = np.random.RandomState(seed)
    n = gaussian_filter(rs.randn(*shape).astype(np.float32), sigma, mode="wrap")
    return n / (n.std() + 1e-9)


def cov1d(n0, n1, a, b):
    px = np.arange(n0, n1, dtype=np.float32)
    return np.clip(np.minimum(px + 1, b) - np.maximum(px, a), 0, 1)


def rect_cov(x0, y0, x1, y1, w=None, h=None):
    w = w or W
    h = h or H
    X0, X1 = max(int(np.floor(x0)), 0), min(int(np.ceil(x1)), w)
    Y0, Y1 = max(int(np.floor(y0)), 0), min(int(np.ceil(y1)), h)
    if X1 <= X0 or Y1 <= Y0:
        return None, None
    cx = cov1d(X0, X1, x0, x1)
    cy = cov1d(Y0, Y1, y0, y1)
    return (slice(Y0, Y1), slice(X0, X1)), cy[:, None] * cx[None, :]


def paint(img, rect, color, alpha=1.0):
    sl, c = rect_cov(*rect, w=img.shape[1], h=img.shape[0])
    if sl is None:
        return
    a = (c * alpha)[..., None]
    col = color(sl) if callable(color) else np.asarray(color, np.float32)
    img[sl] = img[sl] * (1 - a) + col * a


def sector_slots():
    """35 огней: список (ось k, этаж r, сектор) — 7 секторов по 5 из 6 слотов."""
    out = []
    for s, (kc, f, hole) in enumerate(zip(SECTOR_K, SECTOR_F, SECTOR_HOLE)):
        for row in (0, 1):
            for col in (0, 1, 2):
                if (row, col) == hole:
                    continue
                out.append((kc - 1 + col, f + 2 * row, s))
    assert len(out) == 35
    return out


def win_center(k, r):
    return PITCH_X * (k + 0.5), ROW0 + PITCH_Y * r


# ============================================================================
# мир за стеклом: резкий ночной фасад (линейный свет не нужен, строим в дисплейных значениях)
# ============================================================================
def lit_window_template():
    """Одинаковое окно лауреата: тёплый интерьер, штора слева, лампа справа, переплёт."""
    w, h = LIT_W, LIT_H
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u, v = xx / w, yy / h
    base = np.array([0.82, 0.58, 0.35], np.float32)
    img = np.ones((h, w, 3), np.float32) * base
    img *= (0.92 + 0.14 * (1 - v))[..., None]                 # потолок чуть темнее низа? свет сверху — ярче вверху
    curtain = np.clip((0.34 - u) / 0.08, 0, 1)
    folds = 0.80 + 0.20 * np.sin(xx * 1.9)
    img *= (1 - curtain * (1 - 0.55 * folds))[..., None]
    lamp = np.exp(-(((u - 0.70) / 0.17) ** 2 + ((v - 0.36) / 0.15) ** 2))
    img = img * (1 - lamp[..., None]) + WARM_HOT * lamp[..., None] * 1.02
    # переплёт: рама, средник, форточка — силуэтом против света
    fr = np.zeros((h, w), np.float32)
    fr[:3, :] = 1; fr[-3:, :] = 1; fr[:, :3] = 1; fr[:, -3:] = 1
    fr[:, w // 2 - 1:w // 2 + 1] = 1
    fr[int(h * 0.28):int(h * 0.28) + 2, :] = 1
    frame_col = np.array([0.16, 0.08, 0.05], np.float32)
    img = img * (1 - fr[..., None]) + frame_col * fr[..., None]
    return img


def build_facade(seed=11):
    """Резкий мир. Возвращает (база: стена+тёмные окна, дисплейный RGB; маска огней; светящиеся окна, дисплейный RGB)."""
    rs = np.random.RandomState(seed)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    # свет на стене: бассейн в центре кадра, к краям и верху темнее; низ темнее (цоколь в тени)
    ix = 0.45 + 0.55 * np.clip(np.cos((xx / W - 0.5) * np.pi * 0.96), 0, 1) ** 1.2
    iy = np.interp(yy[:, 0], [0, 0.12 * H, 0.50 * H, 0.82 * H, H], [0.38, 0.62, 1.05, 0.80, 0.42])
    illum = ix * iy[:, None]
    stucco = 1 + 0.045 * smooth_noise((H, W), 0.8, seed + 1) + 0.07 * smooth_noise((H, W), 7, seed + 2)
    # крупное «погодное» пятно неравномерности
    stucco *= 1 + 0.10 * smooth_noise((H, W), 90, seed + 3)
    wall = C_SECOND[None, None, :] * (illum * stucco)[..., None]
    img = wall.astype(np.float32)

    # пилястры через каждые 4 оси: светлая грань слева, тень справа
    for j in range(0, int(W / (PITCH_X * 4)) + 2):
        x = PITCH_X * 4 * j
        paint(img, (x - 8, 36, x + 8, H), lambda sl: img[sl] * 1.10)
        paint(img, (x - 8, 36, x - 5, H), lambda sl: img[sl] * 1.06)
        paint(img, (x + 5, 36, x + 11, H), lambda sl: img[sl] * 0.80, 0.8)
    # карниз: фриз, губа, падающая тень
    paint(img, (0, 0, W, 26), lambda sl: img[sl] * 1.02)
    paint(img, (0, 26, W, 33), lambda sl: img[sl] * 1.42)
    sh = np.interp(np.arange(33, 70), [33, 40, 70], [0.30, 0.42, 1.0])
    img[33:70] *= sh[:, None, None]
    # цоколь: рустовка
    base_y = ROW0 + PITCH_Y * 6 + LIT_H / 2 + 20
    paint(img, (0, base_y, W, H), lambda sl: img[sl] * 0.78)
    for y in np.arange(base_y + 8, H, 12):
        paint(img, (0, y, W, y + 1.4), lambda sl: img[sl] * 0.55)

    tpl = lit_window_template()
    lit = {(k, r): s for k, r, s in sector_slots()}
    emis = np.zeros((H, W), np.float32)
    emi = np.zeros((H, W, 3), np.float32)
    wcol = np.array([0.050, 0.140, 0.150], np.float32)
    nk = int(W / PITCH_X) + 1
    for r in range(7):
        for k in range(nk):
            cx, cy = win_center(k, r)
            x0 = float(round(cx - LIT_W / 2)); x1 = x0 + LIT_W
            y0 = float(round(cy - LIT_H / 2)); y1 = y0 + LIT_H
            # потёки под подоконником (неравномерный износ)
            sl_s = rs.rand()
            if r < 6:
                ln = 30 + 40 * rs.rand()
                paint(img, (cx - 9, y1 + 12, cx + 9, y1 + 12 + ln),
                      lambda sl: img[sl] * (1 - 0.20 * sl_s * np.linspace(1, 0.1, sl[0].stop - sl[0].start)[:, None, None]), 1.0)
            # наличник, подоконник
            paint(img, (x0 - 4, y0 - 4, x1 + 4, y1 + 4), lambda sl: img[sl] * 1.08)
            paint(img, (x0 - 7, y1 + 4, x1 + 7, y1 + 8), lambda sl: img[sl] * 1.25)
            paint(img, (x0 - 6, y1 + 8, x1 + 6, y1 + 15),
                  lambda sl: img[sl] * np.linspace(0.45, 0.9, sl[0].stop - sl[0].start)[:, None, None], 0.9)
            is_lit = (k, r) in lit
            if is_lit:
                v = 1.0 + 0.015 * rs.randn()
                sl2, c2 = rect_cov(x0, y0, x1, y1)
                emi[sl2] += _tpl_slice(tpl, sl2, x0, y0) * v * c2[..., None]
                emis[sl2] = np.maximum(emis[sl2], c2)
            if True:
                refl = 0.8 + 0.4 * rs.rand()
                def glass(sl, refl=refl):
                    hh = sl[0].stop - sl[0].start
                    ww = sl[1].stop - sl[1].start
                    gy, gx = np.mgrid[0:hh, 0:ww].astype(np.float32)
                    t = np.clip((gx / max(ww, 1) * 0.6 + gy / max(hh, 1) * 0.4), 0, 1)
                    g = wcol[None, None, :] * (1 + 2.2 * t[..., None]) * refl * (0.7 + 0.5 * illum[sl][..., None])
                    return g
                paint(img, (x0, y0, x1, y1), glass)
                # рама и средник тёмные
                paint(img, (cx - 1, y0, cx + 1, y1), lambda sl: img[sl] * 0.35)
                paint(img, (x0, y0 + LIT_H * 0.28, x1, y0 + LIT_H * 0.28 + 2), lambda sl: img[sl] * 0.35)
    # тёплый спилл от огней на стену (линейный свет)
    spill = gaussian_filter(emis, 20) * 1.0 + gaussian_filter(emis, 6) * 0.5
    lin = s2l(img)
    wl = s2l(C_SECOND)[None, None, :] * (illum * stucco)[..., None] ** 2.2
    warm = s2l(WARM_LAMP)[None, None, :]
    lin += wl * warm * (0.55 * spill * (1 - emis))[..., None] * 2.0
    img = l2s(lin).astype(np.float32)
    return img, emis, emi


def _tpl_slice(tpl, sl, x0, y0):
    ys = sl[0].start - int(np.floor(y0))
    xs = sl[1].start - int(np.floor(x0))
    hh = sl[0].stop - sl[0].start
    ww = sl[1].stop - sl[1].start
    ty = np.clip(np.arange(ys, ys + hh), 0, tpl.shape[0] - 1)
    tx = np.clip(np.arange(xs, xs + ww), 0, tpl.shape[1] - 1)
    return tpl[ty][:, tx]


# ============================================================================
# рифлёное стекло
# ============================================================================
def rib_geometry(seed):
    rs = np.random.RandomState(seed)
    p = P["rib_pitch"]
    n = int(W / p) + 6
    widths = p * np.clip(1 + P["rib_jitter"] * rs.randn(n), 0.8, 1.2)
    b = np.cumsum(np.concatenate([[-rs.rand() * p], widths]))
    xs = np.arange(W, dtype=np.float32) + 0.5
    idx = np.searchsorted(b, xs) - 1
    t = (xs - b[idx]) / (b[idx + 1] - b[idx])
    amp_i = np.clip(1 + P["rib_amp_jitter"] * rs.randn(n), 0.7, 1.3)
    lum_i = 1 + 0.10 * rs.randn(n)           # неодинаковая яркость рёбер
    hl_i = np.clip(1 + 0.45 * rs.randn(n), 0.2, 2.0)  # сила блика на ребре
    return dict(idx=idx, t=t.astype(np.float32), amp=amp_i[idx].astype(np.float32),
                lum=lum_i[idx].astype(np.float32), hl=hl_i[idx].astype(np.float32), p=p)


def disp_field(geo, fade=None):
    """Смещение по x для каждого пикселя (H, W); fade (H,W) — множитель амплитуды (снятие стекла)."""
    A = P["rib_amp_gain"] * geo["p"] / (2 * np.pi)
    d = A * geo["amp"] * np.sin(2 * np.pi * geo["t"])           # (W,)
    d = np.broadcast_to(d[None, :], (H, W)).astype(np.float32)
    if fade is not None:
        d = d * fade
    return d


def sample_x(img, xs):
    """Линейная выборка img (H,W,C) по x-координатам xs (H,W) — те же строки."""
    xs = np.clip(xs, 0, W - 1.001)
    x0 = np.floor(xs).astype(np.int32)
    f = (xs - x0)[..., None]
    rows = np.arange(H)[:, None]
    return img[rows, x0] * (1 - f) + img[rows, x0 + 1] * f


def flute(world_lin, geo, fade=None, emit_lin=None):
    """Рифлёное стекло: смещение по синусоиде + дисперсия + расфокус по вертикали.
    world_lin — линейный свет (H,W,3). fade (H,W) 0..1: 1 — полное стекло, 0 — чисто."""
    pre = gaussian_filter1d(world_lin, P['pre_sigma'], axis=1)   # мелкая фактура фасада (стена, переплёты) смазана до рифления
    if emit_lin is not None:                                    # огни окон — почти резкие, чтобы рифление рвало их на штрихи
        pre = pre + gaussian_filter1d(emit_lin, P['pre_sigma_lit'], axis=1)
    d = disp_field(geo, fade)
    xs = np.arange(W, dtype=np.float32)[None, :] + 0.5 + d
    out = np.empty_like(world_lin)
    for c, k in enumerate((1 - P["disp"], 1.0, 1 + P["disp"])):
        base = np.arange(W, dtype=np.float32)[None, :] + d * k
        out[..., c] = sample_x(pre[..., c:c + 1], base)[..., 0]
    return vblur(out, fade)


def vblur(img, fade=None):
    """Расфокус по вертикали (бокс * гаусс). С fade — стек уровней с интерполяцией."""
    def one(f):
        if f <= 0.001:
            return img
        bx = max(1, int(round(P["blur_box"] * f)))
        o = uniform_filter1d(img, bx, axis=0, mode="nearest")
        return gaussian_filter1d(o, max(0.3, P["blur_sigma"] * f), axis=0, mode="nearest")
    if fade is None:
        return one(1.0)
    levels = [0.0, 0.25, 0.5, 0.75, 1.0]
    stack = [one(f) for f in levels]
    pos = np.clip(fade, 0, 1) * 4
    lo = np.clip(np.floor(pos).astype(int), 0, 3)
    fr = (pos - lo)[..., None]
    out = np.zeros_like(img)
    for i in range(4):
        sel = (lo == i)[..., None]
        out += sel * (stack[i] * (1 - fr) + stack[i + 1] * fr)
    return out


def glass_surface(geo, seed, strength=None):
    """Собственная жизнь стекла: блики/тени на рёбрах, микроцарапины. Возвращает (add_lin (H,W), mul (H,W))."""
    rs = np.random.RandomState(seed)
    t, hl, lum = geo["t"], geo["hl"], geo["lum"]
    prof_hl = np.exp(-((t - 0.20) / 0.07) ** 2) * hl          # блик у левой грани ребра
    prof_sh = np.exp(-((t - 0.86) / 0.10) ** 2)                # тень у правой
    yy = np.arange(H, dtype=np.float32)[:, None]
    xx = np.arange(W, dtype=np.float32)[None, :]
    # отражение мягкого источника: сильнее слева-сверху (софтбокс над залом), мягко гаснет
    refl = (0.25 + 0.75 * np.exp(-((xx / W - 0.22) / 0.40) ** 2)) * np.interp(yy, [0, 0.4 * H, H], [1.0, 0.55, 0.30])
    add = 0.0045 * refl * prof_hl[None, :]
    mul = (1 + 0.07 * (lum[None, :] - 1) * 4 / 4) * (1 - 0.10 * prof_sh[None, :]) * (1 + 0.06 * np.cos(2 * np.pi * t)[None, :])
    # микроцарапины: преимущественно вдоль рёбер, несколько косых
    sc = Image.new("L", (W, H), 0)
    dr = ImageDraw.Draw(sc)
    for _ in range(90):
        x = rs.rand() * W
        y = rs.rand() * H
        ln = 60 + rs.rand() * 360
        ang = np.deg2rad(90 + rs.randn() * 1.5)
        dr.line([(x, y), (x + np.cos(ang) * ln, y + np.sin(ang) * ln)], fill=int(25 + rs.rand() * 60), width=1)
    for _ in range(26):
        x = rs.rand() * W
        y = rs.rand() * H
        ln = 40 + rs.rand() * 160
        ang = np.deg2rad(rs.rand() * 180)
        dr.line([(x, y), (x + np.cos(ang) * ln, y + np.sin(ang) * ln)], fill=int(15 + rs.rand() * 35), width=1)
    scr = gaussian_filter(np.asarray(sc, np.float32) / 255.0, 0.5)
    add = add + 0.012 * scr * refl
    sheen = 1 + 0.16 * np.exp(-(((xx + 0.9 * yy) / W - 0.30) / 0.22) ** 2) - 0.08 * (xx / W)
    mul = mul * sheen
    return add.astype(np.float32), mul.astype(np.float32)


# ============================================================================
# ключ сверху (K1)
# ============================================================================
def key_overlay(x_c, y_tip):
    """Тонкий ключ, пришедший сверху: стержень + бородка. Возвращает (cov, lin-цвет) на холст мастера."""
    ss = 4
    im = Image.new("L", (W * 1 // 1, H), 0)
    big = Image.new("L", (80 * ss, int((y_tip + 30) * ss)), 0)
    d = ImageDraw.Draw(big)
    cx = 40 * ss
    d.rectangle([cx - 3.6 * ss, 0, cx + 3.6 * ss, y_tip * ss], fill=255)         # стержень 4.4 px
    # бородка: ступенчатый зубец ниже стержня справа
    d.rectangle([cx + 3.6 * ss, (y_tip - 20) * ss, cx + 14 * ss, (y_tip) * ss], fill=255)
    d.rectangle([cx + 3.6 * ss, (y_tip - 20) * ss, cx + 14 * ss, (y_tip - 14) * ss], fill=0)
    d.rectangle([cx + 3.6 * ss, (y_tip - 9) * ss, cx + 9 * ss, (y_tip - 4) * ss], fill=0)
    small = np.asarray(big.resize((80, int(y_tip + 30)), Image.LANCZOS), np.float32) / 255.0
    return small, x_c - 40


# ============================================================================
# постобработка
# ============================================================================
def finish(lin, seed, grain=None):
    """линейный -> дисплей, зерно, roll-off верхов, дизеринг -> uint8."""
    rs = np.random.RandomState(seed)
    d = l2s(lin)
    g = (grain if grain is not None else P["grain"]) / 255.0
    lum = d.mean(axis=2, keepdims=True)
    n = rs.randn(H, W, 1).astype(np.float32)
    n = gaussian_filter(n[..., 0], 0.55)[..., None]
    n = n / (n.std() + 1e-9)
    nc = rs.randn(H, W, 3).astype(np.float32) * 0.35
    d = d + g * (0.75 + 0.6 * np.sqrt(lum)) * (n + nc)
    cap = P["peak_cap"]
    knee = 0.78
    over = d > knee
    r = cap - knee
    d = np.where(over, knee + r * np.tanh((d - knee) / r), d)
    d = np.clip(d, 0, cap)
    out = d * 255.0 + rs.rand(H, W, 3).astype(np.float32) - 0.5
    return np.clip(np.round(out), 0, 255).astype(np.uint8)


def save_pair(arr, outdir, name):
    im = Image.fromarray(arr)
    im.save(os.path.join(outdir, name + ".png"))
    im.resize((W // 2, H // 2), Image.LANCZOS).save(os.path.join(outdir, name.split("_")[0] + "_preview.png"))


# ============================================================================
# K1
# ============================================================================
def render_k1(seed):
    world, emis, emi = build_facade()
    geo = rib_geometry(seed)
    lin = s2l(world) * (1 - emis[..., None])
    g = flute(lin, geo, emit_lin=s2l(emi))
    add, mul = glass_surface(geo, seed + 5)
    g = g * mul[..., None] + add[..., None] * np.array([0.85, 1.0, 1.0], np.float32)
    # ключ: перед стеклом, тонкий, мало света
    sl = sector_slots()[0]
    k, r, _ = sl
    cx, cy = win_center(k, r)
    y_tip = cy - LIT_H / 2 - 22
    ky, ox = key_overlay(cx, y_tip)
    h_, w_ = ky.shape
    # латунь: тусклый стержень, блик по левому краю и точка на кончике бородки
    col = np.zeros((h_, w_, 3), np.float32)
    xs = np.arange(w_)[None, :] - 40
    edge = np.exp(-((xs + 2.2) / 1.0) ** 2)
    shade = (0.22 + 1.0 * edge) * np.linspace(0.45, 1.0, h_)[:, None]
    col += s2l(BRASS_LIGHT)[None, None, :] * shade[..., None] * 0.55
    sub = g[0:h_, int(ox):int(ox) + w_]
    g[0:h_, int(ox):int(ox) + w_] = sub * (1 - ky[..., None]) + col * ky[..., None]
    # матовая подсветка стекла под кончиком ключа: рифлёная, не лучи
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    kk = np.exp(-(((xx - cx) / 36.0) ** 2 + ((yy - y_tip) / 46.0) ** 2))
    ribmod = 0.35 + 0.65 * (geo["hl"][None, :] * 0.6 + 0.4 * np.cos(2 * np.pi * geo["t"])[None, :] ** 2)
    g += s2l(WARM_LAMP)[None, None, :] * (0.07 * kk * ribmod)[..., None]
    return finish(g, seed + 9)


# ============================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=["k1", "k2", "k3", "sheet", "stats"])
    ap.add_argument("--out", default=HERE)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    seed = P["seed"]
    if "k1" in a.only:
        save_pair(render_k1(seed), a.out, "k1_glass")
        print("k1 ok")


if __name__ == "__main__":
    main()
