#!/usr/bin/env python3
"""Стайлфреймы направления B «Барельеф. Свет идёт вдоль» — G8 awards demo.

Экран 15000x3500 (screens/g8_panorama_draft.yaml, ЧЕРНОВИК). Рабочий масштаб 1/4 = 3750x875,
превью 1/8, лист 1/16. Все координаты в коде — в ПИКСЕЛЯХ ЭКРАНА (15000x3500), в масштаб
переводит q(). Кадры не рисуются «картинкой»: строится поле высот (барельеф, V-врез имён),
альбедо, затем одна точечная лампа освещает его с жёсткой тенью (heightfield shadow march).
Лампа = данные (ax, ay, d, угол, радиус) -> та же схема годится для relight на сборке.

Запуск:  python3 make_g8_frames.py            (все кадры + лист + frames_spec.json)
         python3 make_g8_frames.py b5_award   (один кадр)
Шрифт: Liberation Sans Bold (плейсхолдер-нейтраль, НЕ выбор студии), см. README.md.
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
SCALE = 4                       # 1/4
W, H = 15000 // SCALE, 3500 // SCALE
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
SEAMS = (3750, 7500, 11250)     # условные стыки (допущение профиля)
rng = np.random.default_rng(80)


def q(v):
    return v / SCALE


# --- палитра (directions.md, Направление B) ---------------------------------
def srgb2lin(c):
    c = np.asarray(c, np.float32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def hexlin(h):
    h = h.lstrip("#")
    return srgb2lin(np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255)


C_LAMP = hexlin("#EEF3F8")      # цвет света
C_UMBRA = hexlin("#3A2A22")     # цвет тени (тёплый отражённый свет)
C_PLASTER = hexlin("#DCD5C6")   # гипс на свету (альбедо ~ этому / 0.9)
C_CINN = hexlin("#C8301E")      # киноварь
AMB_TINT = 0.55 * (C_UMBRA / C_UMBRA.max()) + 0.45
LAMP_TINT = C_LAMP / C_LAMP.max()

# --- шрифт ---------------------------------------------------------------------
_f1000 = ImageFont.truetype(FONT, 1000)
_b = _f1000.getbbox("H")
CAP_RATIO = (_b[3] - _b[1]) / 1000.0     # высота заглавной / кегль


def font_for_cap(cap_px, path=FONT):
    return ImageFont.truetype(path, max(4, int(round(cap_px / CAP_RATIO))))


def text_width(txt, cap_screen):
    """ширина строки в пикселях ЭКРАНА при заданной высоте заглавной"""
    return _f1000.getlength(txt) * (cap_screen / CAP_RATIO) / 1000.0


# --- примитивы профилей ----------------------------------------------------------
def prof_round(mask_hi, hgt, r, ss=2):
    """скруглённый профиль (четверть окружности) по маске; ss — сверхсэмпл маски"""
    dt = ndi.distance_transform_edt(mask_hi) / ss
    p = hgt * np.sqrt(np.clip(1 - (1 - np.clip(dt / r, 0, 1)) ** 2, 0, 1))
    return p


def prof_vgroove(mask_hi, slope, max_depth, ss=2):
    dt = ndi.distance_transform_edt(mask_hi) / ss
    return -np.minimum(dt * slope, max_depth), dt


def down(a, ss=2):
    h, w = a.shape
    return a[:h // ss * ss, :w // ss * ss].reshape(h // ss, ss, w // ss, ss).mean((1, 3))


class Local:
    """локальный холст (в пикселях 1/4) для сборки предмета"""

    def __init__(self, w, h, ss=2):
        self.w, self.h, self.ss = w, h, ss
        self.H = np.zeros((h, w), np.float32)

    def mask(self, fn):
        im = Image.new("L", (self.w * self.ss, self.h * self.ss), 0)
        fn(ImageDraw.Draw(im), self.ss)
        return np.asarray(im) > 127

    def add(self, fn, hgt, r):
        """поднять: hgt (px 1/4) со скруглением r"""
        m = self.mask(fn)
        if not m.any():
            return
        self.H += down(prof_round(m, hgt, r * 1.7, self.ss), self.ss).astype(np.float32)

    def cut(self, fn, depth, slope=1.2):
        m = self.mask(fn)
        if not m.any():
            return
        p, _ = prof_vgroove(m, slope, depth, self.ss)
        self.H += down(np.where(m, p, 0), self.ss)


def rot(pts, ang, c):
    a = np.deg2rad(ang)
    ca, sa = np.cos(a), np.sin(a)
    return [((x - c[0]) * ca - (y - c[1]) * sa + c[0], (x - c[0]) * sa + (y - c[1]) * ca + c[1]) for x, y in pts]


# --- предметы шести индустрий (барельеф, коробка ~260x260 px 1/4 = 1040 экрана) -----
N = 250


def obj_fader(L, flip=False):
    s = N
    L.add(lambda d, k: d.rounded_rectangle([.30 * s * k, .02 * s * k, .70 * s * k, .98 * s * k], 10 * k, fill=255), 5, 6)
    L.cut(lambda d, k: d.rounded_rectangle([.47 * s * k, .10 * s * k, .53 * s * k, .90 * s * k], 4 * k, fill=255), 4)
    for i in range(11):
        y = (.10 + .08 * i) * s
        ln = .10 if i % 5 == 0 else .06
        L.add(lambda d, k, y=y, ln=ln: d.rectangle([.30 * s * k - 2 * k - ln * s * k, y * k - k, .30 * s * k - 2 * k, y * k + k], fill=255), 2.0, 1)
    cy = .62 * s if not flip else .30 * s
    L.add(lambda d, k: d.rounded_rectangle([.34 * s * k, (cy - .11 * s) * k, .66 * s * k, (cy + .11 * s) * k], 5 * k, fill=255), 16, 6)
    L.cut(lambda d, k: d.rectangle([.36 * s * k, (cy - .01 * s) * k, .64 * s * k, (cy + .01 * s) * k], fill=255), 3)


def obj_headphones(L, flip=False):
    s = N
    c = (.5 * s, .52 * s)
    L.add(lambda d, k: d.arc([.12 * s * k, .06 * s * k, .88 * s * k, .90 * s * k], 180, 360, fill=255, width=int(.075 * s * k)), 10, 5)
    for x in (.14, .86):
        L.add(lambda d, k, x=x: d.rounded_rectangle([(x - .10) * s * k, .46 * s * k, (x + .10) * s * k, .90 * s * k], 12 * k, fill=255), 16, 7)
        L.cut(lambda d, k, x=x: d.rounded_rectangle([(x - .05) * s * k, .54 * s * k, (x + .05) * s * k, .82 * s * k], 8 * k, fill=255), 4)
    # провод
    L.add(lambda d, k: d.line([(.14 * s * k, .90 * s * k), (.20 * s * k, .98 * s * k), (.55 * s * k, .99 * s * k)], fill=255, width=int(.035 * s * k)), 5, 2.5)


def obj_clapper(L, flip=False):
    s = N
    L.add(lambda d, k: d.rounded_rectangle([.04 * s * k, .40 * s * k, .96 * s * k, .96 * s * k], 6 * k, fill=255), 8, 5)
    for i in range(3):
        L.cut(lambda d, k, i=i: d.line([(.12 * s * k, (.55 + .13 * i) * s * k), (.88 * s * k, (.55 + .13 * i) * s * k)], fill=255, width=int(.014 * s * k)), 3)
    arm = [(.04 * s, .20 * s), (.96 * s, .20 * s), (.96 * s, .36 * s), (.04 * s, .36 * s)]
    arm = rot(arm, -11, (.04 * s, .36 * s))
    L.add(lambda d, k: d.polygon([(x * k, y * k) for x, y in arm], fill=255), 12, 5)
    for i in range(6):
        x0 = (.10 + .15 * i) * s
        st = [(x0, .38 * s), (x0 + .06 * s, .38 * s), (x0 + .14 * s, .10 * s), (x0 + .08 * s, .10 * s)]
        st = rot(st, -11, (.04 * s, .36 * s))
        L.cut(lambda d, k, st=st: d.polygon([(x * k, y * k) for x, y in st], fill=255), 3.0, 2.0)
    L.add(lambda d, k: d.ellipse([.02 * s * k, .30 * s * k, .12 * s * k, .46 * s * k], fill=255), 16, 5)


def obj_reel(L, flip=False):
    s = N
    c = s / 2
    L.add(lambda d, k: d.ellipse([(c - .48 * s) * k, (c - .48 * s) * k, (c + .48 * s) * k, (c + .48 * s) * k], fill=255), 9, 8)
    for a in range(6):
        x = c + .27 * s * np.cos(np.deg2rad(a * 60 + 15))
        y = c + .27 * s * np.sin(np.deg2rad(a * 60 + 15))
        L.cut(lambda d, k, x=x, y=y: d.ellipse([(x - .10 * s) * k, (y - .10 * s) * k, (x + .10 * s) * k, (y + .10 * s) * k], fill=255), 7, 1.0)
    L.add(lambda d, k: d.ellipse([(c - .09 * s) * k, (c - .09 * s) * k, (c + .09 * s) * k, (c + .09 * s) * k], fill=255), 14, 5)
    L.cut(lambda d, k: d.ellipse([(c - .03 * s) * k, (c - .03 * s) * k, (c + .03 * s) * k, (c + .03 * s) * k], fill=255), 5)


def obj_lens(L, flip=False):
    s = N
    c = s / 2
    def circ(r):
        return lambda d, k: d.ellipse([(c - r * s) * k, (c - r * s) * k, (c + r * s) * k, (c + r * s) * k], fill=255)
    L.add(circ(.48), 8, 6)
    L.add(circ(.40), 7, 5)
    L.cut(circ(.34), 3)
    L.add(circ(.30), 12, 7)
    L.cut(circ(.16), 8, 0.9)
    for a in range(36):
        x0 = c + .42 * s * np.cos(np.deg2rad(a * 10))
        y0 = c + .42 * s * np.sin(np.deg2rad(a * 10))
        x1 = c + .47 * s * np.cos(np.deg2rad(a * 10))
        y1 = c + .47 * s * np.sin(np.deg2rad(a * 10))
        L.cut(lambda d, k, p=(x0, y0, x1, y1): d.line([(p[0] * k, p[1] * k), (p[2] * k, p[3] * k)], fill=255, width=int(.012 * s * k)), 2)


def obj_camera(L, flip=False):
    s = N
    L.add(lambda d, k: d.rounded_rectangle([.04 * s * k, .22 * s * k, .96 * s * k, .90 * s * k], 14 * k, fill=255), 9, 7)
    L.add(lambda d, k: d.rounded_rectangle([.58 * s * k, .10 * s * k, .84 * s * k, .24 * s * k], 5 * k, fill=255), 12, 4)
    cx, cy = .46 * s, .56 * s
    for r, h in ((.27, 12), (.21, 9)):
        L.add(lambda d, k, r=r: d.ellipse([(cx - r * s) * k, (cy - r * s) * k, (cx + r * s) * k, (cy + r * s) * k], fill=255), h, 6)
    L.cut(lambda d, k: d.ellipse([(cx - .11 * s) * k, (cy - .11 * s) * k, (cx + .11 * s) * k, (cy + .11 * s) * k], fill=255), 6, 0.9)
    L.add(lambda d, k: d.ellipse([.10 * s * k, .28 * s * k, .18 * s * k, .36 * s * k], fill=255), 12, 3)


def obj_scissors(L, flip=False):
    s = N
    piv = (.5 * s, .50 * s)
    b1 = [(.47 * s, .52 * s), (.53 * s, .48 * s), (.74 * s, .02 * s), (.68 * s, .02 * s)]
    b2 = [(.53 * s, .52 * s), (.47 * s, .48 * s), (.26 * s, .02 * s), (.32 * s, .02 * s)]
    for b in (b1, b2):
        L.add(lambda d, k, b=b: d.polygon([(x * k, y * k) for x, y in b], fill=255), 8, 3)
    for hx, ax in ((.30, 1), (.70, -1)):
        L.add(lambda d, k, hx=hx: d.ellipse([(hx - .17) * s * k, .68 * s * k, (hx + .17) * s * k, .99 * s * k], fill=255), 10, 6)
        L.cut(lambda d, k, hx=hx: d.ellipse([(hx - .09) * s * k, .74 * s * k, (hx + .09) * s * k, .93 * s * k], fill=255), 8, 1.2)
        L.add(lambda d, k, hx=hx: d.line([(.5 * s * k, .5 * s * k), ((hx + .02 * ax) * s * k, .72 * s * k)], fill=255, width=int(.06 * s * k)), 8, 3)
    L.add(lambda d, k: d.ellipse([(piv[0] - .045 * s) * k, (piv[1] - .045 * s) * k, (piv[0] + .045 * s) * k, (piv[1] + .045 * s) * k], fill=255), 14, 3)


def obj_spool(L, flip=False):
    s = N
    L.add(lambda d, k: d.rounded_rectangle([.18 * s * k, .06 * s * k, .82 * s * k, .20 * s * k], 5 * k, fill=255), 12, 4)
    L.add(lambda d, k: d.rounded_rectangle([.18 * s * k, .80 * s * k, .82 * s * k, .94 * s * k], 5 * k, fill=255), 12, 4)
    L.add(lambda d, k: d.rectangle([.28 * s * k, .20 * s * k, .72 * s * k, .80 * s * k], fill=255), 8, 5)
    for i in range(14):
        y = (.22 + .042 * i) * s
        L.cut(lambda d, k, y=y: d.line([(.28 * s * k, y * k), (.72 * s * k, (y + .02 * s) * k)], fill=255, width=int(.012 * s * k)), 2)
    # сантиметровая лента
    L.add(lambda d, k: d.rectangle([.88 * s * k, .06 * s * k, .98 * s * k, .94 * s * k], fill=255), 4, 2)
    for i in range(20):
        y = (.08 + .043 * i) * s
        L.cut(lambda d, k, y=y, i=i: d.line([(.88 * s * k, y * k), ((.93 if i % 5 else .97) * s * k, y * k)], fill=255, width=int(.008 * s * k) + 1), 1.5)


def obj_chisel(L, flip=False):
    s = N
    # линейка
    L.add(lambda d, k: d.rectangle([.02 * s * k, .78 * s * k, .98 * s * k, .94 * s * k], fill=255), 5, 2.5)
    for i in range(31):
        x = (.04 + .03 * i) * s
        ln = .10 if i % 5 == 0 else .05
        L.cut(lambda d, k, x=x, ln=ln: d.line([(x * k, .78 * s * k), (x * k, (.78 + ln) * s * k)], fill=255, width=int(.006 * s * k) + 1), 1.5)
    # стамеска: рукоять + втулка + лезвие по диагонали
    h = [(.10 * s, .64 * s), (.40 * s, .50 * s), (.44 * s, .58 * s), (.14 * s, .72 * s)]
    bl = [(.40 * s, .54 * s), (.92 * s, .20 * s), (.97 * s, .27 * s), (.44 * s, .60 * s)]
    L.add(lambda d, k: d.polygon([(x * k, y * k) for x, y in h], fill=255), 20, 8)
    L.add(lambda d, k: d.polygon([(x * k, y * k) for x, y in bl], fill=255), 7, 3)
    ring = rot([(.38 * s, .46 * s), (.46 * s, .46 * s), (.48 * s, .64 * s), (.40 * s, .64 * s)], 0, (0, 0))
    L.add(lambda d, k: d.polygon([(x * k, y * k) for x, y in ring], fill=255), 24, 3)


def obj_mallet(L, flip=False):
    s = N
    L.add(lambda d, k: d.rounded_rectangle([.45 * s * k, .30 * s * k, .56 * s * k, .98 * s * k], 8 * k, fill=255), 11, 5)
    L.add(lambda d, k: d.rounded_rectangle([.08 * s * k, .06 * s * k, .92 * s * k, .38 * s * k], 10 * k, fill=255), 18, 9)
    for x in (.14, .86):
        L.cut(lambda d, k, x=x: d.line([(x * s * k, .08 * s * k), (x * s * k, .36 * s * k)], fill=255, width=int(.02 * s * k)), 3)
    L.cut(lambda d, k: d.line([(.46 * s * k, .55 * s * k), (.55 * s * k, .55 * s * k)], fill=255, width=int(.015 * s * k)), 2)


def obj_megaphone(L, flip=False):
    s = N
    horn = [(.22 * s, .38 * s), (.22 * s, .62 * s), (.94 * s, .88 * s), (.94 * s, .12 * s)]
    L.add(lambda d, k: d.polygon([(x * k, y * k) for x, y in horn], fill=255), 14, 8)
    L.cut(lambda d, k: d.ellipse([.86 * s * k, .14 * s * k, .98 * s * k, .86 * s * k], fill=255), 5, 0.8)
    L.add(lambda d, k: d.rounded_rectangle([.06 * s * k, .40 * s * k, .26 * s * k, .60 * s * k], 8 * k, fill=255), 18, 6)
    L.add(lambda d, k: d.rounded_rectangle([.30 * s * k, .62 * s * k, .46 * s * k, .98 * s * k], 8 * k, fill=255), 14, 6)
    L.cut(lambda d, k: d.ellipse([.34 * s * k, .68 * s * k, .42 * s * k, .76 * s * k], fill=255), 4, 1.0)


def obj_onair(L, flip=False):
    s = N
    c = s / 2
    L.add(lambda d, k: d.rounded_rectangle([.02 * s * k, .02 * s * k, .98 * s * k, .98 * s * k], 22 * k, fill=255), 6, 5)
    for r, h in ((.36, 10), (.28, 14)):
        L.add(lambda d, k, r=r: d.ellipse([(c - r * s) * k, (c - r * s) * k, (c + r * s) * k, (c + r * s) * k], fill=255), h, 7)
    L.cut(lambda d, k: d.ellipse([(c - .33 * s) * k, (c - .33 * s) * k, (c + .33 * s) * k, (c + .33 * s) * k], fill=255), 3)
    L.cut(lambda d, k: d.ellipse([(c - .14 * s) * k, (c - .14 * s) * k, (c + .14 * s) * k, (c + .14 * s) * k], fill=255), 5, 0.8)
    for cx in (.13, .87):
        L.add(lambda d, k, cx=cx: d.ellipse([(cx - .04) * s * k, .08 * s * k, (cx + .04) * s * k, .16 * s * k], fill=255), 5, 2)


OBJECTS = [(obj_fader, obj_headphones), (obj_clapper, obj_reel), (obj_lens, obj_camera),
           (obj_scissors, obj_spool), (obj_chisel, obj_mallet), (obj_megaphone, obj_onair)]
OBJ_CACHE = {}


def object_height(i):
    if i not in OBJ_CACHE:
        L = Local(N, N)
        OBJECTS[i // 2][i % 2](L, flip=bool(i % 2))
        OBJ_CACHE[i] = ndi.gaussian_filter(L.H, 0.9)
    return OBJ_CACHE[i]


# --- сцена: поле высот и альбедо ---------------------------------------------------
FR_Y0, FR_Y1 = 1100, 2400          # фриз по directions.md
FLOOR_Y = 3020


def noise(sig, amp):
    n = ndi.gaussian_filter(rng.standard_normal((H, W)).astype(np.float32), sig)
    return n / (n.std() + 1e-9) * amp


class Scene:
    def __init__(self, relief_gain=1.0):
        self.H = np.zeros((H, W), np.float32)
        self.alb = np.zeros((H, W, 3), np.float32)
        self.carv = []              # вырезанные надписи: dict(mask, bbox, text, cap, ...)
        self.relief_gain = relief_gain
        self.slab = np.zeros((H, W), bool)
        self.floor = np.zeros((H, W), bool)
        self.floor[int(q(FLOOR_Y)):, :] = True
        self.slab[int(q(FR_Y0)):int(q(FR_Y1)), :] = True
        # стена: шероховатая штукатурка + сколы
        self.H += noise(1.2, .10) + noise(5, .16) + noise(26, .8)
        chips = ndi.gaussian_filter((rng.random((H, W)) > .9992).astype(np.float32), 2.0)
        self.H -= chips / (chips.max() + 1e-9) * 2.5
        wall = np.array([0.105, 0.100, 0.095], np.float32)
        self.alb[:] = wall * (1 + noise(8, .10))[..., None]
        # пол
        self.alb[self.floor] = np.array([0.06, 0.055, 0.05], np.float32)
        self.H[self.floor] += noise(.8, .35)[self.floor]
        sk = slice(int(q(FLOOR_Y)) - 3, int(q(FLOOR_Y)) + 2)
        self.H[sk, :] += 3.0                                    # плинтус
        # плита фриза
        s0, s1 = int(q(FR_Y0)), int(q(FR_Y1))
        slab = np.zeros((H, W), np.float32)
        slab[s0:s1, :] = 7.0
        slab[s0:s0 + int(q(70)), :] += 4.0                      # верхняя тяга
        slab[s1 - int(q(70)):s1, :] += 4.0                      # нижняя тяга
        self.H += ndi.gaussian_filter(slab, 1.0)
        pl = np.array([0.80, 0.77, 0.70], np.float32)
        tex = (1 + noise(1.5, .04) + noise(9, .04) + noise(60, .04))[..., None]
        self.alb[s0:s1, :] = (pl * tex)[s0:s1]
        # царапины/следы резца (тонкие диагональные штрихи на плите)
        im = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(im)
        for _ in range(900):
            x, y = rng.uniform(0, W), rng.uniform(s0 + 8, s1 - 8)
            a = np.deg2rad(rng.normal(-32, 8))
            l = rng.uniform(6, 40)
            d.line([(x, y), (x + l * np.cos(a), y + l * np.sin(a))], fill=int(rng.uniform(40, 120)), width=1)
        sc = ndi.gaussian_filter(np.asarray(im, np.float32) / 255, .6)
        self.H[s0:s1] -= (sc * 1.3)[s0:s1]
        # швы-облой: канавки по границам слотов 1250 и тонкий облой посередине слота через один
        for i in range(1, 12):
            x = int(q(1250 * i))
            self.H[s0 + 4:s1 - 4, x - 1:x + 1] -= 2.4
        for i in range(0, 12, 3):
            x = int(q(1250 * i + 625 + 40))
            self.H[s0 + 8:s1 - 8, x:x + 1] += 1.1
        # кабель вдоль нижней тяги (рельеф современности) + USB-штекер на слоте 12
        self.cable()

    def cable(self):
        L = Local(W, int(q(260)))
        ys = int(q(2250 - FR_Y0 + 0))
        xs = np.arange(W)
        yy = q(2290 - 2250) + 6 * np.sin(xs / 140.0) + 3 * np.sin(xs / 37.0 + 1.0)
        im = Image.new("L", (W * 2, L.h * 2), 0)
        d = ImageDraw.Draw(im)
        pts = [(x * 2, (yy[x] + 60) * 2) for x in range(0, W, 3)]
        d.line(pts, fill=255, width=int(q(30) * 2))
        m = np.asarray(im) > 127
        p = down(np.where(m, prof_round(m, 6.0, 3.4, 2), 0), 2)
        y0 = int(q(2290 - 60 - 20 + 100)) - 70
        y0 = int(q(2290)) - int(q(260) / 2) + 0
        self.H[y0:y0 + p.shape[0]] += p
        self.cable_row = y0
        # USB-штекер в конце
        x0 = W - int(q(900))
        plug = Local(int(q(520)), int(q(120)))
        plug.add(lambda d, k: d.rounded_rectangle([0, 0, plug.w * k * .8, plug.h * k], 6 * k, fill=255), 9, 4)
        plug.cut(lambda d, k: d.rectangle([plug.w * k * .2, plug.h * k * .3, plug.w * k * .72, plug.h * k * .7], fill=255), 5, .8)
        ycp = y0 + int(q(260) / 2) - plug.h // 2 + int(yy[x0] - yy[0] + 0)
        self.H[ycp:ycp + plug.h, x0:x0 + plug.w] += plug.H

    # --- содержимое ---------------------------------------------------------------
    def put_object(self, slot_i, x_center=None, scale=1.0, gain=None):
        oh = object_height(slot_i) * 1.7 * (self.relief_gain if gain is None else gain)
        cx = q(1250 * slot_i + 625) if x_center is None else q(x_center)
        cy = q((FR_Y0 + FR_Y1) / 2 - 10)
        if scale != 1.0:
            oh = ndi.zoom(oh, scale, order=1)
        h, w = oh.shape
        x0, y0 = int(cx - w / 2), int(cy - h / 2)
        self.H[y0:y0 + h, x0:x0 + w] += oh

    def put_object_at(self, slot_i, x_center, y_center, size_screen, gain=None):
        """предмет в произвольной точке (центр x,y экрана), коробка size_screen"""
        sc = q(size_screen) / N
        oh = object_height(slot_i) * 1.7 * (self.relief_gain if gain is None else gain)
        oh = ndi.zoom(oh, sc, order=1)
        h, w = oh.shape
        x0, y0 = int(q(x_center) - w / 2), int(q(y_center) - h / 2)
        self.H[y0:y0 + h, x0:x0 + w] += oh

    def recess(self, x0, x1, y0, y1, depth=9.0):
        """ниша: прямоугольное углубление с фаской (в экранных px)"""
        m = np.zeros((H, W), np.float32)
        m[int(q(y0)):int(q(y1)), int(q(x0)):int(q(x1))] = 1
        m = ndi.gaussian_filter(m, 1.6)
        self.H -= m * depth
        self.alb[(m > .5)] *= 0.93

    def carve(self, lines, x, y_top, cap, align="left", gap=0.26, name="", fill_to=None, fill_all=False,
              slope=1.35, cap_min=None):
        """вырезать V-врезом строки. x — левый край (align=left) или правый (align=right), экран px.
        Возвращает bbox. fill_to — экранный x, до которого залита киноварь (None = не залита)."""
        out = []
        cap_use = cap
        y = y_top
        info = dict(name=name or " / ".join(lines), cap=cap_use, lines=[], fill_to=fill_to)
        for ln in lines:
            f = font_for_cap(q(cap_use) * 2)
            wpx = f.getlength(ln)
            tw = wpx / 2                                     # ширина в px 1/4
            xl = q(x) if align == "left" else q(x) - tw
            im = Image.new("L", (int(wpx) + 40, int(q(cap_use) * 2 * 1.5) + 40), 0)
            dr = ImageDraw.Draw(im)
            bb = f.getbbox("H")
            dr.text((20, 20 - bb[1] + int(q(cap_use) * 2 * .3)), ln, font=f, fill=255)
            m = np.asarray(im) > 127
            depth = q(cap_use) * 0.0666 * slope * 0.8
            p, dt = prof_vgroove(m, slope, max(depth, 3.0), 2)
            p = np.where(m, p, 0)
            pd = down(p, 2)
            dtd = down(np.where(m, dt, 0), 2)
            mm = down(m.astype(np.float32), 2)
            gx0 = int(round(xl - 10))
            gy0 = int(round(q(y) - 10 - q(cap_use) * .3 + 0))
            h2, w2 = pd.shape
            self._paste(pd, gx0, gy0, "H")
            full = np.zeros((H, W), np.float32)
            dfull = np.zeros((H, W), np.float32)
            self._paste(mm, gx0, gy0, "m", full)
            self._paste(dtd, gx0, gy0, "m", dfull)
            out.append(dict(text=ln, x0=xl * SCALE, x1=(xl + tw) * SCALE, y_top=y, cap=cap_use, mask=full, dt=dfull,
                            maxdt=max(depth / slope, 1.0)))
            y += cap_use * (1 + gap)
        self.carv.append(out)
        s0_, s1_ = int(q(FR_Y0)), int(q(FR_Y1))
        xa, xb = min(r["x0"] for r in out), max(r["x1"] for r in out)
        for i in range(1, 12):
            if xa - 80 <= 1250 * i <= xb + 80:
                x = int(q(1250 * i))
                self.H[s0_ + 4:s1_ - 4, x - 1:x + 1] += 2.4
        # киноварь — в нижней части V-реза
        for rec in out:
            if fill_to is None and not fill_all:
                continue
            fx = fill_to if fill_to is not None else 1e9
            col = np.arange(W)[None, :] * SCALE
            soft = np.clip((fx - col) / 24.0 + .5, 0, 1)
            pool = np.clip((rec["dt"] - rec["maxdt"] * .22) / 1.0, 0, 1) * (rec["mask"] > .5)
            wob = 1 + noise(2, .08)
            a = np.clip(pool * soft * wob, 0, 1)[..., None]
            self.alb = self.alb * (1 - a) + np.array([0.78, 0.125, 0.075], np.float32) * a
        return (out[0]["x0"], y_top, max(r["x1"] for r in out), y - cap_use * gap)

    def _paste(self, arr, x0, y0, mode, target=None):
        h, w = arr.shape
        xa, ya = max(x0, 0), max(y0, 0)
        xb, yb = min(x0 + w, W), min(y0 + h, H)
        if xb <= xa or yb <= ya:
            return
        sub = arr[ya - y0:yb - y0, xa - x0:xb - x0]
        if mode == "H":
            self.H[ya:yb, xa:xb] += sub
        else:
            target[ya:yb, xa:xb] = np.maximum(target[ya:yb, xa:xb], sub)

    def raised_tablet(self, x0, y0, x1, y1, hgt=9.0):
        m = np.zeros((H, W), np.float32)
        m[int(q(y0)):int(q(y1)), int(q(x0)):int(q(x1))] = 1
        dt = ndi.distance_transform_edt(m > .5)
        self.H += hgt * np.sqrt(np.clip(1 - (1 - np.clip(dt / 5, 0, 1)) ** 2, 0, 1)) * m
        pl = np.array([0.80, 0.77, 0.70], np.float32)
        sel = m > .5
        self.alb[sel] = pl * (1 + noise(1.5, .05))[sel][:, None]


# --- свет --------------------------------------------------------------------------
def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a + 1e-9), 0, 1)
    return t * t * (3 - 2 * t)


def light_lamp(Hs, nrm, lamp):
    """вклад одной лампы (линейный RGB-массив H x W x 3 в пределах окна). lamp — dict, экран px."""
    ax, ay = q(lamp["ax"]), q(lamp["ay"])
    Rx, Ry = q(lamp["Rx"]), q(lamp["Ry"])
    ang = np.deg2rad(lamp["angle"])
    sgn = lamp.get("side", -1)                  # -1: лампа слева от пятна
    d = q(lamp["d"]) if "d" in lamp else lamp["z"] / np.tan(ang) if False else None
    z = q(lamp["z"])
    d = z / np.tan(ang)                         # горизонтальное смещение лампы от центра пятна
    sx = ax + sgn * d
    sy = q(lamp.get("sy", lamp["ay"] - 500))
    lamp["_src"] = (sx * SCALE, sy * SCALE, z * SCALE)
    pad = 1.35
    x0, x1 = int(max(0, ax - Rx * pad)), int(min(W, ax + Rx * pad))
    y0, y1 = int(max(0, ay - Ry * pad)), int(min(H, ay + Ry * pad))
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    h = Hs[y0:y1, x0:x1]
    vx, vy, vz = sx - xx, sy - yy, z - h
    dist = np.sqrt(vx ** 2 + vy ** 2 + vz ** 2)
    Lx, Ly, Lz = vx / dist, vy / dist, vz / dist
    n = nrm[y0:y1, x0:x1]
    ndl = np.clip(n[..., 0] * Lx + n[..., 1] * Ly + n[..., 2] * Lz, 0, None)
    # нормировка: плоская стена в центре пятна получает I независимо от угла
    d_aim = np.sqrt((sx - ax) ** 2 + (sy - ay) ** 2 + z ** 2)
    sin_aim = z / d_aim
    gain = 0.60 * lamp["I"] / sin_aim * (d_aim / dist) ** 2
    r = np.sqrt(((xx - ax) / Rx) ** 2 + ((yy - ay) / Ry) ** 2)
    cone = 1 - smoothstep(1 - lamp["soft"], 1.0, r)
    # жёсткая тень: марш по высотному полю к лампе
    sh = np.ones_like(h)
    if lamp.get("shadow", True):
        hd = np.sqrt(vx ** 2 + vy ** 2) + 1e-6
        ux, uy = vx / hd, vy / hd
        step = 1.2
        for k in range(1, 70):
            s = k * step
            qx = np.clip(xx + ux * s, 0, W - 1)
            qy = np.clip(yy + uy * s, 0, H - 1)
            hq = ndi.map_coordinates(Hs, [qy, qx], order=1)
            hray = h + s * (z - h) / hd
            sh = np.minimum(sh, np.where(hq > hray + .25, 0.0, 1.0))
        sh = ndi.gaussian_filter(sh, lamp.get("shadow_blur", .6))
    out = (gain * ndl * cone * sh)[..., None] * LAMP_TINT[None, None, :] * 0.88
    return (y0, y1, x0, x1), out


def ambient_profile(spec):
    """громкость «памяти стены» по x (экран): 0..1; список узлов (x, value)"""
    nodes = spec.get("amb_nodes", [(0, .06), (15000, .06)])
    xs = np.arange(W) * SCALE
    return np.interp(xs, [n[0] for n in nodes], [n[1] for n in nodes]).astype(np.float32)


def draw_lamp_fixture(img, lamp, bright=1.0):
    """видимая лампа на стойке (в линейном RGB, 1/4)"""
    sx, sy, sz = lamp["_src"]
    base_y = 3180
    im = Image.fromarray((img * 0).astype(np.uint8))
    return None


def render(spec, sim_dither=True):
    sc = Scene(relief_gain=spec.get("relief_gain", 1.0))
    spec["build"](sc)
    Hs = ndi.gaussian_filter(sc.H, .55)
    gy, gx = np.gradient(Hs)
    nz = 1.0 / np.sqrt(gx ** 2 + gy ** 2 + 1)
    nrm = np.stack([-gx * nz, -gy * nz, nz], -1)
    # ambient: слабый направленный от верха-лева, тёплый
    La = np.array([-.55, -.55, .63], np.float32)
    La /= np.linalg.norm(La)
    ndl_a = np.clip(nrm @ La, 0, None)
    A = ambient_profile(spec)[None, :]
    amb = A * (0.20 + 0.80 * np.clip(ndl_a / La[2], 0, 1.6))
    lin = sc.alb * (amb[..., None] * AMB_TINT[None, None, :] * 1.0)
    lin = lin + sc.alb * 0.0
    for lamp in spec["lamps"]:
        (y0, y1, x0, x1), c = light_lamp(Hs, nrm, lamp)
        lin[y0:y1, x0:x1] += sc.alb[y0:y1, x0:x1] * c
        # пятно света на полу (пол ~ перпендикулярен стене): мягкий эллипс под лампой
        yy, xx = np.mgrid[int(q(FLOOR_Y)):H, x0:x1].astype(np.float32)
    # пол: отражённый свет под пятном + пыль
    for lamp in spec["lamps"]:
        ax = q(lamp["ax"])
        fl = int(q(FLOOR_Y))
        yy, xx = np.mgrid[fl:H, 0:W].astype(np.float32)
        g = np.exp(-(((xx - ax) / q(lamp["Rx"] * .9)) ** 2 + ((yy - fl) / q(520)) ** 2)) * 0.05 * lamp["I"]
        lin[fl:] += (g[..., None] * LAMP_TINT) * sc.alb[fl:] * 4
    spec_lin = lin
    # видимые лампы
    spec_lin = draw_fixtures(spec_lin, spec)
    # тон: мягкое плечо без bloom
    t = spec_lin
    t = t / (1 + 0.35 * t)
    t = np.clip(t, 0, 1)
    srgb = np.where(t <= .0031308, t * 12.92, 1.055 * np.power(t, 1 / 2.4) - .055)
    if sim_dither:
        # TPDF-дизеринг ~1 LSB + плёночное зерно в тёмном (амплитуда по яркости)
        nz1 = rng.random(srgb.shape[:2]).astype(np.float32) - rng.random(srgb.shape[:2]).astype(np.float32)
        srgb = srgb + nz1[..., None] / 255.0
    return sc, np.clip(np.round(srgb * 255), 0, 255).astype(np.uint8), srgb


def draw_fixtures(lin, spec):
    """видимая лампа: конический кожух, ось на пятно, стойка-тренога; кабель по полу"""
    out = lin.copy()
    for lamp in spec["lamps"]:
        if not lamp.get("fixture", True):
            continue
        sx, sy, sz = lamp["_src"]
        ux, uy = lamp["ax"] - sx, lamp["ay"] - sy
        nn = np.hypot(ux, uy)
        ux, uy = ux / nn, uy / nn
        nx, ny = -uy, ux
        P = lambda x, y: (q(x) * 2, q(y) * 2)
        mask = Image.new("L", (W * 2, H * 2), 0)
        md = ImageDraw.Draw(mask)
        back = (sx - ux * 330, sy - uy * 330)
        poly = [P(sx + nx * 105, sy + ny * 105), P(sx - nx * 105, sy - ny * 105),
                P(back[0] - nx * 55, back[1] - ny * 55), P(back[0] + nx * 55, back[1] + ny * 55)]
        md.polygon(poly, fill=255)
        floor_y = 3190
        px = back[0] + 30
        md.line([P(px, back[1] + 20), P(px, floor_y)], fill=255, width=max(2, int(q(60) * 2)))
        for a in (-1, 1):
            md.line([P(px, floor_y - 300), P(px + a * 330, floor_y + 90)], fill=255, width=max(2, int(q(46) * 2)))
        md.line([P(px, floor_y - 520), P(px + 150, floor_y - 330)], fill=255, width=max(2, int(q(30) * 2)))
        m = np.asarray(mask.resize((W, H), Image.LANCZOS), np.float32) / 255
        lens = Image.new("L", (W * 2, H * 2), 0)
        ld = ImageDraw.Draw(lens)
        pts = []
        for t in np.linspace(0, 2 * np.pi, 40):
            pts.append(P(sx + ux * 10 * np.cos(t) + nx * 92 * np.sin(t), sy + uy * 10 * np.cos(t) + ny * 92 * np.sin(t)))
        ld.polygon(pts, fill=255)
        lm = np.asarray(lens.resize((W, H), Image.LANCZOS), np.float32) / 255
        body = np.array([0.011, 0.011, 0.012], np.float32)
        out = out * (1 - m[..., None]) + body * m[..., None]
        rim = np.clip(ndi.gaussian_filter(m, .8) - ndi.gaussian_filter(m, 2.8) * .9, 0, None) * .30
        out += rim[..., None] * LAMP_TINT * lamp.get("fixture_rim", 1.0)
        L = lamp.get("lens_level", .45)
        out = out * (1 - lm[..., None]) + (LAMP_TINT * L)[None, None, :] * lm[..., None]
    return out


# --- кадры ----------------------------------------------------------------------------
NAMES = dict(
    artist=["ЭЛИО", "БРАНД"],
    host_a=["ЙОНАС", "ЁЛКИН"],
    host_b=["ДАНА", "ВОЛК"],
    prev1=["МАРЕН", "КОВАЧ"],
    prev2=["ТИМ", "СЪЕДИН"],
    laur=["ЯНА", "ОРЛОВА"],
)


def slots_free(sc_fn, skip):
    pass


def fill_objects(sc, skip_ranges, only=None, gain=None):
    """предметы во всех слотах, кроме перекрытых блоками (диапазоны x экрана)"""
    for i in range(12):
        a, b = 1250 * i, 1250 * (i + 1)
        if any(not (b <= s0 or a >= s1) for s0, s1 in skip_ranges):
            continue
        if only is not None and i not in only:
            continue
        sc.put_object(i, gain=gain)


def build_b1(sc):
    fill_objects(sc, [])
    # перемычка [G8-плейсхолдер]: x 7500-8750, над фризом
    sc.raised_tablet(7500 + 40, 330, 8750 - 40, 1070, 9)
    f_cap = 420
    wG8 = text_width("G8", f_cap)
    x = 8125 - wG8 / 2
    sc.carve(["G8"], x, 400, f_cap, name="G8_wordmark_placeholder")
    # инвентарный номер (служебный голос, cap 160)
    sc.carve(["№ 0008"], 7500 + 190, 880, 160, name="inv_number")


def build_b2(sc):
    skip = [(5000, 7500)]
    fill_objects(sc, skip)
    sc.carve(NAMES["artist"], 5150, 1275, 420, name="artist")


def build_b3(sc):
    skip = [(5000, 7500), (7500, 10000)]
    fill_objects(sc, skip)
    w = max(text_width(t, 420) for t in NAMES["host_a"])
    sc.carve(NAMES["host_a"], 7200 - w, 1275, 420, align="left", name="host_a")
    sc.carve(NAMES["host_b"], 7800, 1275, 420, name="host_b")


NICHE_X0, NICHE_W = 3750, 1875
NICHE_NAMES = ["АРНО", "БРАНД", "ЙОНАС", "КОВАЧ", "ЛИНДКВИСТ"]


def build_b4(sc):
    # категория: слово на перемычке (cap 700), 5 ниш по 1875 (кратно половине выхода)
    sc.raised_tablet(7480, 250, 10780, 1060, 9)
    sc.carve(["ЗВУК"], 7650, 340, 700, name="category_word")
    for i in range(5):
        x0 = NICHE_X0 + NICHE_W * i
        sc.recess(x0 + 70, x0 + NICHE_W - 70, FR_Y0 + 90, FR_Y1 - 90, 9.0)
    for i in range(5):
        x0 = NICHE_X0 + NICHE_W * i
        cx = x0 + NICHE_W / 2
        sc.put_object_at(i * 2 + 1 if i != 2 else 4, cx, 1560, 900)
        nm = NICHE_NAMES[i]
        cap = 300
        wmax = NICHE_W - 330
        w = text_width(nm, cap)
        if w > wmax:
            cap = cap * wmax / w                 # авто-ужим (правило длинных данных)
            w = wmax
        sc.carve([nm], cx - w / 2, 2060 + (300 - cap) / 2, cap, name="nominee_%d" % (i + 1))
    # слева — остальные слоты: предметы, чтобы фриз не обрывался
    for i in range(3):
        sc.put_object(i)
    sc.put_object(11)


def build_b5(sc):
    # предыдущие лауреаты: киноварь залита. Панели 1 и 2
    fill_objects(sc, [(1500, 3650), (4300, 7000), (7500, 11250)])
    sc.carve(NAMES["prev1"], 1500, 1275, 420, name="prev1", fill_all=True)
    sc.carve(NAMES["prev2"], 4300, 1275, 420, name="prev2", fill_all=True)
    # текущий лауреат: предмет слева в слоте 7, имя 2 строки в слотах 8-9
    sc.put_object_at(8, 8050, 1750, 960)
    wmax = max(text_width(t, 420) for t in NAMES["laur"])
    xn = 8800
    sc.carve(NAMES["laur"], xn, 1275, 420, name="laureate", fill_to=xn + wmax * 0.62)
    # на стене справа — ещё не награждённые панели: предметы
    fill_objects(sc, [(0, 7500), (7500, 11250)], only=range(9, 12))


FRAMES = {
    "b1_intro": dict(
        title="Интро: лампа замерла на перемычке G8 (пауза 2 с)", build=build_b1,
        lamps=[dict(ax=8125, ay=1300, Rx=1500, Ry=1250, angle=25, z=840, I=1.0, soft=.55, sy=1950)],
        amb_nodes=[(0, .075), (6300, .06), (7400, .035), (9000, .008), (15000, .004)]),
    "b2_artists": dict(
        title="Выход артиста: жёсткое пятно с именем, угол 35°", build=build_b2,
        lamps=[dict(ax=6180, ay=1760, Rx=1750, Ry=1050, angle=20, z=764, I=0.95, soft=.30, sy=2150)],
        amb_nodes=[(0, .035), (15000, .035)]),
    "b3_hosts": dict(
        title="Ведущие: два мягких пятна сливаются на стыке, рельеф приглушён", build=build_b3,
        relief_gain=.30,
        lamps=[dict(ax=6300, ay=1750, Rx=2300, Ry=1250, angle=30, z=1478, I=.58, soft=.85, sy=1900, side=-1, shadow_blur=2.0),
               dict(ax=8700, ay=1750, Rx=2300, Ry=1250, angle=30, z=1478, I=.58, soft=.85, sy=1900, side=1, shadow_blur=2.0)],
        amb_nodes=[(0, .03), (15000, .03)]),
    "b4_nominations": dict(
        title="Номинации: пять ниш, лампа в третьей, остальные 15%", build=build_b4,
        lamps=[dict(ax=8437, ay=1750, Rx=1250, Ry=1050, angle=22, z=1131, I=1.0, soft=.40, sy=1750)],
        amb_nodes=[(0, .05), (15000, .05)]),
    "b5_award": dict(
        title="Награждение: лампа встала, угол 8°, киноварь заливает врез слева направо", build=build_b5,
        lamps=[dict(ax=9900, ay=1760, Rx=2050, Ry=1000, angle=9, z=400, I=1.0, soft=.38, sy=2060, shadow_blur=.5)],
        amb_nodes=[(0, .05), (7300, .05), (11000, .03), (15000, .02)]),
}


def save_all(name, spec):
    spec["_name"] = name
    sc, img8, srgbf = render(spec)
    out = os.path.join(HERE, name + ".png")
    Image.fromarray(img8).save(out, optimize=True)
    Image.fromarray(img8).resize((W // 2, H // 2), Image.LANCZOS).save(os.path.join(HERE, name + "_preview8.png"))
    return sc, img8, srgbf


def make_sheet(imgs):
    """лист: кадры 1/16 один под другим, слева цвет с осями стыков, справа серый тест"""
    s = 4  # 1/4 -> 1/16
    tw, th = W // s, H // s
    pad, lab = 24, 20
    sw = pad * 3 + tw * 2
    sh = pad + len(imgs) * (th + lab + 10) + pad
    sheet = Image.new("RGB", (sw, sh), (14, 14, 14))
    d = ImageDraw.Draw(sheet)
    f = ImageFont.truetype(FONT_REG, 12)
    y = pad
    for name, im in imgs:
        small = Image.fromarray(im).resize((tw, th), Image.LANCZOS)
        g = small.convert("L").convert("RGB")
        sheet.paste(small, (pad, y + lab))
        sheet.paste(g, (pad * 2 + tw, y + lab))
        d.text((pad, y + 3), name + "   (1/16; оси: стыки 3750 / 7500 / 11250, поля безопасной зоны 1500 / 13500)", fill=(150, 150, 150), font=f)
        d.text((pad * 2 + tw, y + 3), "серый тест", fill=(150, 150, 150), font=f)
        for ox in (pad, pad * 2 + tw):
            for sx_ in SEAMS:
                x = ox + sx_ // 16
                for yy in range(y + lab, y + lab + th, 6):
                    d.line([(x, yy), (x, yy + 3)], fill=(60, 140, 170))
            for sx_ in (1500, 13500):
                x = ox + sx_ // 16
                for yy in range(y + lab, y + lab + th, 8):
                    d.point((x, yy), fill=(120, 120, 60))
            d.rectangle([ox, y + lab, ox + tw - 1, y + lab + th - 1], outline=(40, 40, 40))
        y += th + lab + 10
    sheet.save(os.path.join(HERE, "_sheet.png"))
    return sheet


def main():
    names = sys.argv[1:] or list(FRAMES)
    imgs = []
    meta = {}
    for n in names:
        sc, img8, sf = save_all(n, FRAMES[n])
        imgs.append((n, img8))
        meta[n] = dict(
            title=FRAMES[n]["title"],
            lamps=[{k: v for k, v in l.items() if not k.startswith("_")} | {"lamp_source_xyz_screen": [round(v) for v in l["_src"]]} for l in FRAMES[n]["lamps"]],
            carved=[[dict(text=r["text"], x0=round(r["x0"]), x1=round(r["x1"]), cap=round(r["cap"], 1)) for r in grp] for grp in sc.carv],
            relief_gain=FRAMES[n].get("relief_gain", 1.0))
        print("ok", n)
    if len(names) == len(FRAMES):
        make_sheet(imgs)
        with open(os.path.join(HERE, "frames_spec.json"), "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
