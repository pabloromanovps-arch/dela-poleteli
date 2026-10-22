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
    pre_sigma_lit=2.0,
    halo=0.22,            # доля рассеянного в толще стекла света окон
    halo_sigma=26.0,        # горизонтальный предфильтр мира (мастер px): мелкая фактура фасада не штрихкодит
    seed=2611,
)

LIT_W, LIT_H = 48, 72            # окно лауреата в мастере (96x144 на холсте)
PITCH_X, PITCH_Y = 75.0, 96.0    # шаг фасада
ROW0 = 130.0
SECTOR_K = [4, 15, 20, 25, 30, 35, 46]       # центральная ось сектора (номер оси)
SECTOR_F = [0, 2, 1, 2, 1, 2, 0]             # верхний этаж пары (этажи f и f+2); этажей 6 (0..5)
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


def aniso_noise(shape, sy, sx, seed):
    rs = np.random.RandomState(seed)
    n = gaussian_filter(rs.randn(*shape).astype(np.float32), (sy, sx), mode='wrap')
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
    wall = C_SECOND[None, None, :] * (illum * stucco)[..., None] * 0.92
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
    base_y = ROW0 + PITCH_Y * 5 + LIT_H / 2 + 20
    paint(img, (0, base_y, W, H), lambda sl: img[sl] * 0.78)
    for y in np.arange(base_y + 8, H, 12):
        paint(img, (0, y, W, y + 1.4), lambda sl: img[sl] * 0.55)

    tpl = lit_window_template()
    lit = {(k, r): s for k, r, s in sector_slots()}
    emis = np.zeros((H, W), np.float32)
    emi = np.zeros((H, W, 3), np.float32)
    wcol = np.array([0.080, 0.150, 0.155], np.float32)
    nk = int(W / PITCH_X) + 1
    for r in range(6):
        for k in range(nk):
            cx, cy = win_center(k, r)
            x0 = float(round(cx - LIT_W / 2)); x1 = x0 + LIT_W
            y0 = float(round(cy - LIT_H / 2)); y1 = y0 + LIT_H
            # потёки под подоконником (неравномерный износ)
            sl_s = rs.rand()
            if r < 5:
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
                    g = wcol[None, None, :] * (1 + 1.0 * t[..., None]) * refl * (0.7 + 0.5 * illum[sl][..., None])
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
        pre = pre + P['halo'] * gaussian_filter1d(emit_lin, P['halo_sigma'], axis=1)   # рассеяние света внутри стекла
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
    """Тонкий латунный ключ, пришедший сверху (стержень 8 px, бородка с двумя вырезами).
    Возвращает (cov (h,w), color_lin (h,w,3), x-смещение) — рисуется поверх стекла, резко."""
    ss = 4
    w_, h_ = 80, int(y_tip + 30)
    big = Image.new("L", (w_ * ss, h_ * ss), 0)
    d = ImageDraw.Draw(big)
    cx = 40 * ss
    d.rectangle([cx - 4 * ss, 0, cx + 4 * ss, y_tip * ss], fill=255)
    d.rectangle([cx + 4 * ss, (y_tip - 26) * ss, cx + 20 * ss, y_tip * ss], fill=255)
    d.rectangle([cx + 4 * ss, (y_tip - 26) * ss, cx + 20 * ss, (y_tip - 19) * ss], fill=0)
    d.rectangle([cx + 4 * ss, (y_tip - 13) * ss, cx + 13 * ss, (y_tip - 6) * ss], fill=0)
    cov = np.asarray(big.resize((w_, h_), Image.LANCZOS), np.float32) / 255.0
    yy, xx = np.mgrid[0:h_, 0:w_].astype(np.float32)
    u = xx - 40
    # латунь только как свет: тёмное тело + блик по левой грани + угол бородки
    body = 0.16 + 0.10 * np.clip(yy / y_tip, 0, 1)
    edgeL = np.exp(-((u + 3.0) / 0.9) ** 2) * (0.45 + 0.55 * np.clip(yy / y_tip, 0, 1) ** 1.5)
    edgeR = np.exp(-((u - 3.2) / 0.8) ** 2) * 0.18
    tip = np.exp(-(((u - 4.5) / 5.0) ** 2 + ((yy - (y_tip - 1)) / 3.0) ** 2)) * 0.9
    sh = np.clip(body + 0.75 * edgeL + edgeR + tip, 0, 0.95)
    col = s2l(BRASS_LIGHT)[None, None, :] * (sh ** 1.0)[..., None] * 1.0
    return cov, col.astype(np.float32), x_c - 40


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
def glass_base(seed, world_pack=None):
    """Мир за рифлёным стеклом + собственные блики стекла. Линейный свет (H,W,3)."""
    world, emis, emi = world_pack or build_facade()
    geo = rib_geometry(seed)
    lin = s2l(world) * (1 - emis[..., None])
    g = flute(lin, geo, emit_lin=s2l(emi))
    add, mul = glass_surface(geo, seed + 5)
    g = g * mul[..., None] + add[..., None] * np.array([0.85, 1.0, 1.0], np.float32)
    return g, geo, (world, emis, emi)


def add_key(g, geo):
    k, r, _ = sector_slots()[0]
    cx, cy = win_center(k, r)
    cx = float(round(cx - LIT_W / 2)) + LIT_W / 2
    y_tip = float(round(cy - LIT_H / 2)) - 24
    ky, col, ox = key_overlay(cx, y_tip)
    h_, w_ = ky.shape
    ox = int(round(ox))
    sub = g[0:h_, ox:ox + w_]
    g[0:h_, ox:ox + w_] = sub * (1 - ky[..., None]) + col * ky[..., None]
    # матовая подсветка стекла под кончиком ключа: рифлёная, не лучи
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    kk = np.exp(-(((xx - cx) / 34.0) ** 2 + ((yy - y_tip) / 44.0) ** 2))
    ribmod = 0.35 + 0.65 * (geo["hl"][None, :] * 0.6 + 0.4 * np.cos(2 * np.pi * geo["t"])[None, :] ** 2)
    g += s2l(WARM_LAMP)[None, None, :] * (0.07 * kk * ribmod)[..., None]
    return g


def render_k1(seed):
    g, geo, _ = glass_base(seed)
    g = add_key(g, geo)
    return finish(g, seed + 9)


# ============================================================================
# окно: геометрия, фаска, композиция
# ============================================================================
def sdf_rrect(xx, yy, x0, y0, x1, y1, r):
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hx, hy = (x1 - x0) / 2 - r, (y1 - y0) / 2 - r
    qx = np.abs(xx - cx) - hx
    qy = np.abs(yy - cy) - hy
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r


def sample_xy(img, xs, ys):
    """Билинейная выборка img (h,w,3) по (xs, ys) (любая форма)."""
    h, w = img.shape[:2]
    xs = np.clip(xs, 0, w - 1.001)
    ys = np.clip(ys, 0, h - 1.001)
    x0 = np.floor(xs).astype(np.int32)
    y0 = np.floor(ys).astype(np.int32)
    fx = (xs - x0)[..., None]
    fy = (ys - y0)[..., None]
    a = img[y0, x0] * (1 - fx) + img[y0, x0 + 1] * fx
    b = img[y0 + 1, x0] * (1 - fx) + img[y0 + 1, x0 + 1] * fx
    return a * (1 - fy) + b * fy


def poly_mask(points, size, ss=3, blur=0.0):
    w, h = size
    im = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(im).polygon([(x * ss, y * ss) for x, y in points], fill=255)
    m = np.asarray(im.resize((w, h), Image.LANCZOS), np.float32) / 255.0
    return gaussian_filter(m, blur) if blur > 0 else m


def ellipse_pts(cx, cy, rx, ry, rot=0.0, n=120, wob=None, seed=0, wob_amp=0.0):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    r = np.ones_like(t)
    if wob_amp > 0:
        rs = np.random.RandomState(seed)
        ph = rs.rand(4) * 6.28
        r = 1 + wob_amp * (np.sin(5 * t + ph[0]) * 0.5 + np.sin(11 * t + ph[1]) * 0.35 + np.sin(23 * t + ph[2]) * 0.2)
    x = rx * np.cos(t) * r
    y = ry * np.sin(t) * r
    c, s_ = np.cos(rot), np.sin(rot)
    return list(zip(cx + x * c - y * s_, cy + x * s_ + y * c))


# окно K2 в мастере: 500x625 (4:5), пересекает стык x=768
AX0, AY0, AW, AH = 505, 72, 500, 625
LAMP = (432.0, 218.0)     # лампа в локальных координатах окна
CONSOLE_V = 555           # линия кромки консоли (она же нить)
THREAD_Y = AY0 + CONSOLE_V


def build_interior(seed=5):
    """Тёплая комната (линейный свет, AH x AW x 3) + эмиссия лампы. Лицо не рисуется.
    Слои по глубине: фон (стена, шторы, лампа) — мягкий; фигура — почти резко; консоль — резко."""
    rs = np.random.RandomState(seed)
    yy, xx = np.mgrid[0:AH, 0:AW].astype(np.float32)
    lw = s2l(WARM_LAMP)
    lampc = s2l(WARM_HOT)
    # --- стена: обои вертикальной полосой (рифмуется со стеклом), свет от лампы
    albedo = np.array([0.52, 0.44, 0.35], np.float32)
    stripe = 1 + 0.08 * np.sin(2 * np.pi * xx / 15.0) + 0.05 * smooth_noise((AH, AW), 1.2, seed + 1) + 0.10 * smooth_noise((AH, AW), 28, seed + 2)
    d = np.hypot(xx - LAMP[0], (yy - LAMP[1]) * 0.9)
    lamp_i = 1.55 / (1 + (d / 95.0) ** 2) ** 1.0
    amb = np.array([0.010, 0.017, 0.019], np.float32)
    ceil = np.interp(yy[:, 0], [0, 110, 300, AH], [0.22, 0.55, 1.0, 0.85])[:, None]
    wall = s2l(albedo)[None, None, :] * (amb + lamp_i[..., None] * lw[None, None, :]) * (stripe * ceil)[..., None]
    # --- шторы слева: тёмная бирюза, глубокие складки
    cu = 240 + 6 * np.sin(yy / 160.0 + 1.0) + 7 * smooth_noise((AH, AW), 60, seed + 3)
    cm = np.clip((cu - xx) / 4.0, 0, 1)
    fold = 0.5 + 0.5 * np.sin(2 * np.pi * xx / 41.0 + 0.45 * np.sin(yy / 260.0) + 1.0 * aniso_noise((AH, AW), 160, 9, seed + 4) + 0.35 * np.sin(2 * np.pi * xx / 17.0 + 1.2 * aniso_noise((AH, AW), 120, 6, seed + 7)))
    fold_l = 0.10 + 0.90 * fold ** 1.6
    fine = 1 + 0.10 * smooth_noise((AH, AW), 1.0, seed + 5)
    curtain_alb = s2l(np.array([0.28, 0.40, 0.40], np.float32))
    ci = 0.05 + 0.55 * lamp_i
    curtain = curtain_alb[None, None, :] * (amb * 3 + ci[..., None] * lw[None, None, :] * 0.8) * (fold_l * fine)[..., None]
    img = wall * (1 - cm[..., None]) + curtain * cm[..., None]
    # --- панели под рейкой
    rail = 430
    img = img * (1 - 0.55 * (yy > rail).astype(np.float32)[..., None])
    img += (np.exp(-((yy - rail) / 1.4) ** 2) * lamp_i)[..., None] * lw[None, None, :] * 0.30
    # --- лампа (на фоне, мягкая): абажур с тканью
    shade_pts = [(LAMP[0] - 16, LAMP[1] - 38), (LAMP[0] + 16, LAMP[1] - 38), (LAMP[0] + 27, LAMP[1] + 38), (LAMP[0] - 27, LAMP[1] + 38)]
    sh = poly_mask(shade_pts, (AW, AH))
    gv = np.clip((yy - (LAMP[1] - 38)) / 76.0, 0, 1)
    gu = np.abs(xx - LAMP[0]) / 27.0
    fab = (0.80 + 0.20 * gv) * (1 - 0.25 * np.clip(gu, 0, 1) ** 2) * (1 + 0.025 * np.sin(xx * 2.0))
    shade_col = lampc[None, None, :] * fab[..., None] * 1.0
    img = img * (1 - sh[..., None]) + shade_col * sh[..., None]
    emit = sh[..., None] * shade_col
    # --- фон в мягком фокусе
    bg = gaussian_filter(img, (5.5, 5.5, 0))
    # лёгкая вуаль вокруг лампы (рассеяние в объективе), не флэр
    veil = gaussian_filter(emit.mean(axis=2), 18)
    bg = bg + veil[..., None] * lw[None, None, :] * 0.16
    # --- консоль, латунная кромка (резко)
    cons = np.clip(yy - (CONSOLE_V - 0.5), 0, 1)
    wood = s2l(np.array([0.13, 0.08, 0.055], np.float32))[None, None, :] * (0.25 + lamp_i[..., None] * 1.5) \
        * (1 + 0.18 * smooth_noise((AH, AW), 2, seed + 6) + 0.10 * np.sin(yy / 2.3))[..., None]
    wood = wood * np.interp(yy[:, 0], [CONSOLE_V, AH], [1.0, 0.22])[:, None, None]
    edge_i = 0.40 + 0.60 * np.exp(-((xx - LAMP[0]) / 300.0) ** 2)
    edge = np.exp(-((yy - (CONSOLE_V + 0.6)) / 1.0) ** 2) * edge_i
    top_glint = np.exp(-((yy - (CONSOLE_V - 1.6)) / 0.9) ** 2) * edge_i * 0.35      # блик на верхней грани
    # --- звонок на консоли (латунь только бликом)
    bx, br = 336.0, 17.0
    dxb, dyb = xx - bx, yy - (CONSOLE_V - 0.5)
    bell_m = np.clip(br - np.hypot(dxb, dyb * 1.0), 0, 1) * (yy < CONSOLE_V)
    nrm = np.clip(dxb / br, -1, 1)
    spec = np.exp(-(((xx - (bx + 6.5)) / 2.6) ** 2 + ((yy - (CONSOLE_V - 12)) / 3.6) ** 2))
    bell_col = s2l(BRASS_LIGHT)[None, None, :] * (0.025 + 0.12 * np.clip(nrm, 0, 1) ** 2 + 0.55 * spec)[..., None]
    # --- фигура лауреата: контровой свет справа, без лица
    hx, hy = 376.0, 216.0
    k = 0.80
    def F(px, py):                       # масштаб фигуры вокруг (hx, hy)
        return (hx + (px - hx) * k, hy + (py - hy) * k)
    head = poly_mask(ellipse_pts(hx, hy, 34, 45, rot=-0.10), (AW, AH))
    jaw = poly_mask(ellipse_pts(hx + 2, hy + 20, 28, 34, rot=-0.08), (AW, AH))
    hair = poly_mask(ellipse_pts(hx - 2, hy - 14, 37, 34, rot=-0.10, wob_amp=0.03, seed=seed + 8), (AW, AH))
    neck = poly_mask([(hx - 17, hy + 32), (hx + 20, hy + 32), (hx + 24, hy + 78), (hx - 27, hy + 78)], (AW, AH), blur=1.0)
    # плечи: вогнутая линия трапеции от шеи, угол плеча, руки вниз (неидеально: левое плечо ниже и дальше)
    body_pts = [(hx - 20, hy + 62), (hx - 40, hy + 80), (hx - 70, hy + 91), (hx - 100, hy + 102), (hx - 118, hy + 124), (hx - 123, hy + 170), (hx - 126, 520), (hx - 126, AH),
                (hx + 124, AH), (hx + 122, 520), (hx + 117, hy + 165), (hx + 104, hy + 120), (hx + 82, hy + 98), (hx + 54, hy + 84), (hx + 36, hy + 70), (hx + 22, hy + 62)]
    body = poly_mask(body_pts, (AW, AH))
    body = np.clip(gaussian_filter(body, 4.0) * 1.9 - 0.45, 0, 1)
    strands = Image.new("L", (AW * 3, AH * 3), 0)
    sd = ImageDraw.Draw(strands)
    rs2 = np.random.RandomState(seed + 21)
    for _ in range(22):                                    # выбившиеся волоски на контуре волос
        th = np.deg2rad(-100 + rs2.rand() * 130)
        ln = 3 + rs2.rand() * 6
        bend = rs2.randn() * 0.5
        pts = []
        for q in np.linspace(0, 1, 6):
            ang = th + bend * q
            pts.append(((hx - 2 + (37 + ln * q) * np.cos(ang)) * 3, (hy - 14 + (34 + ln * q) * np.sin(ang)) * 3))
        sd.line(pts, fill=int(110 + rs2.rand() * 110), width=1)
    strands = gaussian_filter(np.asarray(strands.resize((AW, AH), Image.LANCZOS), np.float32) / 255.0, 0.45)
    figure = np.clip(np.maximum.reduce([head, jaw, hair, neck, body, strands * 0.8]), 0, 1)
    figure = gaussian_filter(figure, 0.8)
    figure = np.where(yy >= CONSOLE_V, 0, figure)
    fb = gaussian_filter(figure, 1.8)
    gy, gx = np.gradient(fb)
    gn = np.hypot(gx, gy) + 1e-6
    nx, ny = -gx / gn, -gy / gn
    Ldir = np.array([LAMP[0] - hx + 20, LAMP[1] - hy - 6], np.float32)
    Ldir = Ldir / np.hypot(*Ldir)
    ndl = np.clip(nx * Ldir[0] + ny * Ldir[1], 0, 1)
    ins = distance_transform_edt(figure > 0.5)
    rim_w = np.where(yy < 262, 4.2, 3.2)
    wrap = np.clip(nx * Ldir[0] + ny * Ldir[1], 0, 1) ** 2.0 * np.exp(-ins / 16.0) * 0.30
    rim = (ndl ** 1.3 * np.exp(-ins / rim_w) + wrap) * (0.78 + 0.22 * smooth_noise((AH, AW), 3, seed + 9))
    rim *= np.interp(yy[:, 0], [0, 200, 340, 555], [1.0, 1.0, 0.75, 0.40])[:, None]
    rim = np.maximum(rim, strands * 0.35 * (0.5 + 0.5 * ndl))
    cool = np.clip(-nx, 0, 1) ** 1.6 * np.exp(-ins / 3.2) * 0.07
    body_col = s2l(np.array([0.048, 0.037, 0.030], np.float32))
    soft = (lamp_i / 1.55)[..., None]
    fig_col = body_col[None, None, :] * (1.4 + 7.0 * soft) + lampc[None, None, :] * (rim * 1.25)[..., None] \
        + s2l(np.array([0.30, 0.45, 0.47], np.float32))[None, None, :] * cool[..., None]
    face = np.exp(-(((xx - (hx - 2)) / 20.0) ** 2 + ((yy - (hy + 8)) / 28.0) ** 2))
    fig_col = fig_col * (1 - 0.35 * face[..., None])
    img = bg
    img = img * (1 - cons[..., None]) + wood * cons[..., None]
    img = img + (edge + top_glint)[..., None] * s2l(BRASS_LIGHT)[None, None, :] * 0.9
    # фигура стоит за консолью; звонок на консоли поверх фигуры
    img = img * (1 - figure[..., None]) + fig_col * figure[..., None]
    img = img * (1 - bell_m[..., None]) + bell_col * bell_m[..., None]
    # вуаль ещё раз на силуэт от лампы (контровой свет «заливает» край)
    img += (gaussian_filter(emit.mean(axis=2), 7) * 0.05)[..., None] * lw[None, None, :] * (figure[..., None])
    img = gaussian_filter(img, (0.55, 0.55, 0))
    return img.astype(np.float32), emit


def fit_card_lines(draw_font_fn, text, width):
    """Перенос по пробелам/дефису без висячих предлогов; возвращает строки."""
    words = text.replace(" «", "\u00a0«").split(" ")
    # неразрывные пробелы после коротких слов
    merged = []
    i = 0
    while i < len(words):
        wd = words[i]
        while len(wd) <= 2 and i + 1 < len(words):
            i += 1
            wd = wd + "\u00a0" + words[i]
        merged.append(wd)
        i += 1
    lines, cur = [], ""
    for wd in merged:
        t = (cur + " " + wd).strip()
        if draw_font_fn(t) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return [l.replace("\u00a0", " ") for l in lines]


def draw_card(lin, data, x_left=65, width=370, y_thread=THREAD_Y, report=None):
    """Карточка лауреата на боковом экране. ВРЕМЕННЫЙ шрифт Inter. Растёт вверх от нити; номинация под нитью."""
    name_parts = data["name"].split(" ")
    surname, given = " ".join(name_parts[:-1]), name_parts[-1]
    nsize_max, csize_max, nom_size = 50, 26, 21
    def fw(font):
        return lambda t: font.getlength(t)
    # имя: сначала фамилия целиком, если шире — по дефису
    nsize = nsize_max
    while nsize > 30:
        f = ImageFont.truetype(FONT_NAME, nsize)
        parts = surname.split("-")
        tokens = [parts[0] + ("-" if len(parts) > 1 else "")] + parts[1:] if len(parts) > 1 else [surname]
        if max(f.getlength(t) for t in tokens + [given]) <= width and f.getlength(surname) <= width:
            break
        if max(f.getlength(t) for t in tokens + [given]) <= width and len(parts) > 1:
            break
        nsize -= 1
    fN = ImageFont.truetype(FONT_NAME, nsize)
    sn_lines = [surname] if fN.getlength(surname) <= width else [parts[0] + "-"] + parts[1:]
    name_lines = sn_lines + [given]
    csize = csize_max
    while True:
        fC = ImageFont.truetype(FONT_BODY, csize)
        cl = fit_card_lines(fw(fC), data["company"], width)
        if len(cl) <= 3 or csize <= 22:
            break
        csize -= 1
    fO = ImageFont.truetype(FONT_BODY, nom_size)
    nl = fit_card_lines(fw(fO), data["nomination"], width)
    layer = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(layer)
    layers = []
    y = y_thread + 16                                       # номинация под нитью
    for l in nl:
        layers.append((l, fO, y, 0.70)); y += int(nom_size * 1.3)
    y_end = y
    y = y_thread - 20                                       # компания над нитью, снизу вверх
    for l in reversed(cl):
        y -= int(csize * 1.28)
        layers.append((l, fC, y, 0.78))
    y -= 18
    for i, l in enumerate(reversed(name_lines)):
        y -= int(nsize * 1.04)
        layers.append((l, fN, y, 1.0 if i == len(name_lines) - 1 else 0.90))   # фамилия 1.0, имя 0.90
    top = y
    # рисуем каждую яркость отдельным слоем
    res = lin.copy()
    for (txt, f, yy_, gain) in layers:
        lay = Image.new("L", (W, H), 0)
        ImageDraw.Draw(lay).text((x_left, yy_), txt, font=f, fill=255)
        a = np.asarray(lay, np.float32) / 255.0
        col = s2l(C_TEXT * (0.62 + 0.38 * gain) if gain < 1 else C_TEXT)
        res = res * (1 - a[..., None]) + col[None, None, :] * a[..., None]
    if report is not None:
        report.update(dict(name_size_master=nsize, name_size_canvas=nsize * 2, company_size_master=csize,
                           company_lines=len(cl), name_lines=len(name_lines), nomination_lines=len(nl),
                           block_top_y_canvas=top * 2, block_bottom_y_canvas=y_end * 2,
                           max_line_px_canvas=2 * max([fN.getlength(t) for t in name_lines] + [fC.getlength(t) for t in cl])))
    return res


CARD_DEFAULT = dict(name="Орлов Пётр", company="Сервис «Гид»", nomination="Лучшая городская гостиница")
CARD_WORST = dict(name="Константинопольская-Щедрина Анастасия",
                  company="Объединённая управляющая компания гостиничных и курортных активов «Пример»",
                  nomination="Лучшее решение для доступной среды")


def render_k2(seed, card=CARD_DEFAULT, report=None):
    g, geo, pack = glass_base(seed)
    interior, emit = build_interior()
    xx0, xx1 = AX0 - 70, AX0 + AW + 70
    yy0, yy1 = AY0 - 70, AY0 + AH + 70
    X, Y = np.meshgrid(np.arange(xx0, xx1, dtype=np.float32) + 0.5, np.arange(yy0, yy1, dtype=np.float32) + 0.5)
    sdf = sdf_rrect(X, Y, AX0, AY0, AX0 + AW, AY0 + AH, 5.0)
    # нормаль наружу
    gy_, gx_ = np.gradient(gaussian_filter(sdf, 0.8))
    gn = np.hypot(gx_, gy_) + 1e-6
    nx, ny = gx_ / gn, gy_ / gn
    BW = 14.0
    t = np.clip(sdf / BW, 0, 1)
    sub = g[yy0:yy1, xx0:xx1].copy()
    # --- мягкий тёплый спилл света комнаты в толщу стекла снаружи (по рёбрам)
    inside = np.clip(0.5 - sdf, 0, 1)
    room_mean = np.array([0.22, 0.12, 0.06], np.float32)
    sp = gaussian_filter(inside, 26) * (1 - inside)
    ribmod = (0.45 + 0.9 * geo["hl"][xx0:xx1] * 0.5 + 0.3 * np.cos(2 * np.pi * geo["t"][xx0:xx1]) ** 2)[None, :]
    sub += (sp * ribmod * 0.10)[..., None] * room_mean[None, None, :] * 2.2
    # --- фаска: рефракция по нормали, дисперсия, грани
    ring = (sdf > 0) & (sdf < BW)
    amp = (1 - t) ** 1.3
    shift = 34 * amp + 10 * np.sin(np.clip(t, 0, 1) * np.pi)
    ref = np.empty_like(sub)
    for c, k in enumerate((0.70, 1.0, 1.38)):             # дисперсия на фаске: умеренно
        ref[..., c] = sample_xy(sub[..., c:c + 1], (X - xx0) - nx * shift * k, (Y - yy0) - ny * shift * k * 0.55)[..., 0]
    # интерьер, продлённый за край (для отсвета комнаты в толще фаски)
    ii = np.zeros_like(sub)
    ii[AY0 - yy0:AY0 - yy0 + AH, AX0 - xx0:AX0 - xx0 + AW] = interior
    pad = np.pad(interior, ((70, 70), (70, 70), (0, 0)), mode="edge")
    room_e = sample_xy(pad, (X - AX0 + 70) - nx * (sdf + 6) * 1.0, (Y - AY0 + 70) - ny * (sdf + 6) * 1.0)
    # лампа (мировые x,y) для направления света на фаске
    Ld = np.array([AX0 + LAMP[0] - X, AY0 + LAMP[1] - Y])
    Lm = np.hypot(Ld[0], Ld[1]) + 1e-6
    ndl = np.clip(nx * Ld[0] / Lm + ny * Ld[1] / Lm, -1, 1)
    topleft = np.clip(-0.75 * ny - 0.55 * nx, 0, 1)             # грани, смотрящие на софтбокс сверху-слева
    facetA = (t < 0.55)
    shade = np.where(facetA, 0.80 + 0.30 * np.clip(ndl, 0, 1), 1.12 + 0.25 * np.clip(ndl, 0, 1))
    crease = np.exp(-((t - 0.55) / 0.04) ** 2)
    lampfall = np.exp(-(Lm / 420.0))
    kerb = np.exp(-((sdf - 0.9) / 0.85) ** 2) * (0.30 + 0.70 * lampfall) * (0.40 + 0.60 * np.clip(ndl + 0.5, 0, 1))
    outer = np.exp(-((sdf - BW + 1.3) / 0.75) ** 2) * (0.05 + 0.7 * topleft)
    # собственная отражённость фаски: мягкий холодный свет сверху-слева, чтобы кромка читалась как стекло
    glassy = 0.0 * topleft
    ring_col = ref * (shade * 1.35)[..., None] * (1 - 0.60 * crease[..., None])
    ring_col += room_e * ((1 - t) ** 1.1 * 0.55)[..., None]
    ring_col += glassy[..., None] * s2l(np.array([0.78, 0.86, 0.84], np.float32))[None, None, :]
    ring_col += kerb[..., None] * s2l(BRASS_LIGHT)[None, None, :] * 0.85
    ring_col += (crease * 0.012 * (0.4 + lampfall))[..., None] * s2l(WARM_LAMP)[None, None, :]
    ring_col += outer[..., None] * s2l(np.array([0.80, 0.88, 0.86], np.float32))[None, None, :] * 0.30
    ringm = np.clip(1 - np.clip(sdf - BW + 0.5, 0, 1), 0, 1) * np.clip(sdf + 0.5, 0, 1)
    out = sub * (1 - ringm[..., None]) + ring_col * ringm[..., None]
    # --- интерьер внутри проёма
    inn = inside[..., None]
    out = out * (1 - inn) + ii * inn
    g[yy0:yy1, xx0:xx1] = out
    # --- нить света от кромки консоли через стык к карточке (в стекле: рифлёная, неровная)
    xs = np.arange(0, AX0 - int(BW) + 2, dtype=np.float32)
    yy_ = np.arange(H, dtype=np.float32)[:, None]
    rl = (0.30 + 0.70 * np.clip(0.55 * geo["hl"][:len(xs)] + 0.55 * (np.cos(2 * np.pi * geo["t"][:len(xs)]) ** 2), 0, 1.4))
    wob = 0.0 * geo["t"][:len(xs)]
    fall = 0.20 + 0.80 * np.exp(-((AX0 - xs) / 230.0))
    fall = np.where(xs < 66, fall * np.clip((xs - 52) / 14.0, 0, 1) + 0, fall)          # конец у левого поля карточки
    prof = np.exp(-((yy_ - (THREAD_Y + 0.8 + wob[None, :])) / 1.15) ** 2)
    thr = prof * (rl * fall)[None, :]
    g[:, :len(xs)] += thr[..., None] * s2l(BRASS_LIGHT)[None, None, :] * 0.70
    g = draw_card(g, card, report=report)
    return finish(g, seed + 10)


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
    if "k2" in a.only:
        rep = {}
        save_pair(render_k2(seed, report=rep), a.out, "k2_window")
        print("k2 ok", rep)


if __name__ == "__main__":
    main()
