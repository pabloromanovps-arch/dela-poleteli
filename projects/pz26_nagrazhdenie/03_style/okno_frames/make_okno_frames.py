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
WARM_HOT = np.array([0.97, 0.89, 0.74], np.float32)    # ядро лампы ~3000 K
BRASS_LIGHT = np.array([0.93, 0.76, 0.50], np.float32)  # латунь только как блик

FONT_NAME = "/usr/share/fonts/opentype/inter/InterDisplay-Medium.otf"   # ВРЕМЕННЫЙ шрифт
FONT_BODY = "/usr/share/fonts/opentype/inter/Inter-Regular.otf"

# ---- параметры (в одном месте; их же пишет README) -------------------------
P = dict(
    rib_pitch=24.0,       # шаг рифления: 48 px холста (okno_direction п.2.1), стыки 1536/6144 попадают во впадину
    rib_jitter=0.0,       # ширина ребра строго постоянна (стык во впадине); неидеальность — в амплитуде/яркости рёбер
    rib_amp_gain=1.9,     # A = gain*p/(2*pi): производная смещения 1-gain..1+gain
    rib_amp_jitter=0.10,
    disp=0.12,            # дисперсия: R -12 %, B +12 % амплитуды смещения
    blur_box_wall=96,
    blur_sigma_wall=22.0,
    blur_box=44,          # расфокус по вертикали: бокс (px мастера) ...
    blur_sigma=10.0,       # ... и гаусс
    grain=1.7,            # зерно, LSB
    haze_floor=(0.0, 0.073, 0.090),   # дымка стекла: самое тёмное ~ код 14-20 (direction п.2.4)
    peak_cap=0.93,        # потолок канала после roll-off (237/255)
    pre_sigma=9.0,
    pre_sigma_lit=1.5,
    halo=0.14,            # доля рассеянного в толще стекла света окон
    halo_sigma=26.0,        # горизонтальный предфильтр мира (мастер px): мелкая фактура фасада не штрихкодит
    wall_gain=0.85,       # K1/K2: яркость стены за стеклом (подбор по замеру тона)
    emit_gain=2.05,       # яркость огней до стекла
    seed=2611,
)

LIT_W, LIT_H = 26, 52            # окно лауреата в мастере (72x108 на холсте)
PITCH_X, PITCH_Y = 75.0, 96.0    # шаг фасада
ROW0 = 130.0
SECTOR_K = [5, 13, 19, 25, 31, 37, 46]       # центральная ось сектора (номер оси)
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
def lit_window_template(sc=1):
    """Одинаковое окно лауреата: тёплый интерьер, штора слева, лампа справа, переплёт. sc — суперсэмплинг."""
    w, h = LIT_W * sc, LIT_H * sc
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u, v = xx / w, yy / h
    base = np.array([0.80, 0.63, 0.40], np.float32)
    img = np.ones((h, w, 3), np.float32) * base
    img *= (0.92 + 0.14 * (1 - v))[..., None]
    curtain = np.clip((0.34 - u) / 0.08, 0, 1)
    folds = 0.80 + 0.20 * np.sin(xx * 1.9 / sc)
    img *= (1 - curtain * (1 - 0.55 * folds))[..., None]
    lamp = np.exp(-(((u - 0.70) / 0.17) ** 2 + ((v - 0.36) / 0.15) ** 2))
    img = img * (1 - lamp[..., None]) + WARM_HOT * lamp[..., None] * 1.02
    fr = np.zeros((h, w), np.float32)
    t3 = 3 * sc
    fr[:t3, :] = 1; fr[-t3:, :] = 1; fr[:, :t3] = 1; fr[:, -t3:] = 1
    fr[:, w // 2 - sc:w // 2 + sc] = 1
    fr[int(h * 0.28):int(h * 0.28) + 2 * sc, :] = 1
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
    b = np.cumsum(np.concatenate([[0.0 - 2 * p], widths]))   # граница ребра ровно на x=0, 24, 48 ...
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


def displace(pre, geo, fade):
    d = disp_field(geo, fade)
    out = np.empty_like(pre)
    for c, k in enumerate((1 - P["disp"], 1.0, 1 + P["disp"])):
        base = np.arange(W, dtype=np.float32)[None, :] + d * k
        out[..., c] = sample_x(pre[..., c:c + 1], base)[..., 0]
    return out


def flute(world_lin, geo, fade=None, emit_lin=None):
    """Рифлёное стекло: смещение по синусоиде + дисперсия + расфокус по вертикали.
    world_lin — линейный свет стены/окон без огней (H,W,3); emit_lin — огни (почти резкие до стекла).
    Стена расфокусируется сильнее огней (стена дальше от стекла); fade (H,W) 0..1: 1 — полное стекло, 0 — чисто."""
    pre = gaussian_filter1d(world_lin, P['pre_sigma'], axis=1)
    out = vblur(displace(pre, geo, fade), fade, box=P["blur_box_wall"], sigma=P["blur_sigma_wall"])
    if emit_lin is not None:
        pl = gaussian_filter1d(emit_lin, P['pre_sigma_lit'], axis=1) + P['halo'] * gaussian_filter1d(emit_lin, P['halo_sigma'], axis=1)
        out = out + vblur(displace(pl, geo, fade), fade)
    return out


def vblur(img, fade=None, box=None, sigma=None):
    """Расфокус по вертикали (бокс * гаусс). С fade — стек уровней с интерполяцией."""
    def one(f):
        if f <= 0.001:
            return img
        bx = max(1, int(round((box or P["blur_box"]) * f)))
        o = uniform_filter1d(img, bx, axis=0, mode="nearest")
        return gaussian_filter1d(o, max(0.3, (sigma or P["blur_sigma"]) * f), axis=0, mode="nearest")
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
def key_overlay(x_c, y_tip, tilt_deg=5.0):
    """Латунный ключ (тёмная латунь, свет только по кромке), пришёл сверху, ось 5 градусов от вертикали.
    Стержень 12 px, плечо, бородка с тремя вырезами. Остриё — центр вращения и самая светлая точка.
    Возвращает (cov, color_lin, x0, y0) — левый верхний угол в мастере."""
    ss = 4
    w_, h_ = 200, int(y_tip + 70)
    big = Image.new("L", (w_ * ss, h_ * ss), 0)
    d = ImageDraw.Draw(big)
    cx = 90 * ss
    d.rounded_rectangle([cx - 6 * ss, -50 * ss, cx + 6 * ss, y_tip * ss], radius=5 * ss, fill=255)
    d.rectangle([cx - 12 * ss, (y_tip - 74) * ss, cx + 12 * ss, (y_tip - 66) * ss], fill=255)       # плечо
    d.rectangle([cx + 4 * ss, (y_tip - 46) * ss, cx + 40 * ss, (y_tip - 3) * ss], fill=255)        # бородка
    for (ya, yb, xa) in ((46, 38, 26), (32, 25, 14), (18, 9, 24)):                                # вырезы зубцов
        d.rectangle([(cx + xa * ss), (y_tip - ya) * ss, cx + 41 * ss, (y_tip - yb) * ss], fill=0)
    cov = np.asarray(big.resize((w_, h_), Image.LANCZOS), np.float32) / 255.0
    cb = gaussian_filter(cov, 1.1)
    gy, gx = np.gradient(cb)
    lit = np.clip(-(gx * 0.65 + gy * 0.75) * 2.2, 0, 1)                    # кромки, обращённые вверх-влево, ловят свет
    yy, xx = np.mgrid[0:h_, 0:w_].astype(np.float32)
    u = xx - 90
    cyl = np.exp(-((u + 3.2) / 2.0) ** 2) * (np.abs(u) < 7) * 0.5            # блик цилиндра на стержне
    body = 0.07 + 0.05 * np.clip(yy / y_tip, 0, 1)
    sh = np.clip(body + 1.05 * lit * (0.45 + 0.55 * np.clip(yy / y_tip, 0, 1) ** 1.2) + cyl * (0.4 + 0.9 * np.clip(yy / y_tip, 0, 1)), 0, 1.15)
    tip = np.exp(-(((u - 1.0) / 3.4) ** 2 + ((yy - (y_tip - 2.0)) / 2.6) ** 2)) * 1.0
    sh = sh + tip * 1.6
    col = s2l(BRASS_LIGHT)[None, None, :] * sh[..., None]
    arr = np.concatenate([cov[..., None], col], axis=2)
    chans = []
    for c in range(4):
        im = Image.fromarray(arr[..., c].astype(np.float32), mode="F")
        im = im.rotate(-tilt_deg, resample=Image.BICUBIC, center=(90, y_tip))
        chans.append(np.asarray(im))
    arr = np.stack(chans, axis=2)
    cov = np.clip(arr[..., 0], 0, 1)
    colr = np.clip(arr[..., 1:], 0, None).astype(np.float32)
    # расфокус растёт от острия к кольцу (резкость = близость к стеклу)
    yy2 = np.arange(h_, dtype=np.float32)[:, None]
    t = np.clip((y_tip - 70 - yy2) / 330.0, 0, 1)[..., None]
    covb = gaussian_filter(cov, 5.0); colb = gaussian_filter(colr * cov[..., None], (5.0, 5.0, 0)) / np.maximum(covb[..., None], 1e-3)
    cov = cov * (1 - t[..., 0]) + covb * t[..., 0]
    colr = colr * (1 - t) + colb * t
    return cov, colr, x_c - 90, 0


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
    mx = d.max(axis=2, keepdims=True)           # перегруженные блики уходят в белый (как плёнка/сенсор), цвет остаётся в средних
    hi = np.clip((mx - 0.85) / 0.30, 0, 1) * 0.85
    d = d * (1 - hi) + mx * hi
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
def glass_base(seed, world_pack=None, fade=None):
    """Мир за рифлёным стеклом + дымка + собственные блики стекла. Линейный свет (H,W,3)."""
    world, emis, emi = world_pack or build_facade()
    geo = rib_geometry(seed)
    lin = s2l(world) * (1 - emis[..., None]) * P['wall_gain']
    g = flute(lin, geo, fade=fade, emit_lin=s2l(emi) * P['emit_gain'])
    add, mul = glass_surface(geo, seed + 5)
    haze = s2l(np.array(P["haze_floor"], np.float32))
    gf = 1.0 if fade is None else fade[..., None]
    g = g * mul[..., None] + add[..., None] * np.array([0.85, 1.0, 1.0], np.float32) * gf
    g = g + haze[None, None, :] * 1.0                 # стекло поднимает чёрное: ночная бирюза, не 0
    return g, geo, (world, emis, emi)


def add_key(g, geo):
    cx, y_tip = 1250.0, 300.0           # ~32 % ширины (сдвинут с 35 % в воздух между секторами 2 и 3), остриё на ~39 % высоты (direction п.9 K1)
    ky, col, ox, oy = key_overlay(cx, y_tip)
    h_, w_ = ky.shape
    ox = int(round(ox)); oy = int(round(oy))
    y0 = max(oy, 0); y1 = min(oy + h_, H)
    sub = g[y0:y1, ox:ox + w_]
    kk = ky[y0 - oy:y1 - oy]; cc = col[y0 - oy:y1 - oy]
    g[y0:y1, ox:ox + w_] = sub * (1 - kk[..., None]) + cc * kk[..., None]
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


BW = 19.0
# окно K2 (мир-1, 16:9) в мастере 1100x619, пересекает стык x=768 (40 % слева)
AX0, AY0, AW, AH = 328, 74, 1100, 619
LAMP = (432.0, 218.0)     # лампа в локальных координатах окна
CONSOLE_V = 600           # линия кромки консоли (она же нить), чуть выше нижней грани окна (по direction п.8.3 нить на уровне низа)
THREAD_Y = AY0 + CONSOLE_V


RW, RH = 500, 625        # комната лауреата 4:5 (плейсхолдер: силуэт без лица)
RLAMP = (432.0, 218.0)
RCV = 600


def build_room(seed=5, wall_tint=(1, 1, 1), fig_tint=(1, 1, 1), lamp_gain=1.0):
    """Тёплая комната (линейный свет, RH x RW x 3) + эмиссия лампы. Лицо не рисуется.
    Слои по глубине: фон (стена, шторы, лампа) — мягкий; фигура — почти резко; консоль — резко."""
    rs = np.random.RandomState(seed)
    yy, xx = np.mgrid[0:RH, 0:RW].astype(np.float32)
    lw = s2l(WARM_LAMP)
    lampc = s2l(WARM_HOT)
    # --- стена: обои вертикальной полосой (рифмуется со стеклом), свет от лампы
    albedo = np.array([0.52, 0.44, 0.35], np.float32) * np.array(wall_tint, np.float32)
    stripe = 1 + 0.08 * np.sin(2 * np.pi * xx / 15.0) + 0.05 * smooth_noise((RH, RW), 1.2, seed + 1) + 0.10 * smooth_noise((RH, RW), 28, seed + 2)
    d = np.hypot(xx - RLAMP[0], (yy - RLAMP[1]) * 0.9)
    lamp_i = 1.55 * lamp_gain / (1 + (d / 95.0) ** 2) ** 1.0
    amb = np.array([0.010, 0.017, 0.019], np.float32)
    ceil = np.interp(yy[:, 0], [0, 110, 300, RH], [0.22, 0.55, 1.0, 0.85])[:, None]
    wall = s2l(albedo)[None, None, :] * (amb + lamp_i[..., None] * lw[None, None, :]) * (stripe * ceil)[..., None]
    # --- шторы слева: тёмная бирюза, глубокие складки
    cu = 240 + 6 * np.sin(yy / 160.0 + 1.0) + 7 * smooth_noise((RH, RW), 60, seed + 3)
    cm = np.clip((cu - xx) / 4.0, 0, 1)
    fold = 0.5 + 0.5 * np.sin(2 * np.pi * xx / 41.0 + 0.45 * np.sin(yy / 260.0) + 1.0 * aniso_noise((RH, RW), 160, 9, seed + 4) + 0.35 * np.sin(2 * np.pi * xx / 17.0 + 1.2 * aniso_noise((RH, RW), 120, 6, seed + 7)))
    fold_l = 0.10 + 0.90 * fold ** 1.6
    fine = 1 + 0.10 * smooth_noise((RH, RW), 1.0, seed + 5)
    curtain_alb = s2l(np.array([0.28, 0.40, 0.40], np.float32))
    ci = 0.05 + 0.55 * lamp_i
    curtain = curtain_alb[None, None, :] * (amb * 3 + ci[..., None] * lw[None, None, :] * 0.8) * (fold_l * fine)[..., None]
    img = wall * (1 - cm[..., None]) + curtain * cm[..., None]
    # --- панели под рейкой
    rail = 430
    img = img * (1 - 0.55 * (yy > rail).astype(np.float32)[..., None])
    img += (np.exp(-((yy - rail) / 1.4) ** 2) * lamp_i)[..., None] * lw[None, None, :] * 0.30
    # --- лампа (на фоне, мягкая): абажур с тканью
    shade_pts = [(RLAMP[0] - 16, RLAMP[1] - 38), (RLAMP[0] + 16, RLAMP[1] - 38), (RLAMP[0] + 27, RLAMP[1] + 38), (RLAMP[0] - 27, RLAMP[1] + 38)]
    sh = poly_mask(shade_pts, (RW, RH))
    gv = np.clip((yy - (RLAMP[1] - 38)) / 76.0, 0, 1)
    gu = np.abs(xx - RLAMP[0]) / 27.0
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
    cons = np.clip(yy - (RCV - 0.5), 0, 1)
    wood = s2l(np.array([0.13, 0.08, 0.055], np.float32))[None, None, :] * (0.25 + lamp_i[..., None] * 1.5) \
        * (1 + 0.18 * smooth_noise((RH, RW), 2, seed + 6) + 0.10 * np.sin(yy / 2.3))[..., None]
    wood = wood * np.interp(yy[:, 0], [RCV, RH], [1.0, 0.22])[:, None, None]
    edge_i = 0.40 + 0.60 * np.exp(-((xx - RLAMP[0]) / 300.0) ** 2)
    edge = np.exp(-((yy - (RCV + 0.6)) / 1.0) ** 2) * edge_i
    top_glint = np.exp(-((yy - (RCV - 1.6)) / 0.9) ** 2) * edge_i * 0.35      # блик на верхней грани
    # --- звонок на консоли (латунь только бликом)
    bx, br = 336.0, 17.0
    dxb, dyb = xx - bx, yy - (RCV - 0.5)
    bell_m = np.clip(br - np.hypot(dxb, dyb * 1.0), 0, 1) * (yy < RCV)
    nrm = np.clip(dxb / br, -1, 1)
    spec = np.exp(-(((xx - (bx + 6.5)) / 2.6) ** 2 + ((yy - (RCV - 12)) / 3.6) ** 2))
    bell_col = s2l(BRASS_LIGHT)[None, None, :] * (0.025 + 0.12 * np.clip(nrm, 0, 1) ** 2 + 0.55 * spec)[..., None]
    # --- фигура лауреата: контровой свет справа, без лица
    hx, hy = 376.0, 216.0
    k = 0.80
    def F(px, py):                       # масштаб фигуры вокруг (hx, hy)
        return (hx + (px - hx) * k, hy + (py - hy) * k)
    head = poly_mask(ellipse_pts(hx, hy, 34, 45, rot=-0.10), (RW, RH))
    jaw = poly_mask(ellipse_pts(hx + 2, hy + 20, 28, 34, rot=-0.08), (RW, RH))
    hair = poly_mask(ellipse_pts(hx - 2, hy - 14, 37, 34, rot=-0.10, wob_amp=0.03, seed=seed + 8), (RW, RH))
    neck = poly_mask([(hx - 17, hy + 32), (hx + 20, hy + 32), (hx + 24, hy + 78), (hx - 27, hy + 78)], (RW, RH), blur=1.0)
    # плечи: вогнутая линия трапеции от шеи, угол плеча, руки вниз (неидеально: левое плечо ниже и дальше)
    body_pts = [(hx - 20, hy + 62), (hx - 40, hy + 80), (hx - 70, hy + 91), (hx - 100, hy + 102), (hx - 118, hy + 124), (hx - 123, hy + 170), (hx - 126, 520), (hx - 126, RH),
                (hx + 124, RH), (hx + 122, 520), (hx + 117, hy + 165), (hx + 104, hy + 120), (hx + 82, hy + 98), (hx + 54, hy + 84), (hx + 36, hy + 70), (hx + 22, hy + 62)]
    body = poly_mask(body_pts, (RW, RH))
    body = np.clip(gaussian_filter(body, 4.0) * 1.9 - 0.45, 0, 1)
    strands = Image.new("L", (RW * 3, RH * 3), 0)
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
    strands = gaussian_filter(np.asarray(strands.resize((RW, RH), Image.LANCZOS), np.float32) / 255.0, 0.45)
    figure = np.clip(np.maximum.reduce([head, jaw, hair, neck, body, strands * 0.8]), 0, 1)
    figure = gaussian_filter(figure, 0.8)
    figure = np.where(yy >= RCV, 0, figure)
    from scipy.ndimage import shift as ndshift
    Ldir = np.array([RLAMP[0] - hx + 20, RLAMP[1] - hy - 6], np.float32)
    Ldir = Ldir / np.hypot(*Ldir)
    fs = gaussian_filter(figure, 1.0)
    rim = np.zeros_like(fs)
    for dist, wgt in ((2.0, 0.45), (4.0, 0.30), (7.0, 0.17), (11.0, 0.08)):   # геометрический кромочный свет: что видит лампу
        sh_ = ndshift(fs, (-Ldir[1] * dist, -Ldir[0] * dist), order=1, mode="nearest")
        rim += wgt * np.clip(fs - sh_, 0, 1)
    rim = gaussian_filter(rim, 0.8)
    rim *= np.where(yy < 262, 1.15, 1.0)
    rim *= np.interp(yy[:, 0], [0, 200, 340, 555], [1.0, 1.0, 0.75, 0.40])[:, None]
    rim = np.maximum(rim, strands * 0.30 * (np.clip(rim * 3, 0, 1)))
    # нормаль для холодного отсвета слева
    gy, gx = np.gradient(gaussian_filter(figure, 1.8))
    gn = np.hypot(gx, gy) + 1e-6
    nx = -gx / gn
    ins = distance_transform_edt(figure > 0.5)
    cool = np.clip(-nx, 0, 1) ** 1.6 * np.exp(-ins / 3.2) * 0.07
    body_col = s2l(np.array([0.048, 0.037, 0.030], np.float32))
    soft = (lamp_i / 1.55)[..., None]
    fig_col = body_col[None, None, :] * np.array(fig_tint, np.float32) * (1.4 + 7.0 * soft) + lampc[None, None, :] * (rim * 2.2)[..., None] \
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


def apply_aperture(g, interior, AX0, AY0, AW, AH, BW=19.0, lit_gain=0.95, glint=0.40):
    """Врезает окно с фаской в стекло g (линейный свет, на месте). interior — (AH,AW,3) линейный.
    Фаска по okno_direction п.3.2: преломлённое зеркально содержимое окна (сжатие 0.8), освещены верх/лево,
    тень низ/право, срез 45, дисперсия R/B +-3 px холста, внешний срез и блик только на освещённых гранях."""
    pad_m = 80
    xx0, xx1 = AX0 - pad_m, AX0 + AW + pad_m
    yy0, yy1 = max(AY0 - pad_m, 0), min(AY0 + AH + pad_m, H)
    X, Y = np.meshgrid(np.arange(xx0, xx1, dtype=np.float32) + 0.5, np.arange(yy0, yy1, dtype=np.float32) + 0.5)
    sub = g[yy0:yy1, xx0:xx1].copy()
    # прямоугольный проём, внутренняя граница без радиуса; фаска со срезом углов 45 градусов (мини-ус)
    dxl = AX0 - X; dxr = X - (AX0 + AW); dyt = AY0 - Y; dyb = Y - (AY0 + AH)
    dx = np.maximum(dxl, dxr)          # >0 снаружи по горизонтали
    dy = np.maximum(dyt, dyb)
    dd = np.maximum(dx, dy)            # Chebyshev: расстояние от внутреннего края
    inside = np.clip(0.5 - dd, 0, 1)
    ring = np.clip(dd + 0.5, 0, 1) * np.clip(BW + 0.5 - dd, 0, 1)
    horiz = dy > dx                    # грань верх/низ (диагональ ус 45)
    is_top = horiz & (dyt >= dyb)
    is_left = (~horiz) & (dxl >= dxr)
    lit_face = is_top | is_left
    t = np.clip(dd / BW, 0, 1)
    # --- интерьер, продлённый зеркально через внутреннюю кромку (сжатие 0.8) — преломлённое содержимое
    pad = np.pad(interior, ((90, 90), (90, 90), (0, 0)), mode="edge")
    def mirror_sample(shift_px):
        d_ = dd * 0.55 + shift_px
        sx = np.where(horiz, X, np.where(is_left, AX0 + d_, AX0 + AW - d_))
        sy = np.where(horiz, np.where(is_top, AY0 + d_, AY0 + AH - d_), Y)
        return sample_xy(pad, sx - AX0 + 90, sy - AY0 + 90)
    refr = np.empty_like(sub)
    for c, k_ in enumerate((-1.5, 0.0, 1.5)):               # дисперсия R/B +-3 px холста только в полосе фаски
        refr[..., c] = mirror_sample(k_)[..., c]
    # --- грани: освещены верх и лево (×(1+0.55) пик на 30 % ширины, тепло 22 %), тень низ и право (×0.45 → ×0.30)
    bump = np.exp(-((t - 0.30) / 0.28) ** 2)
    mul_lit = 1 + lit_gain * bump
    mul_shadow = 0.45 + (0.30 - 0.45) * t
    mul = np.where(lit_face, mul_lit, mul_shadow)
    col = refr * mul[..., None]
    warm = s2l(hexrgb("#F0D6A0"))
    lum_c = col.mean(axis=2, keepdims=True) / warm.mean()
    col = np.where(lit_face[..., None], col * (1 - 0.22) + 0.22 * warm[None, None, :] * lum_c * 1.6, col)
    # собственная плотность стекла: немного окружающего стекла просвечивает сквозь фаску (иначе выглядит дырой)
    outer_ref = np.empty_like(sub)
    for c, k_ in enumerate((0.7, 1.0, 1.4)):
        sh_ = 18 * (1 - t) * k_
        sx = X - xx0 + np.where(horiz, 0, np.where(is_left, -sh_, sh_))
        sy = Y - yy0 + np.where(horiz, np.where(is_top, -sh_, sh_), 0)
        outer_ref[..., c] = sample_xy(sub[..., c:c + 1], sx, sy)[..., 0]
    col = col * 0.80 + outer_ref * (0.20 * np.where(lit_face, 1.0, 0.55))[..., None]
    # отражение холодной стены в наклонной грани (стекло, а не латунь): на освещённых гранях градиент внутрь->наружу
    cool = s2l(np.array([0.50, 0.72, 0.74], np.float32))
    col = col + (np.where(lit_face, 0.22 * (1 - t) ** 1.5 * (0.6 + 0.4 * t), 0.05 * (1 - t)))[..., None] * cool[None, None, :]
    # тонкая яркая линия на внутренней кромке (каустика): у теневых граней холодная, у освещённых тёплая
    inner = np.exp(-((dd - 1.2) / 0.9) ** 2)
    col = col + (inner * np.where(lit_face, 0.50, 0.18))[..., None] * np.where(lit_face[..., None], s2l(hexrgb('#F0D6A0'))[None, None, :], cool[None, None, :])
    # неравномерность полировки: яркость грани гуляет вдоль кромки
    col = col * (1 + 0.16 * np.sin(np.where(horiz, X, Y) / 53.0 + 1.3) * np.sin(np.where(horiz, X, Y) / 17.0))[..., None]
    # внешний срез: линия 2 px мастера #F0D6A0 50 % только на освещённых гранях
    cut = np.exp(-((dd - (BW - 1.0)) / 0.9) ** 2) * lit_face * 0.50
    col += cut[..., None] * warm[None, None, :] * 0.85
    # блик на верхней грани: длина ~5 wb, толщина 0.6 wb, начало в 3 wb от левого угла, +40 % #F0D6A0
    xl = (X - AX0)
    hl_x = np.exp(-(((xl - (3 * BW + 2.5 * BW)) / (2.5 * BW)) ** 2))
    hl_y = np.exp(-(((dd - 0.36 * BW) / (0.30 * BW)) ** 2))
    glint = hl_x * hl_y * is_top * glint
    col += glint[..., None] * warm[None, None, :] * 1.0
    out = sub * (1 - ring[..., None]) + col * ring[..., None]
    out = out * (1 - inside[..., None])
    ii = np.zeros_like(sub)
    ii[AY0 - yy0:AY0 - yy0 + AH, AX0 - xx0:AX0 - xx0 + AW] = interior
    out = out + ii * inside[..., None]
    g[yy0:yy1, xx0:xx1] = out
    return g


# ============================================================================
# окно мира для K2: ключница отеля (латунные бирки на крючках), лампа-бра, сухая резкая картинка
# ============================================================================
SCONCE = (330.0, 56.0)     # бра в локальных координатах окна (30 % x, верх панели)


def build_keyrack(seed=7, gain=1.0):
    """Ключница за стойкой: ореховая панель, 3 ряда латунных крючков, бирки без текста, ключи.
    Линейный свет (AH,AW,3). Освещение — одно бра слева сверху; всё резко (плоскость стойки)."""
    rs = np.random.RandomState(seed)
    yy, xx = np.mgrid[0:AH, 0:AW].astype(np.float32)
    lw = s2l(WARM_LAMP)
    d = np.hypot((xx - SCONCE[0]) * 0.8, yy - SCONCE[1])
    I = gain * 2.4 / (1 + (d / 190.0) ** 2) + 0.02
    I *= 0.85 + 0.15 * np.clip(1 - np.abs(xx / AW - 0.5) * 1.2, 0, 1)
    # --- ореховая панель: вертикальные доски, волокно, швы
    alb = s2l(np.array([0.64, 0.58, 0.49], np.float32))          # известковая панель (limewash): нейтральная светлая, тёплое остаётся латуни
    grain = 1 + 0.035 * smooth_noise((AH, AW), 1.0, seed + 1) + 0.05 * aniso_noise((AH, AW), 14, 4.0, seed + 2) + 0.13 * smooth_noise((AH, AW), 26, seed + 9) + 0.07 * smooth_noise((AH, AW), 90, seed + 8)
    plank = np.floor(xx / 183.0)
    ptone = (1 + 0.10 * np.sin(plank * 7.3 + 1.0))
    seam = 1 - 0.75 * np.exp(-(((xx % 183.0) - 0.0) / 1.3) ** 2) - 0.0 * xx
    seam *= 1 - 0.75 * np.exp(-(((xx % 183.0) - 183.0) / 1.3) ** 2)
    img = alb[None, None, :] * (I * grain * ptone * seam)[..., None]
    # --- карниз панели: латунная рейка стойки внизу (резко) и тёмный верх
    ry = 600
    shelf = np.clip(yy - ry, 0, 1)
    wood2 = alb[None, None, :] * (I * 0.35 * (1 + 0.2 * aniso_noise((AH, AW), 1, 40, seed + 3)))[..., None]
    img = img * (1 - shelf[..., None]) + wood2 * shelf[..., None]
    rail = np.exp(-((yy - (ry + 1.2)) / 1.2) ** 2) * (0.35 + 0.65 * np.exp(-((xx - SCONCE[0]) / 380.0) ** 2))
    img += rail[..., None] * s2l(BRASS_LIGHT)[None, None, :] * 0.85 * gain
    img += (np.exp(-((yy - (ry - 1.4)) / 1.0) ** 2) * 0.25 * np.exp(-((xx - SCONCE[0]) / 380.0) ** 2))[..., None] * lw[None, None, :]
    # --- тень под рейкой и общий спад к краям (стена живая, не плоская)
    img *= (1 - 0.45 * np.clip((np.abs(xx / AW - 0.5) - 0.30) / 0.2, 0, 1))[..., None]

    brass = s2l(BRASS_LIGHT)
    shadow_acc = np.zeros((AH, AW), np.float32)
    layers = []
    ss = 3
    pw, ph = 76, 160
    sc = 1.22
    rows = [122, 278, 434]
    cols = np.arange(60, AW - 80, 104)
    empty = {(0, 3), (1, 8), (2, 5), (0, 10), (2, 9), (1, 2), (0, 6)}
    for j, hy in enumerate(rows):
        for i, hx in enumerate(cols):
            hxx = hx + (42 if j == 1 else 0) + rs.randn() * 4.0
            hook_cx, hook_cy = hxx, hy + rs.randn() * 1.0
            if (j, i) in empty:
                layers.append(("hook", hook_cx, hook_cy, 1.0))
                continue
            ang = rs.randn() * 2.2
            big = Image.new("L", (pw * ss, ph * ss), 0)
            dr = ImageDraw.Draw(big)
            cxp = pw / 2
            dr.ellipse([(cxp - 8) * ss, 0, (cxp + 8) * ss, 16 * ss], outline=255, width=2 * ss)         # кольцо
            tw_ = 19 + 5 * rs.rand(); th_ = 88 - 14 * (rs.rand() < 0.35)
            if rs.rand() < 0.3:
                dr.ellipse([(cxp - tw_) * ss, 20 * ss, (cxp + tw_) * ss, (20 + 2 * tw_ + 10) * ss], fill=255)       # круглая бирка
                th_ = 2 * tw_ + 30
            else:
                dr.rounded_rectangle([(cxp - tw_) * ss, 18 * ss, (cxp + tw_) * ss, th_ * ss], radius=7 * ss, fill=255)   # бирка
            dr.ellipse([(cxp - 4) * ss, 25 * ss, (cxp + 4) * ss, 33 * ss], fill=0)                     # отверстие
            dr.rectangle([(cxp - 3) * ss, (th_ - 2) * ss, (cxp + 3) * ss, (th_ + 40) * ss], fill=255)                # ключ
            dr.rectangle([(cxp + 3) * ss, (th_ + 16) * ss, (cxp + 15) * ss, (th_ + 42) * ss], fill=255)
            dr.rectangle([(cxp + 8) * ss, (th_ + 22) * ss, (cxp + 16) * ss, (th_ + 27) * ss], fill=0)
            dr.rectangle([(cxp + 8) * ss, (th_ + 33) * ss, (cxp + 16) * ss, (th_ + 37) * ss], fill=0)
            big = big.rotate(-ang, resample=Image.BICUBIC, center=(cxp * ss, 8 * ss))
            cov = np.asarray(big.resize((int(pw * sc), int(ph * sc)), Image.LANCZOS), np.float32) / 255.0
            cb = gaussian_filter(cov, 1.0)
            gy, gx = np.gradient(cb)
            cxw, cyw = hook_cx, hook_cy + 55
            Ld = np.array([SCONCE[0] - cxw, SCONCE[1] - cyw], np.float32); Ld /= np.hypot(*Ld)
            lit = np.clip(-(gx * -Ld[0] * -1 + gy * -Ld[1] * -1) * 0 + (gx * Ld[0] + gy * Ld[1]) * -2.4, 0, 1)
            ly = np.arange(cov.shape[0], dtype=np.float32)[:, None]
            face = (0.50 + 0.12 * np.sin(ly / 22.0) - 0.15 * ly / cov.shape[0]) * np.ones((1, cov.shape[1]), np.float32)
            Il = float(gain * 2.4 / (1 + (np.hypot((cxw - SCONCE[0]) * 0.8, cyw - SCONCE[1]) / 190.0) ** 2) + 0.02)
            var = 0.88 + 0.24 * rs.rand()
            sh = (face * 0.20 + 1.15 * lit) * Il * var
            col = brass[None, None, :] * sh[..., None]
            layers.append(("tag", hook_cx - pw * sc / 2, hook_cy - 8 * sc, cov, col))
    # тени на панели
    for L in layers:
        if L[0] != "tag":
            continue
        _, x0, y0, cov, col = L
        x0i, y0i = int(round(x0)), int(round(y0))
        sh = np.zeros((AH, AW), np.float32)
        sy0, sx0 = max(y0i + 7, 0), max(x0i + 5, 0)
        ch = min(cov.shape[0], AH - sy0); cw = min(cov.shape[1], AW - sx0)
        if ch > 0 and cw > 0:
            shadow_acc[sy0:sy0 + ch, sx0:sx0 + cw] = np.maximum(shadow_acc[sy0:sy0 + ch, sx0:sx0 + cw], cov[:ch, :cw])
    shadow = gaussian_filter(shadow_acc, 4.0)
    img *= (1 - 0.62 * shadow)[..., None]
    for L in layers:
        if L[0] == "tag":
            _, x0, y0, cov, col = L
            x0i, y0i = int(round(x0)), int(round(y0))
            ys, xs_ = slice(max(y0i, 0), min(y0i + cov.shape[0], AH)), slice(max(x0i, 0), min(x0i + cov.shape[1], AW))
            cy0, cx0 = ys.start - y0i, xs_.start - x0i
            c = cov[cy0:cy0 + (ys.stop - ys.start), cx0:cx0 + (xs_.stop - xs_.start)]
            k = col[cy0:cy0 + c.shape[0], cx0:cx0 + c.shape[1]]
            img[ys, xs_] = img[ys, xs_] * (1 - c[..., None]) + k * c[..., None]
    # крючки (латунные чашки со бликом) поверх колец
    for L in layers:
        hx_, hy_ = (L[1] + 0, L[2] + 8 * sc) if L[0] == "tag" else (L[1], L[2])
        if L[0] == "tag":
            hx_ = L[1] + 38 * sc
        m = np.clip(5.5 - np.hypot(xx - hx_, yy - hy_), 0, 1)
        Il = gain * 2.4 / (1 + (np.hypot((hx_ - SCONCE[0]) * 0.8, hy_ - SCONCE[1]) / 190.0) ** 2) + 0.02
        spec = np.exp(-(((xx - (hx_ - 1.8)) / 1.5) ** 2 + ((yy - (hy_ - 2.0)) / 1.5) ** 2))
        hc = brass[None, None, :] * ((0.09 + 0.75 * spec) * Il)[..., None]
        img = img * (1 - m[..., None]) + hc * m[..., None]
    # --- бра: латунная чашка и единственная резкая лампа-точка (бусина)
    sx_, sy_ = SCONCE
    plate = np.clip(14 - np.maximum(np.abs(xx - sx_) - 0.0, np.abs(yy - (sy_ + 18)) * 1.3), 0, 1) * 0
    cup = np.clip(18 - np.hypot(xx - sx_, (yy - (sy_ + 10)) * 1.15), 0, 1) * (yy > sy_ + 4)
    cup_sh = (0.10 + 0.45 * np.exp(-((xx - (sx_ - 6)) / 5.0) ** 2) + 0.22 * np.clip((yy - sy_) / 24, 0, 1))
    img = img * (1 - cup[..., None]) + brass[None, None, :] * (cup_sh * 1.1)[..., None] * cup[..., None]
    bead = np.clip(6.2 - np.hypot(xx - sx_, yy - (sy_ - 1)), 0, 1)
    img = img * (1 - bead[..., None]) + s2l(hexrgb("#F0D6A0"))[None, None, :] * 3.2 * bead[..., None]
    # рассеяние вокруг чашки на панели (стена подсвечена вверх и вниз), без свечения вокруг самой бусины
    img = gaussian_filter(img, (0.45, 0.45, 0))
    return img.astype(np.float32)


# ============================================================================
# круглая «полированная» вставка (рождение окна)
# ============================================================================
def apply_disc(g, content_fn, cx, cy, r, bw=9.0):
    """Круг Ø2r, очищенный в стекле; край — фаска (то же правило, что у проёма): свет верх-лево."""
    pad = 60
    x0, x1 = int(cx - r - pad), int(cx + r + pad)
    y0, y1 = int(cy - r - pad), int(cy + r + pad)
    X, Y = np.meshgrid(np.arange(x0, x1, dtype=np.float32) + 0.5, np.arange(y0, y1, dtype=np.float32) + 0.5)
    sub = g[y0:y1, x0:x1].copy()
    dx, dy = X - cx, Y - cy
    rr = np.hypot(dx, dy) + 1e-6
    d = rr - r
    nx, ny = dx / rr, dy / rr
    Ld = np.array([-0.62, -0.78], np.float32)
    facing = nx * Ld[0] + ny * Ld[1]
    lit = np.clip((facing + 0.15) / 0.55, 0, 1)
    lit = lit * lit * (3 - 2 * lit)
    inside = np.clip(0.5 - d, 0, 1)
    ring = np.clip(d + 0.5, 0, 1) * np.clip(bw + 0.5 - d, 0, 1)
    t = np.clip(d / bw, 0, 1)
    def mir(shift):
        rin = np.maximum(r - (d * 0.8 + shift), 0)
        return content_fn(cx + nx * rin, cy + ny * rin)
    refr = np.empty_like(sub)
    for c, k_ in enumerate((-1.2, 0.0, 1.2)):
        refr[..., c] = mir(k_)[..., c]
    bump = np.exp(-((t - 0.30) / 0.28) ** 2)
    mul = lit * (1 + 0.55 * bump) + (1 - lit) * (0.45 + (0.30 - 0.45) * t)
    col = refr * mul[..., None]
    warm = s2l(hexrgb("#F0D6A0"))
    lum_c = col.mean(axis=2, keepdims=True) / warm.mean()
    col = col * (1 - 0.22 * lit[..., None]) + 0.22 * lit[..., None] * warm[None, None, :] * lum_c * 1.6
    outer = np.empty_like(sub)
    for c, k_ in enumerate((0.7, 1.0, 1.4)):
        sh_ = 14 * (1 - t) * k_
        outer[..., c] = sample_xy(sub[..., c:c + 1], X - x0 - nx * sh_, Y - y0 - ny * sh_)[..., 0]
    col = col * 0.80 + outer * (0.20 * (0.55 + 0.45 * lit))[..., None]
    cut = np.exp(-((d - (bw - 1.0)) / 0.9) ** 2) * lit * 0.50
    col += cut[..., None] * warm[None, None, :] * 0.85
    ang = np.arctan2(dy, dx)
    gl = np.exp(-(((ang - np.arctan2(Ld[1], Ld[0]) - 0.35) / 0.42) ** 2)) * np.exp(-(((d - 0.36 * bw) / (0.30 * bw)) ** 2)) * 0.40
    col += gl[..., None] * warm[None, None, :]
    out = sub * (1 - ring[..., None]) + col * ring[..., None]
    cont = content_fn(X, Y)
    out = out * (1 - inside[..., None]) + cont * inside[..., None]
    g[y0:y1, x0:x1] = out
    return g


def thread_line(g, geo, x_a, x_b, y_c, peak=1.0, fade_dir=1):
    """Нить света: тело #C9A961 (8 px холста = 4 мастера), ядро #F0D6A0 (1,5 px мастера); без ореола.
    Живёт в рифлёном стекле: яркость модулируется рёбрами. fade_dir=+1 — ярче к x_b."""
    xs = np.arange(int(x_a), int(x_b), dtype=np.float32)
    yy2 = np.arange(H, dtype=np.float32)[:, None]
    rl = 0.45 + 0.55 * np.clip(0.55 * geo["hl"][xs.astype(int)] + 0.55 * (np.cos(2 * np.pi * geo["t"][xs.astype(int)]) ** 2), 0, 1.3)
    u = (xs - x_a) / max(x_b - x_a, 1)
    ramp = (u if fade_dir > 0 else 1 - u)
    fall = 0.18 + 0.82 * ramp ** 1.3
    endcap = np.clip(xs - x_a, 0, 6) / 6.0 * np.clip(x_b - xs, 0, 6) / 6.0
    amp = (rl * fall * endcap * peak)[None, :]
    body = np.exp(-((yy2 - y_c) / 2.0) ** 4)
    core = np.exp(-((yy2 - y_c) / 0.8) ** 2)
    k_body = s2l(hexrgb("#C9A961")) * 0.55
    k_core = s2l(hexrgb("#F0D6A0")) * 0.85
    sl = slice(int(x_a), int(x_b))
    g[:, sl] += (body * amp)[..., None] * k_body[None, None, :] + (core * amp)[..., None] * k_core[None, None, :]
    return g


# ============================================================================
# K2
# ============================================================================
def render_k2(seed):
    yy_, xx_ = np.mgrid[0:H, 0:W].astype(np.float32)
    # след окна (окно едет вправо): слева за рамкой стекло слабее
    trail = (1 - np.clip((AX0 - xx_) / 380.0, 0, 1)) * (xx_ < AX0) * (xx_ > AX0 - 400)
    vy = np.clip(np.clip(1 - np.abs(yy_ - (AY0 + AH / 2)) / (0.40 * AH), 0, 1) * 4, 0, 1)
    fade = (1 - 0.42 * trail * vy).astype(np.float32)
    g, geo, pack = glass_base(seed, fade=fade)
    rack = build_keyrack(gain=P_K2["rack_gain"])
    g = apply_aperture(g, rack, AX0, AY0, AW, AH, BW=BW)
    # рождение следующего окна: полированный круг вокруг огня сектора 5 (x ~ станция 65 %)
    sector5 = [(k, r) for k, r, s in sector_slots() if s == 4]
    k, r = max(sector5, key=lambda kr: win_center(*kr)[0])
    ccx, ccy = win_center(k, r)
    sc_ = 6
    hi = lit_window_template(sc_)
    # огонь, ставший окном: то же окно (лампа, штора, переплёт), «подошли ближе» x1.75; вокруг него стена фасада
    hw, hh = hi.shape[1], hi.shape[0]
    wallc = np.array([0.10, 0.17, 0.17], np.float32)
    padh = np.concatenate([np.broadcast_to(wallc, (hh, 90, 3)), hi, np.broadcast_to(wallc, (hh, 90, 3))], 1)
    padh = np.concatenate([np.broadcast_to(wallc, (90, padh.shape[1], 3)), padh, np.broadcast_to(wallc, (90, padh.shape[1], 3))], 0)
    zoom = 1.8
    def content(X, Y):
        tx = (hw / 2 + 90) + (X - ccx) / zoom * sc_
        ty = (hh / 2 + 90) + (Y - ccy) / zoom * sc_
        return s2l(sample_xy(padh, tx, ty)) * P_K2["disc_gain"]
    g = apply_disc(g, content, ccx, ccy, 50.0, bw=9.0)
    # нить света под нижней фаской окна, от левого экрана через стык
    g = thread_line(g, geo, 70, AX0 + AW - 20, AY0 + AH + BW * 0.5, fade_dir=1)
    return finish(g, seed + 10)


P_K2 = dict(rack_gain=0.62, disc_gain=1.0)
# ============================================================================
# K3: стекло снято, бархат, 35 створок 9:16 с фасками
# ============================================================================
SEC_C = [192, 499, 730, 960, 1190, 1421, 1728]          # центры секторов, превью (direction п.4)
SEC_DY = [0, -14, 10, -6, 14, -10, 6]
SEC_DX = [0, 4, -5, 0, 5, -4, 0]
TW, TH = 120, 214                                         # створка 9:16 в мастере (240x427 холста)
BW3 = 6.5                                                 # фаска створки: 13 px холста
P_K3 = dict(wall_gain=1.30, spill=0.50, content_gain=4.6, desat=0.40, grain=1.4)
ROOM_VARIANTS = [
    dict(wall_tint=(1.00, 1.00, 1.00), fig_tint=(5.5, 5.0, 4.2), lamp_gain=1.00),
    dict(wall_tint=(0.86, 0.96, 1.06), fig_tint=(2.6, 4.4, 5.8), lamp_gain=0.92),
    dict(wall_tint=(1.12, 0.92, 0.80), fig_tint=(7.0, 3.4, 2.2), lamp_gain=1.05),
    dict(wall_tint=(0.94, 1.06, 0.92), fig_tint=(3.4, 5.6, 3.6), lamp_gain=0.98),
    dict(wall_tint=(1.05, 0.88, 0.94), fig_tint=(6.2, 2.8, 3.8), lamp_gain=1.08),
]


def tile_positions():
    """35 центров створок (мастер): (x0, y0, сектор). 3 внизу (шаг 132), 2 вверху (между ними), сдвиги по таблице."""
    out = []
    for s, c in enumerate(SEC_C):
        cx = 2 * (c + SEC_DX[s]); dy = 2 * SEC_DY[s]
        for i, off in enumerate((-132, 0, 132)):
            out.append((cx + off - TW / 2, 344 + dy + (0, 10, 0)[i], s))
        for i, off in enumerate((-66, 66)):
            out.append((cx + off - TW / 2, 96 + dy + (0, -12)[i], s))
    return out


def build_velvet(seed=21):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    yv = np.interp(yy[:, 0] / H, [0, 0.12, 0.22, 0.40, 0.60, 0.74, 1.0], [0.20, 0.42, 0.85, 1.0, 0.72, 0.30, 0.15])
    xv = 0.80 + 0.20 * np.clip(np.cos((xx[0] / W - 0.5) * np.pi * 1.1), 0, 1)
    L = yv[:, None] * xv[None, :]
    # драпировка: вертикальные складки неровного периода
    ph = 2 * np.pi * xx / 330.0 + 1.6 * aniso_noise((H, W), 260, 90, seed) + 0.35 * np.sin(yy / 380.0)
    fold = 0.5 + 0.5 * np.sin(ph)
    L = L * (0.70 + 0.45 * fold ** 1.2)
    # ворс: вертикальное волокно, неровность ворса пятнами
    fib = 1 + 0.05 * smooth_noise((H, W), 1.1, seed + 1) + 0.035 * aniso_noise((H, W), 9, 2.2, seed + 2)
    nap = 1 + 0.10 * smooth_noise((H, W), 55, seed + 3)
    L = L * fib * nap * P_K3["wall_gain"]
    dark, lit = hexrgb("#00151C") * 0 + hexrgb("#002935"), hexrgb("#0F5A6B")
    t = np.clip(L, 0, 1.35)[..., None]
    col = dark[None, None, :] * 0.5 + (lit - dark * 0.5)[None, None, :] * np.clip(t, 0, 1.3) ** 1.15
    return s2l(np.clip(col, 0, 0.62)).astype(np.float32), L


def render_k3(seed):
    wall, L = build_velvet()
    rooms = [build_room(5 + i, **v)[0] for i, v in enumerate(ROOM_VARIANTS)]
    tiles = tile_positions()
    order = np.random.RandomState(seed).permutation(35)
    spill_map = np.zeros((H, W, 3), np.float32)
    g = wall.copy()
    contents = []
    for n, (x0, y0, s) in enumerate(tiles):
        rm = rooms[order[n] % 5]
        crop = Image.fromarray(np.ascontiguousarray(rm[:, 148:500, :]), mode=None) if False else None
        # ресайз в линейном свете по каналам
        rj = np.random.RandomState(100 + n)
        z = 0.86 + 0.14 * rj.rand()
        cw_, ch_ = 352 * z, 625 * z
        cxm = 324 + rj.uniform(-24, 24)
        bx0 = float(np.clip(cxm - cw_ / 2, 0, 500 - cw_)); by0 = float(rj.uniform(0, 625 - ch_))
        gx, gy = np.meshgrid(bx0 + (np.arange(TW) + 0.5) * cw_ / TW, by0 + (np.arange(TH) + 0.5) * ch_ / TH)
        tile = sample_xy(rm, gx, gy).astype(np.float32)
        tl = tile.mean(axis=2, keepdims=True)
        tile = (tile * (1 - P_K3["desat"]) + tl * P_K3["desat"]) * P_K3["content_gain"]
        tile = np.power(np.clip(tile, 0, None), 1.18) * 1.3
        tile = tile / (1 + 0.90 * tile)       # плечо: лампа не уходит в белое пятно
        yy, xx = np.mgrid[0:TH, 0:TW].astype(np.float32)
        lamp_loc = ((432.0 - bx0) * TW / cw_, (218.0 - by0) * TH / ch_)
        bead = np.clip(3.4 - np.hypot(xx - lamp_loc[0], yy - lamp_loc[1]), 0, 1)
        tile = tile * (1 - bead[..., None]) + s2l(hexrgb("#F0D6A0"))[None, None, :] * 3.2 * bead[..., None]
        contents.append((x0, y0, tile))
        xi, yi = int(round(x0)), int(round(y0))
        spill_map[yi:yi + TH, xi:xi + TW] += tile
    spill = gaussian_filter(spill_map, (43, 43, 0))
    tint = spill / (spill.mean(axis=2, keepdims=True) + 1e-6)
    g = g + spill * P_K3["spill"] * (L[..., None] ** 0.3) * 1.0
    for (x0, y0, tile) in contents:
        g = apply_aperture(g, tile, int(round(x0)), int(round(y0)), TW, TH, BW=BW3, lit_gain=0.40, glint=0.25)
    return finish(g, seed + 12, grain=P_K3["grain"])


# ============================================================================
# замеры, лист
# ============================================================================
def luma(a):
    a = a.astype(np.float32)
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def tone_stats(arr):
    Y = luma(arr)
    n = Y.size
    r = dict(dark=100 * (Y < 40).mean(), mid=100 * ((Y >= 40) & (Y < 150)).mean(),
             light=100 * ((Y >= 150) & (Y <= 235)).mean(), peak=100 * (Y > 235).mean(),
             warm=100 * ((arr[..., 0].astype(int) - arr[..., 2].astype(int)) >= 40).mean(),
             min_code=float(np.percentile(Y, 0.1)), max_code=int(arr.max()), mean=float(Y.mean()))
    return r


def top_mask(arr, frac=0.005):
    Y = luma(arr)
    th = np.quantile(Y, 1 - frac)
    return Y >= th, th


def frame_checks(name, arr):
    out = {}
    m, th = top_mask(arr)
    out["top_threshold"] = float(th)
    if name == "k1":
        world, emis, emi = build_facade()
        zone = gaussian_filter(emis, 14) > 0.04
        kx = np.zeros_like(zone); kx[250:312, 1200:1300] = True
        out["top05_in_fires_or_key"] = float((m & (zone | kx)).sum() / m.sum() * 100)
        out["key_tip_code"] = int(luma(arr[285:312, 1225:1275]).max())
        out["fire_core_codes"] = [float(np.percentile(luma(arr)[zone], 99.0))]
    if name == "k2":
        bevel = np.zeros(m.shape, bool)
        bevel[AY0 - 24:AY0 + int(BW) + 6, AX0 - 24:AX0 + AW + 24] = True
        bevel[AY0 - 24:AY0 + AH + 24, AX0 - 24:AX0 + int(BW) + 6] = True
        bevel[AY0 + AH - 12:AY0 + AH + 28, AX0 - 24:AX0 + AW + 24] = True
        bevel[AY0:AY0 + 140, 300 + 328 - 40:300 + 328 + 40] = True      # бра
        bevel[170:280, 2370:2510] = True                                     # круг
        out["top05_on_bevel_bead_disc_sconce"] = float((m & bevel).sum() / m.sum() * 100)
        Yl = luma(arr)
        inner = Yl[AY0 + 30:AY0 + AH - 30, AX0 + 30:AX0 + AW - 30].mean()
        mask = np.ones(Yl.shape, bool); mask[AY0 - 40:AY0 + AH + 40, AX0 - 40:AX0 + AW + 40] = False
        outer = Yl[mask & (np.arange(Yl.shape[0])[:, None] > 10)].mean()
        out["window_mean"] = float(inner); out["glass_mean"] = float(outer); out["ratio"] = float(inner / outer)
    if name == "k3":
        shares = [0] * 7
        ys, xs = np.nonzero(m)
        centers = [2 * (c + dx) for c, dx in zip(SEC_C, SEC_DX)]
        idx = np.argmin(np.abs(xs[:, None] - np.array(centers)[None, :]), axis=1)
        for i in range(7):
            shares[i] = float((idx == i).sum() / len(xs) * 100)
        out["top05_share_by_sector"] = [round(v, 1) for v in shares]
    return out


def make_sheet(outdir):
    fr = [("k1_glass", "K1 · всё в стекле"), ("k2_window", "K2 · окно едет через стык"), ("k3_clear", "K3 · стекло снято")]
    F = ImageFont.truetype(FONT_BODY, 17)
    Fb = ImageFont.truetype(FONT_NAME, 21)
    M = 40
    SW = 1920 + 2 * M
    rows = []
    sheet_h = 2 * M + len(fr) * 640
    sh = Image.new("RGB", (SW, sheet_h), (14, 20, 22))
    d = ImageDraw.Draw(sh)
    y = M
    for fn, label in fr:
        im = Image.open(os.path.join(outdir, fn + ".png")).convert("RGB")
        pv = im.resize((1920, 384), Image.LANCZOS)
        d.text((M, y), label + "   (предпросмотр 1920x384; рамка и ось стыков — только на листе)", font=F, fill=(190, 196, 190))
        y += 28
        sh.paste(pv, (M, y))
        for sx in (384, 1536):
            for yy_ in range(0, 384, 12):
                d.line([(M + sx, y + yy_), (M + sx, y + yy_ + 5)], fill=(120, 130, 130), width=1)
        y += 384 + 8
        gr = pv.convert("L").resize((960, 192), Image.LANCZOS)
        sh.paste(gr.convert("RGB"), (M, y))
        s8 = im.resize((240, 48), Image.LANCZOS)
        sh.paste(s8, (M + 960 + 30, y))
        s16 = im.resize((120, 24), Image.LANCZOS)
        sh.paste(s16, (M + 960 + 30, y + 58))
        d.text((M + 960 + 30 + 260, y + 4), "серый 1/2 слева · цвет 1/16 (240x48) и 1/32 (120x24)", font=F, fill=(150, 158, 152))
        y += 192 + 16
    sh = sh.crop((0, 0, SW, y + M // 2))
    sh.save(os.path.join(outdir, "_sheet.png"))


# ============================================================================




# ============================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=["k1", "k2", "k3", "sheet", "stats"])
    ap.add_argument("--out", default=HERE)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    seed = P["seed"]
    names = dict(k1="k1_glass", k2="k2_window", k3="k3_clear")
    fn = dict(k1=render_k1, k2=render_k2, k3=render_k3)
    for k in ("k1", "k2", "k3"):
        if k in a.only:
            save_pair(fn[k](seed), a.out, names[k])
            print(k, "ok", flush=True)
    if "sheet" in a.only:
        make_sheet(a.out)
        print("sheet ok")
    if "stats" in a.only:
        res = {}
        for k in ("k1", "k2", "k3"):
            arr = np.asarray(Image.open(os.path.join(a.out, names[k] + ".png")).convert("RGB"))
            res[k] = dict(tone=tone_stats(arr), checks=frame_checks(k, arr))
        with open(os.path.join(a.out, "tone_stats.json"), "w") as f:
            json.dump(res, f, indent=1, ensure_ascii=False)
        print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
