"""Стайлфреймы стадии 03 «Зазор» — pz26_nagrazhdenie. Blender (bpy 5.2), Cycles + OIDN.

Одна команда — все кадры:
    python make_frames.py                      # S1, S1 hires, S2, S3, S4, лист
    python make_frames.py --only s1 s3         # часть кадров
    python make_frames.py --samples 48 --scale 0.5   # быстрый черновик (в scratch, не в frames/)
Запуск через Blender: blender -b -P make_frames.py -- --only s1

Что строится (см. 03_style/direction.md, п. 4, 5, 6, 9):
  S1 «Линия среза»  s1_line.png (1920x384), s1_line_hires.png (3840x768)
  S2 «Разрез»       s2_cut.png
  S3 «Ключ входит»  s3_enter.png
  S4 «Карточка бокового экрана» s4_card.png (центр 5:1 + два квадрата, на ВРЕМЕННОМ шрифте Inter)
  _sheet.png        контактный лист (цвет + серый + миниатюра 1/8)
Данные: высоты штифтов = md5(id) из data/laureates.csv (не рейтинг). Seed фиксирован (SEED).
Единица сцены: 1 u = 5 мм (штифт r=0.36 u = Ø3.6 мм). Масштабы текстур заданы в u, а не в метрах из п. 5.
"""
import argparse, csv, hashlib, math, os, random, sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))
CSV = os.path.join(PROJ, "data", "laureates.csv")
ap = argparse.ArgumentParser()
ap.add_argument("--only", nargs="*", default=["s1", "s1hi", "s2", "s3", "s4", "sheet"])
ap.add_argument("--samples", type=int, default=160)
ap.add_argument("--hi_samples", type=int, default=256)
ap.add_argument("--scale", type=float, default=1.0, help="масштаб разрешения (черновики)")
ap.add_argument("--out", default=HERE)
ap.add_argument("--scratch", default=os.path.join(HERE, "_scratch"))
ap.add_argument("--tag", default="")
ap.add_argument("--crop", default="", help="x0,y0,x1,y1 в долях кадра: рендер только области (для подбора)")
ap.add_argument("--P", default="{}", help="JSON-переопределение параметров света (для подбора)")
A = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
SEED = 2610
os.makedirs(A.scratch, exist_ok=True)

NEED_BPY = any(k in A.only for k in ("s1", "s1hi", "s2", "s3", "s4", "test"))
if NEED_BPY:
    import bpy, bmesh
    from mathutils import Vector
    from bpy_extras.object_utils import world_to_camera_view

# ------------------------------------------------------------------ данные
rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
IDS = [r["id"] for r in rows]
assert len(IDS) == 35
H = [int(hashlib.md5(i.encode()).hexdigest()[:8], 16) / 2**32 for i in IDS]
PITCH, SEC_GAP = 1.1, 1.6
RP = 0.36                      # радиус штифта, u (1 u = 5 мм)
GAP = 0.035                    # полу-зазор шва, u (0.06 u = 0.3 мм)
FIL = 0.03                     # фаска/скругление торцов (0.15 мм)
KEY_R = (0.14, 0.26)
BODY_R = (0.32, 0.50)           # шероховатость плоскости разреза (шлифованная сталь, вариация по шуму)
WIN_Z, PK_Z = 1.6, -1.3       # окно пружин начинается выше шва на 1.6 u; карман ключа ниже шва на 1.3 u
D_LEN = 0.55                   # длина верхнего штифта (драйвера)
LEN = [1.0 + 1.9 * h for h in H]   # длина нижнего штифта = хэш id


def pin_positions():
    PX, x = [], 0.0
    for i in range(35):
        if i and i % 5 == 0:
            x += SEC_GAP
        PX.append(x); x += PITCH
    mid = (PX[0] + PX[-1]) / 2
    return [p - mid for p in PX]


PX = pin_positions()


def lin(h):
    h = h.lstrip("#"); c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(((v + 0.055) / 1.055) ** 2.4 if v > 0.04045 else v / 12.92 for v in c) + (1.0,)


# ------------------------------------------------------------------ узлы материалов
def nd(t, typ, **kw):
    n = t.nodes.new(typ)
    for k, v in kw.items():
        if k in n.inputs: n.inputs[k].default_value = v
        else: setattr(n, k, v)
    return n


def ln(t, a, b, i=None, j=None):
    o = a.outputs[i if i is not None else 0]
    inp = b.inputs[j if j is not None else 0]
    t.links.new(o, inp)


def val(t, v):
    n = t.nodes.new("ShaderNodeValue"); n.outputs[0].default_value = v; return n


def mth(t, op, a, b=None, clamp=False):
    n = t.nodes.new("ShaderNodeMath"); n.operation = op; n.use_clamp = clamp
    for i, x in enumerate((a, b)):
        if x is None: continue
        if isinstance(x, (int, float)): n.inputs[i].default_value = x
        else: t.links.new(x.outputs[0] if hasattr(x, "outputs") else x, n.inputs[i])
    return n


def ramp(t, fac, stops, interp="LINEAR"):
    r = t.nodes.new("ShaderNodeValToRGB"); r.color_ramp.interpolation = interp
    el = r.color_ramp.elements
    while len(el) < len(stops): el.new(0.5)
    for e, (p, v) in zip(el, stops):
        e.position = p; e.color = (v, v, v, 1) if isinstance(v, (int, float)) else v
    t.links.new(fac.outputs[0] if hasattr(fac, "outputs") else fac, r.inputs["Fac"]); return r


def maprange(t, src, a0, a1, b0=0.0, b1=1.0, clamp=True, out=0):
    m = t.nodes.new("ShaderNodeMapRange"); m.clamp = clamp
    m.inputs["From Min"].default_value = a0; m.inputs["From Max"].default_value = a1
    m.inputs["To Min"].default_value = b0; m.inputs["To Max"].default_value = b1
    t.links.new(src, m.inputs["Value"]); return m


def make_metal(name, base_hex, rough_lo, rough_hi, aniso, tangent, ax_scale, bump=0.12,
               scratch=None, graphite=0.0, oil=0.0, patina=True, per_object=True, wear=0.0,
               wear_rough=0.14, brass=False, sec_ramp=None, cut_plane=False):
    """Металл по п. 5.1/5.2. ax_scale=(sx,sy,sz) для шума в u^-1: вытянут вдоль оси обработки.
    scratch=(sx,sy,sz,width): Voronoi distance-to-edge, вытянутый вдоль царапин.
    graphite — доля покрытия налётом смазки; oil — доля площади с масляной плёнкой; wear — доля полированных площадок.
    sec_ramp — множители графита по 7 секциям (по world X)."""
    m = bpy.data.materials.new(name); m.use_nodes = True; t = m.node_tree
    for n in list(t.nodes): t.nodes.remove(n)
    out = nd(t, "ShaderNodeOutputMaterial")
    tc = nd(t, "ShaderNodeTexCoord"); geo = nd(t, "ShaderNodeNewGeometry")
    oi = nd(t, "ShaderNodeObjectInfo")
    # смещение шума на объект (чтобы 35 штифтов не были копиями)
    vm = nd(t, "ShaderNodeVectorMath", operation="SCALE"); t.links.new(oi.outputs["Random"], vm.inputs[3]); vm.inputs[0].default_value = (37.0, 53.0, 71.0)
    def mapping(sc, loc_from_rand=True):
        mp = nd(t, "ShaderNodeMapping"); mp.inputs["Scale"].default_value = sc
        t.links.new(tc.outputs["Object"], mp.inputs["Vector"])
        if loc_from_rand and per_object: t.links.new(vm.outputs[0], mp.inputs["Location"])
        return mp
    # 1. шум обработки (риски вдоль оси)
    nz = nd(t, "ShaderNodeTexNoise", **{"Scale": 1.0, "Detail": 6.0, "Roughness": 0.55}); t.links.new(mapping(ax_scale).outputs[0], nz.inputs["Vector"])
    # 2. царапины
    sc_mask = None
    if scratch:
        # царапины = изолинии сильно вытянутого шума: длинные, почти параллельные, разной длины (не «плитка» Вороного)
        sn = nd(t, "ShaderNodeTexNoise", **{"Scale": 1.0, "Detail": 0.0, "Roughness": 0.5, "Distortion": 0.0})
        t.links.new(mapping(scratch[:3]).outputs[0], sn.inputs["Vector"])
        dev = mth(t, "ABSOLUTE", mth(t, "SUBTRACT", sn.outputs["Fac"], 0.5))
        sc_mask = ramp(t, dev, [(0.0, 1.0), (scratch[3], 0.0)])
    # 3. полированные площадки износа
    wr_mask = None
    if wear > 0:
        wn = nd(t, "ShaderNodeTexNoise", **{"Scale": 1.0, "Detail": 3.0, "Roughness": 0.6}); wsc = (0.9, 0.9, 0.9) if not brass else (0.7, 0.7, 0.7)
        t.links.new(mapping(wsc).outputs[0], wn.inputs["Vector"])
        wr_mask = ramp(t, wn.outputs["Fac"], [(1 - wear - 0.04, 0.0), (1 - wear + 0.04, 1.0)])
    # roughness
    r0 = maprange(t, nz.outputs["Fac"], 0.25, 0.75, rough_lo, rough_hi, True)
    rough_out = r0.outputs[0]
    if sc_mask is not None:
        rs = mth(t, "SUBTRACT", rough_out, mth(t, "MULTIPLY", sc_mask, 0.18)); rough_out = rs.outputs[0]
    if wr_mask is not None:
        rm = nd(t, "ShaderNodeMix", data_type="FLOAT"); t.links.new(wr_mask.outputs[0], rm.inputs[0]); t.links.new(rough_out, rm.inputs[2]); rm.inputs[3].default_value = wear_rough; rough_out = rm.outputs[0]
    # bump
    hmix = mth(t, "SUBTRACT", nz.outputs["Fac"], mth(t, "MULTIPLY", sc_mask, 1.5) if sc_mask is not None else 0.0)
    bp = nd(t, "ShaderNodeBump", **{"Strength": bump, "Distance": 0.012}); t.links.new(hmix.outputs[0], bp.inputs["Height"])
    # patina/AO
    base = nd(t, "ShaderNodeRGB"); base.outputs[0].default_value = lin(base_hex)
    col_out = base.outputs[0]
    if patina:
        ao = nd(t, "ShaderNodeAmbientOcclusion", **{"Distance": 0.18, "samples": 4}); 
        pc = nd(t, "ShaderNodeRGB"); pc.outputs[0].default_value = lin("#2A1D0C" if brass else "#1A2224")
        mx = nd(t, "ShaderNodeMix", data_type="RGBA"); t.links.new(ao.outputs["AO"], mx.inputs[0])
        mx.inputs[6].default_value = lin("#2A1D0C" if brass else "#1A2224"); t.links.new(base.outputs[0], mx.inputs[7]); col_out = mx.outputs[2]
        # AO=0 в полости -> цвет патины
    bs = nd(t, "ShaderNodeBsdfPrincipled", **{"Metallic": 1.0, "Anisotropic": aniso})
    t.links.new(col_out, bs.inputs["Base Color"]); t.links.new(rough_out, bs.inputs["Roughness"]); t.links.new(bp.outputs["Normal"], bs.inputs["Normal"])
    tv = nd(t, "ShaderNodeCombineXYZ"); tv.inputs[0].default_value, tv.inputs[1].default_value, tv.inputs[2].default_value = tangent
    t.links.new(tv.outputs[0], bs.inputs["Tangent"])
    # масляная плёнка (Coat)
    if oil > 0:
        on = nd(t, "ShaderNodeTexNoise", **{"Scale": 1.0, "Detail": 2.0, "Roughness": 0.5})
        t.links.new(mapping((0.22, 0.22, 0.22), False).outputs[0], on.inputs["Vector"])
        om = ramp(t, on.outputs["Fac"], [(1 - oil * 0.55 - 0.03, 0.0), (1 - oil * 0.55 + 0.02, 1.0)])
        cw = mth(t, "MULTIPLY", om, 0.35); t.links.new(cw.outputs[0], bs.inputs["Coat Weight"]); bs.inputs["Coat Roughness"].default_value = 0.05
    shader = bs
    if graphite > 0:
        gn = nd(t, "ShaderNodeTexNoise", **{"Scale": 1.0, "Detail": 5.0, "Roughness": 0.6})
        t.links.new(mapping((3.0, 3.0, 3.0), False).outputs[0], gn.inputs["Vector"])
        gf = nd(t, "ShaderNodeTexNoise", **{"Scale": 1.0, "Detail": 2.0, "Roughness": 0.5})
        t.links.new(mapping((70.0, 70.0, 70.0), False).outputs[0], gf.inputs["Vector"])
        gmix = mth(t, "ADD", gn.outputs["Fac"], mth(t, "MULTIPLY", mth(t, "SUBTRACT", gf.outputs["Fac"], 0.5), 0.25))
        thr = 1 - graphite
        if sec_ramp:
            # множитель по секциям: сдвиг порога
            sep = nd(t, "ShaderNodeSeparateXYZ"); gp = nd(t, "ShaderNodeNewGeometry")
            t.links.new(gp.outputs["Position"], sep.inputs[0])
            fx = maprange(t, sep.outputs[0], -25.0, 25.0, 0.0, 1.0, True)
            sr = ramp(t, fx, [(i / 7, v) for i, v in enumerate(sec_ramp)], "CONSTANT")
            gm = ramp(t, mth(t, "SUBTRACT", gmix, mth(t, "MULTIPLY", sr, 0.0)), [(thr - 0.05, 0.0), (thr + 0.05, 1.0)])
            thr_node = mth(t, "SUBTRACT", mth(t, "ADD", gmix, mth(t, "MULTIPLY", sr, 0.25)), 0.0)
            gm = ramp(t, thr_node, [(thr - 0.05 + 0.1, 0.0), (thr + 0.05 + 0.1, 1.0)])
        else:
            gm = ramp(t, gmix, [(thr - 0.05, 0.0), (thr + 0.05, 1.0)])
        gb = nd(t, "ShaderNodeBsdfPrincipled", **{"Metallic": 0.2, "Roughness": 0.9})
        gb.inputs["Base Color"].default_value = lin("#1A1F21")
        mxs = nd(t, "ShaderNodeMixShader"); t.links.new(gm.outputs[0], mxs.inputs[0])
        t.links.new(bs.outputs[0], mxs.inputs[1]); t.links.new(gb.outputs[0], mxs.inputs[2]); shader = mxs
    t.links.new(shader.outputs[0], out.inputs["Surface"])
    return m


def make_velvet(name="velvet", hexc="#002935"):
    m = bpy.data.materials.new(name); m.use_nodes = True; t = m.node_tree
    bs = t.nodes["Principled BSDF"]
    bs.inputs["Base Color"].default_value = lin(hexc); bs.inputs["Roughness"].default_value = 0.9
    bs.inputs["Sheen Weight"].default_value = 1.0; bs.inputs["Sheen Roughness"].default_value = 0.35
    bs.inputs["Sheen Tint"].default_value = lin("#3F7F8C")
    tc = nd(t, "ShaderNodeTexCoord"); mp = nd(t, "ShaderNodeMapping"); mp.inputs["Scale"].default_value = (60, 60, 60)
    t.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nz = nd(t, "ShaderNodeTexNoise", **{"Scale": 1.0, "Detail": 6.0}); t.links.new(mp.outputs[0], nz.inputs["Vector"])
    # одна крупная складка по диагонали
    mp2 = nd(t, "ShaderNodeMapping"); mp2.inputs["Scale"].default_value = (0.05, 0.05, 0.05); mp2.inputs["Rotation"].default_value = (0, 0, math.radians(35))
    t.links.new(tc.outputs["Object"], mp2.inputs["Vector"])
    wv = nd(t, "ShaderNodeTexWave", wave_type="BANDS", bands_direction="X", **{"Scale": 1.0, "Distortion": 1.5, "Detail": 1.0}); t.links.new(mp2.outputs[0], wv.inputs["Vector"])
    hh = mth(t, "ADD", mth(t, "MULTIPLY", nz.outputs["Fac"], 0.5), mth(t, "MULTIPLY", wv.outputs["Fac"], 1.5))
    bp = nd(t, "ShaderNodeBump", **{"Strength": 0.4, "Distance": 0.05}); t.links.new(hh.outputs[0], bp.inputs["Height"]); t.links.new(bp.outputs["Normal"], bs.inputs["Normal"])
    return m


PEAK_F, LEFT_F, RIGHT_F = 0.38, 0.60, 0.40


def profile(f, pk=PEAK_F):
    """профиль яркости линии вдоль кадра (доля пика): пик на pk (38 %), слева 60 %, справа 40 %"""
    f = min(max(f, 0.0), 1.0)
    if f <= pk: return LEFT_F + (1 - LEFT_F) * (f / pk)
    return 1 - (1 - RIGHT_F) * (f - pk) / (1 - pk)


def make_emit(name, peak, x0=-25.0, x1=25.0, color="#FFE9C2", prof_x=None, K=1.0, n=21):
    """эмиссия шва, яркость вдоль мирового X по prof_x(x) (доля пика). Диапазон x0..x1 — где задан профиль.
    Камера видит только переднюю грань шва (ядро линии, код <= 240); верхняя/нижняя грани светят сцене,
    но для камеры прозрачны. K — во сколько раз излучение для освещения сцены (вторичные лучи) сильнее видимого ядра."""
    m = bpy.data.materials.new(name); m.use_nodes = True; t = m.node_tree
    for n_ in list(t.nodes): t.nodes.remove(n_)
    tc = nd(t, "ShaderNodeTexCoord"); sep = nd(t, "ShaderNodeSeparateXYZ"); t.links.new(tc.outputs["Object"], sep.inputs[0])
    fx = maprange(t, sep.outputs[0], x0, x1, 0.0, 1.0, True)
    prof_x = prof_x or (lambda x: profile((x + 25.0) / 50.0))
    r = ramp(t, fx, [(i / (n - 1), prof_x(x0 + (x1 - x0) * i / (n - 1))) for i in range(n)])
    lp = nd(t, "ShaderNodeLightPath"); gm = nd(t, "ShaderNodeNewGeometry")
    kk = mth(t, "ADD", mth(t, "MULTIPLY", lp.outputs["Is Camera Ray"], 1.0 - K), K)
    mul = mth(t, "MULTIPLY", mth(t, "MULTIPLY", r.outputs[0], peak), kk)
    em = nd(t, "ShaderNodeEmission"); em.inputs["Color"].default_value = lin(color); t.links.new(mul.outputs[0], em.inputs["Strength"])
    nsep = nd(t, "ShaderNodeSeparateXYZ"); t.links.new(gm.outputs["Normal"], nsep.inputs[0])
    ny = mth(t, "ABSOLUTE", nsep.outputs[1])
    side = mth(t, "LESS_THAN", ny, 0.5)                       # 1 для верхней/нижней граней
    hide = mth(t, "MULTIPLY", side, lp.outputs["Is Camera Ray"])
    tr = nd(t, "ShaderNodeBsdfTransparent")
    mx = nd(t, "ShaderNodeMixShader"); t.links.new(hide.outputs[0], mx.inputs[0]); t.links.new(em.outputs[0], mx.inputs[1]); t.links.new(tr.outputs[0], mx.inputs[2])
    out = nd(t, "ShaderNodeOutputMaterial"); t.links.new(mx.outputs[0], out.inputs["Surface"]); return m


def make_matte(name, hexc, rough=0.85, metallic=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = lin(hexc); b.inputs["Roughness"].default_value = rough; b.inputs["Metallic"].default_value = metallic
    return m


# ------------------------------------------------------------------ геометрия
def mk(name, verts, faces, mat=None, smooth=True, loc=(0, 0, 0)):
    me = bpy.data.meshes.new(name); me.from_pydata(verts, [], faces); me.update()
    bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.recalc_face_normals(bm, faces=bm.faces); bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = smooth
    o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o); o.location = loc
    if mat: o.data.materials.append(mat)
    return o


def lathe(name, prof, mat, loc, seg=56):
    """тело вращения вокруг Z; prof=[(r,z)...] снизу вверх, крайние точки r=0"""
    v, f, rings = [], [], []
    for r, z in prof:
        if r < 1e-9:
            rings.append([len(v)]); v.append((0, 0, z))
        else:
            rings.append(list(range(len(v), len(v) + seg)))
            v += [(r * math.cos(2 * math.pi * k / seg), r * math.sin(2 * math.pi * k / seg), z) for k in range(seg)]
    for a, b in zip(rings[:-1], rings[1:]):
        for k in range(seg):
            n = (k + 1) % seg
            if len(a) == 1: f.append((a[0], b[n], b[k]))
            elif len(b) == 1: f.append((a[k], a[n], b[0]))
            else: f.append((a[k], a[n], b[n], b[k]))
    return mk(name, v, f, mat, True, loc)


def pin_profile(z0, z1, r=RP, c=FIL, n=3):
    p = [(0, z0), (r - c, z0)]
    for k in range(1, n + 1):
        a = -math.pi / 2 + (math.pi / 2) * k / n; p.append((r - c + c * math.cos(a), z0 + c + c * math.sin(a)))
    for k in range(0, n):
        a = (math.pi / 2) * k / n; p.append((r - c + c * math.cos(a), z1 - c + c * math.sin(a)))
    p += [(r - c, z1), (0, z1)]
    # убрать дубль на стыке дуги и стенки
    out = []
    for q in p:
        if not out or abs(q[0] - out[-1][0]) + abs(q[1] - out[-1][1]) > 1e-9: out.append(q)
    return out


def box_vf(x0, x1, y0, y1, z0, z1):
    v = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return v, f


def box(name, x0, x1, y0, y1, z0, z1, mat=None, bevel=0.0, hidden=False):
    v, f = box_vf(x0, x1, y0, y1, z0, z1); o = mk(name, v, f, mat, False)
    if bevel:
        b = o.modifiers.new("bv", "BEVEL"); b.width = bevel; b.segments = 2; b.limit_method = "ANGLE"
    if hidden: o.hide_render = True; o.hide_viewport = True
    return o


def cutter_cyl(name, cx, cy, z0, z1, r, seg=64):
    v, f = [], []
    ring = lambda z: [(cx + r * math.cos(2 * math.pi * k / seg), cy + r * math.sin(2 * math.pi * k / seg), z) for k in range(seg)]
    v = ring(z0) + ring(z1) + [(cx, cy, z0), (cx, cy, z1)]
    for k in range(seg):
        n = (k + 1) % seg
        f += [(k, n, seg + n, seg + k), (2 * seg, n, k), (seg + k, seg + n, 2 * seg + 1)]
    o = mk(name, v, f, None, True); o.hide_render = True; o.hide_viewport = True
    return o


def merged_cutters(name, centers, y, z0, z1, r, seg=64):
    V, F = [], []
    for cx in centers:
        o = cutter_cyl("tmp", cx, y, z0, z1, r, seg); off = len(V)
        V += [tuple(c) for c in (v.co for v in o.data.vertices)]
        F += [tuple(i + off for i in p.vertices) for p in o.data.polygons]
        bpy.data.objects.remove(o)
    return mk(name, V, F, None, True)


def boolean(obj, cutter, op="DIFFERENCE"):
    cutter.hide_render = True; cutter.hide_viewport = True
    m = obj.modifiers.new("bool", "BOOLEAN"); m.operation = op; m.object = cutter; m.solver = "MANIFOLD"
    return m


def bevel(obj, w=FIL, seg=2):
    b = obj.modifiers.new("bv", "BEVEL"); b.width = w; b.segments = seg; b.limit_method = "ANGLE"; b.angle_limit = math.radians(35)


def spring_obj(name, cx, cy, z0, z1, mat, rng, rad=0.27, wire=0.045, pitch=0.33):
    cu = bpy.data.curves.new(name, "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = wire; cu.bevel_resolution = 2
    sp = cu.splines.new("POLY")
    pts = []; a = 0.0; z = z0
    while z < z1:
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a), z))
        da = 2 * math.pi / 14; a += da
        z += pitch * (1 + rng.uniform(-0.08, 0.08)) / 14
    sp.points.add(len(pts) - 1)
    for p, c in zip(sp.points, pts): p.co = (*c, 1)
    o = bpy.data.objects.new(name, cu); bpy.context.scene.collection.objects.link(o)
    o.data.materials.append(mat); return o


def key_polygon(xs_pins, lens, y_bot, x_lo=-33.0, x_hi=33.0, half=0.45):
    """контур ключа в XZ: верх идёт по -LEN каждого штифта, между ними скос"""
    pts = [(x_lo, y_bot), (x_lo, -lens[0])]
    for x, L in zip(xs_pins, lens): pts += [(x - half, -L), (x + half, -L)]
    pts += [(x_hi, -lens[-1]), (x_hi, y_bot)]
    return pts


def poly_prism(name, pts, y0, y1, mat, bev=0.03):
    n = len(pts); area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    if area < 0: pts = pts[::-1]
    v = [(x, y0, z) for x, z in pts] + [(x, y1, z) for x, z in pts]
    f = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))] + [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    o = mk(name, v, f, mat, False)
    if bev: bevel(o, bev)
    return o


# ------------------------------------------------------------------ сцена
def reset(w, h, samples, exposure=0.0):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene; r = sc.render
    r.engine = "CYCLES"; r.resolution_x, r.resolution_y = w, h; r.resolution_percentage = 100
    cy = sc.cycles; cy.samples = samples; cy.use_denoising = True; cy.device = "CPU"
    cy.denoiser = "OPENIMAGEDENOISE"; cy.max_bounces = 8; cy.diffuse_bounces = 3; cy.glossy_bounces = 6
    cy.sample_clamp_indirect = 8.0; cy.filter_width = 1.2; cy.seed = SEED; cy.use_adaptive_sampling = True; cy.adaptive_threshold = 0.004
    sc.view_settings.view_transform = "AgX"; sc.view_settings.look = "None"; sc.view_settings.exposure = exposure
    sc.display_settings.display_device = "sRGB"
    sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True
    return sc


def world_fill(strength, hexc="#002935"):
    b = bpy.context.scene.world.node_tree.nodes["Background"]
    b.inputs["Color"].default_value = lin(hexc); b.inputs["Strength"].default_value = strength


def area_light(name, loc, rot_deg, size, size_y, power, color, spread=180):
    d = bpy.data.lights.new(name, "AREA"); d.shape = "RECTANGLE"; d.size = size; d.size_y = size_y; d.energy = power
    d.color = color[:3]; d.spread = math.radians(spread)
    o = bpy.data.objects.new(name, d); bpy.context.scene.collection.objects.link(o); o.location = loc
    o.rotation_euler = [math.radians(a) for a in rot_deg]; return o


def look_cam(target, dist, yaw, pitch, lens, fstop, focus, W, H, width_u, line_px=None, line_pt=None, lens_scale=20.0, roll=0.0, sensor_mult=1.0):
    """Камера: yaw° вокруг вертикали от нормали к плоскости разреза (камера левее цели), pitch° вниз.
    Реальный объектив lens мм (экв. 36 мм), сцена 1u=5мм: оптика масштабируется (K) для корректной ГРИП.
    line_pt=(x,z) мировая точка, line_px=(fx,fy) куда она должна лечь в кадре (доли от левого/верхнего края)."""
    K = lens_scale
    c = bpy.data.cameras.new("cam"); c.sensor_fit = "HORIZONTAL"; c.sensor_width = 36.0 * K * sensor_mult; c.lens = lens * K
    d = width_u * lens / 36.0
    ya, pi = math.radians(yaw), math.radians(pitch)
    T = Vector(target)
    # направление взгляда: из камеры к цели; камера на -Y, смещена к -X на yaw
    fwd = Vector((math.sin(ya) * math.cos(pi), math.cos(ya) * math.cos(pi), -math.sin(pi))).normalized()
    loc = T - fwd * d
    o = bpy.data.objects.new("cam", c); bpy.context.scene.collection.objects.link(o); o.location = loc
    o.rotation_euler = fwd.to_track_quat("-Z", "Y").to_euler()
    if roll: o.rotation_euler.rotate_axis("Z", math.radians(roll))
    # фокус: глубина вдоль оси
    fp = Vector(focus); c.dof.use_dof = fstop is not None
    if fstop:
        c.dof.focus_distance = abs((fp - loc).dot(fwd))
        # f_blender так, чтобы диаметр апертуры в u = (lens/fstop)/5мм: d_u = lens*K*1e-3/f_b
        c.dof.aperture_fstop = max(0.1, K * lens * 1e-3 / ((lens / fstop) / 5.0))
    bpy.context.scene.camera = o
    if line_pt:
        bpy.context.view_layer.update()
        sc = bpy.context.scene
        for _ in range(8):
            p = world_to_camera_view(sc, o, Vector((line_pt[0], 0.0, line_pt[1])))
            c.shift_x += (p.x - line_px[0]); c.shift_y += (p.y - (1 - line_px[1])) * (H / W)
            bpy.context.view_layer.update()
        p = world_to_camera_view(sc, o, Vector((line_pt[0], 0.0, line_pt[1])))
        print("  cam calib: point at fx=%.4f fy=%.4f (target %.3f, %.3f)" % (p.x, 1 - p.y, line_px[0], line_px[1]))
    return o


def render_png(path):
    sc = bpy.context.scene; r = sc.render
    r.image_settings.file_format = "PNG"; r.image_settings.color_mode = "RGB"; r.image_settings.color_depth = "16"
    if A.crop:
        x0, y0, x1, y1 = [float(v) for v in A.crop.split(",")]
        r.use_border = True; r.use_crop_to_border = True
        r.border_min_x, r.border_max_x, r.border_min_y, r.border_max_y = x0, x1, 1 - y1, 1 - y0
    r.filepath = os.path.abspath(path); bpy.ops.render.render(write_still=True)


# ------------------------------------------------------------------ общий «замок»: секции в плоскости разреза
SEC_GRAPH = [0.7, 1.0, 0.45, 0.9, 0.3, 0.8, 0.55]     # покрытие графитом по 7 секциям (неравномерно)


def materials(velvet="#002935"):
    M = {}
    M["brass"] = make_metal("brass", "#AA8A4C", 0.15, 0.22, 0.3, (0, 0, 1), (90, 90, 2), 0.012,
                            scratch=(0.9, 0.9, 0.045, 0.006), oil=0.16, wear=0.35, brass=True, graphite=0.0)
    M["key"] = make_metal("key", "#6E5428", KEY_R[0], KEY_R[1], 0.5, (1, 0, 0), (25, 25, 25), 0.05,
                          scratch=(0.02, 0.9, 0.9, 0.006), oil=0.12, wear=0.30, wear_rough=0.12, brass=True, per_object=False)
    M["pin"] = make_metal("pin", "#8D9695", 0.13, 0.21, 0.3, (0, 0, 1), (90, 90, 2), 0.012,
                          scratch=(0.9, 0.9, 0.045, 0.006), patina=True, wear=0.0)
    M["body"] = make_metal("body", "#6E7A7B", BODY_R[0], BODY_R[1], 0.8, (1, 0, 0), (1.5, 90, 90), 0.012,
                           scratch=(0.004, 0.45, 0.45, 0.005), graphite=0.18, oil=0.10, sec_ramp=SEC_GRAPH, per_object=False)
    M["spring"] = make_metal("spring", "#59646A", 0.30, 0.42, 0.0, (0, 0, 1), (20, 20, 20), 0.05, patina=False, per_object=True)
    M["ghost"] = make_metal("ghost", "#3C4849", 0.55, 0.7, 0.0, (1, 0, 0), (2.0, 60, 60), 0.05, patina=False, per_object=False)
    M["graphite"] = make_matte("graphite", "#070E11", 0.92, 0.1)
    M["velvet"] = make_velvet("velvet", velvet)
    return M


class Lock:
    """Один ряд: блоки (корпус над швом, сердечник под швом), штифты, пружины, ключ."""

    def __init__(self, M, rng, y_off=0.0, x_off=0.0, ghost=False):
        self.M, self.rng, self.y, self.x, self.ghost = M, rng, y_off, x_off, ghost
        self.mat = dict(M)
        if ghost: self.mat["body"] = self.mat["pin"] = self.mat["brass"] = self.mat["spring"] = self.mat["key"] = M["ghost"]

    def block(self, xs, ids, x0, x1, tag="b", d_len=D_LEN):
        """блок: корпус+сердечник с каналами для штифтов xs (мировые X), ids — индексы в хэш-высотах"""
        M, rng, y = self.mat, self.rng, self.y
        up = box("shell_" + tag, x0, x1, y, y + 2.2, GAP, 8.0, M["body"])
        win = box("win", x0 - 1, x1 + 1, y - 1.5, y + 1.0, WIN_Z, 9.0, None, hidden=True); boolean(up, win)
        ch = merged_cutters("ch", xs, y, 0.0, WIN_Z + 0.2, RP + 0.10); boolean(up, ch); bevel(up)
        dn = box("plug_" + tag, x0, x1, y, y + 2.2, -9.0, -GAP, M["body"])
        pk = box("pocket", x0 - 1, x1 + 1, y - 1.5, y + 1.0, -9.5, PK_Z, None, hidden=True); boolean(dn, pk)
        ch2 = merged_cutters("ch2", xs, y, PK_Z - 0.3, 0.0, RP + 0.10); boolean(dn, ch2); bevel(dn)
        for px, i in zip(xs, ids):
            tilt = rng.uniform(-0.3, 0.3)
            kp = lathe("keypin%02d" % i, pin_profile(-LEN[i], -GAP), M["brass"], (px, y, 0)); kp.rotation_euler[1] = math.radians(tilt)
            dp = lathe("drv%02d" % i, pin_profile(GAP, d_len), M["pin"], (px, y, 0)); dp.rotation_euler[1] = math.radians(tilt)
            spring_obj("sp%02d" % i, px, y, d_len + 0.01, 4.6, M["spring"], rng)

    def sections(self, key=True):
        for k in range(7):
            xs = [PX[5 * k + j] + self.x for j in range(5)]
            self.block(xs, list(range(5 * k, 5 * k + 5)), xs[0] - 0.65, xs[-1] + 0.65, "s%d" % k)
        if key:
            xs_all = [p + self.x for p in PX]
            poly_prism("key", key_polygon(xs_all, LEN, -4.4), self.y + 0.28, self.y + 0.92, self.mat["key"], 0.03)
        return self


def build_seam(x0=-30, x1=30, y0=-0.50, y1=0.4, mat=None, z=GAP * 0.93):
    return box("seam", x0, x1, y0, y1, -z, z, mat)


def spill_lights(peak, color=(1.0, 0.93, 0.80), x_lo=-30, x_hi=30, seg=4.0, y0=-1.6, y1=10.0, f_range=(-25, 25), z=0.0, prof=None):
    prof = prof or profile
    n = int((x_hi - x_lo) / seg)
    for i in range(n):
        xc = x_lo + seg * (i + 0.5)
        p = prof(((xc - f_range[0]) / (f_range[1] - f_range[0])))
        for sgn, nm in ((1, "up"), (-1, "dn")):
            area_light("spill_%s%02d" % (nm, i), (xc, (y0 + y1) / 2, z), (0 if sgn < 0 else 180, 0, 0), seg, y1 - y0, peak * p, color)


def aim(obj, target):
    obj.rotation_euler = (Vector(target) - Vector(obj.location)).to_track_quat("-Z", "Y").to_euler()


def common_lights(P, rim_loc=(-4, 5.0, 7.5), rim_tgt=(-4, 0, 1.5), fill_tgt=(0, 0, 0)):
    rl = area_light("rim", rim_loc, (0, 0, 0), 24, 3, P["rim"], lin("#5FA3B3"), 120); aim(rl, rim_tgt)
    world_fill(P["fill"])
    if P.get("fillL", 0):
        fl = area_light("fillL", (-40, -8.0, 1.5), (0, 0, 0), 16, 16, P["fillL"], lin(P.get("fillL_col", "#8FB4BC")), 120); aim(fl, fill_tgt)


def prof_world(xl, xr, pk_x):
    """профиль линии по мировому X: пик в pk_x, на левом краю xl 60 %, на правом xr 40 %"""
    def f(x):
        if x <= pk_x: return LEFT_F + (1 - LEFT_F) * max(0.0, (x - xl)) / (pk_x - xl)
        return 1 - (1 - RIGHT_F) * (x - pk_x) / (xr - pk_x)
    return f


# ================================================================== S1 (+ широкий вариант для S4)
S1P = dict(seam=2.3, K=24.0, rim=25.0, fill=0.2, fillL=5000.0, fstop=4.0, exposure=0.0, ghost_light=12.0)
import json
S1P.update(json.loads(A.P))


def scene_s1(W, H, samples, P, wide=False):
    sc = reset(W, H, samples, P.get("exposure", 0.0)); M = materials()
    rng = random.Random(SEED)
    Lock(M, rng).sections()
    if P.get("ghost", 1):
        Lock(M, random.Random(SEED + 1), y_off=8.0, x_off=3.55, ghost=True).sections(key=False)
        spill_lights(P["ghost_light"], y0=6.5, y1=11.0)
    if wide:
        # стыки: плоскость разреза продолжается за краями ряда (фон карточек): корпус над швом, сердечник под швом
        for sgn in (-1, 1):
            xa, xb = (24.4, 70.0) if sgn > 0 else (-70.0, -24.4)
            for nm, z0, z1 in (("sideU", GAP, 8.0), ("sideD", -9.0, -GAP)):
                o = box(nm, xa, xb, 0.0, 2.2, z0, z1, M["body"]); bevel(o)
        x0, x1 = -35.0, 35.0
        pf = prof_world(-25.0, 25.0, -6.0)
        def prof_x(x):
            if x < -25: return LEFT_F + (0.35 - LEFT_F) * min(1.0, (-25 - x) / 10.0)
            if x > 25: return RIGHT_F + (0.35 - RIGHT_F) * min(1.0, (x - 25) / 10.0)
            return pf(x)
        mat = make_emit("seam", P["seam"], x0, x1, prof_x=prof_x, K=P["K"])
        build_seam(-70, 70, y0=-0.50, y1=0.4, mat=mat)
    else:
        build_seam(y0=-0.50, y1=0.4, mat=make_emit("seam", P["seam"], K=P["K"]))
    common_lights(P)
    box("velvet", -120, 120, 16.0, 16.2, -40, 40, M["velvet"])
    sm = W / 1920.0 if wide else 1.0
    fx = (384 + 0.38 * 1920) / 2688.0 if wide else 0.38
    look_cam((-6.0, 0, 0), 0, 7.0, 2.5, 100, P["fstop"], (-6.0, 0, 0), W, H, 50.0, line_pt=(-6.0, 0.0), line_px=(fx, 0.38), sensor_mult=sm)
    return sc


# ================================================================== S2 «Разрез»
S2P = dict(seam=2.2, K=5.0, rim=25.0, fill=0.05, fillL=250.0, fstop=45.0, exposure=0.0, ghost_light=12.0)
S2_IDS = list(range(11, 20))          # 9 штифтов; в кадре ~7 (по краям неполные)
PITCH2 = 1.3                          # шаг макро-кадра: 270 px при 208 px/u (ТЗ S2)
S2_FOCUS_K = 3                        # индекс в S2_IDS штифта «3-й слева» (k=2 → ids[3] с учётом неполного слева)


def scene_s2(W, H, samples, P):
    global GAP
    GAP = 0.0125
    sc = reset(W, H, samples, P.get("exposure", 0.0)); M = materials()
    rng = random.Random(SEED + 2)
    xs = [(k - 3) * PITCH2 for k in range(len(S2_IDS))]          # pin k=3 (3-й полный слева) в x=0
    lk = Lock(M, rng)
    lk.block(xs, S2_IDS, xs[0] - 1.2, xs[-1] + 1.2, "s2")
    wu = 1920.0 / 208.0
    f0 = 0.42
    xl, xr = -f0 * wu, (1 - f0) * wu
    build_seam(-12, 12, y0=-0.50, y1=0.4, mat=make_emit("seam", P["seam"], xl, xr, prof_x=prof_world(xl, xr, 0.0), K=P["K"]), z=GAP * 0.93)
    common_lights(P, rim_loc=(-1, 4.0, 4.0), rim_tgt=(-1, 0, 0.6))
    box("velvet", -60, 60, 16.0, 16.2, -40, 40, M["velvet"])
    look_cam((0, 0, 0), 0, 6.5, 2.5, 100, P["fstop"], (0.0, -0.2, 0.0), W, H, wu, line_pt=(0.0, 0.0), line_px=(f0, 0.41))
    return sc


# ================================================================== S3 «Ключ входит»
S3P = dict(seam=0.07, K=24.0, rim=160.0, fill=0.005, fillL=2200.0, keyfill=2000.0, keyfront=700.0, tip2=150.0, fstop=4.0, exposure=0.0, hole=0.15, tip=900.0)
R_PLUG = 2.75
Z_AX = -R_PLUG
X_TIP = -1.7


def key_polygon_s3(xt):
    top, bot = -1.5, -4.0
    pts = [(-70, top), (xt - 0.9, top), (xt, -2.15), (xt, -3.55), (xt - 0.4, bot)]
    for i in range(9):
        xr = xt - 1.0 - 1.3 * i; d = 0.15 + 0.85 * H[5 * (i % 7) + 2]
        pts += [(xr, bot), (xr, bot + d), (xr - 0.9, bot + d), (xr - 0.9, bot)]
    pts += [(-70, bot)]
    return pts


def scene_s3(W, H_, samples, P):
    sc = reset(W, H_, samples, P.get("exposure", 0.0)); M = materials(P.get("velvet", "#00131A"))
    rng = random.Random(SEED + 3)
    body = M["body"]
    up = box("shell_up", 0.0, 90.0, -3.4, 3.4, GAP, 2.8, body); bevel(up)
    dn = box("shell_dn", 0.0, 90.0, -3.4, 3.4, -9.0, -GAP, body)
    bore = cutter_cyl("bore", 0, 0, -1.0, 91.0, R_PLUG + 0.045); bore.rotation_euler[1] = math.pi / 2; bore.location = (0, 0, Z_AX)
    boolean(dn, bore); bevel(dn)
    plug = lathe("plug", pin_profile(0.0, 90.0, r=R_PLUG, c=0.06, n=4), body, (0, 0, Z_AX), seg=128); plug.rotation_euler[1] = math.pi / 2
    slot = box("slot", -0.3, 9.0, -0.34, 0.34, Z_AX - 1.45, Z_AX + 1.45, None, hidden=True); boolean(plug, slot)
    # ключ
    poly_prism("key", key_polygon_s3(X_TIP), -0.2, 0.2, M["key"], 0.04)
    # шов на внешней грани корпуса: только справа от торца, слабый (25-30 % пика S1)
    build_seam(0.0, 90.0, y0=-3.75, y1=-2.9, mat=make_emit("seam", P["seam"], 0.0, 40.0, prof_x=lambda x: 1.0 - 0.45 * min(1.0, x / 40.0), K=P["K"]))
    # скважина изнутри: слабое свечение стенки щели + крошечный источник в устье щели
    wall = box("hole_glow", 0.03, 4.0, 0.33, 0.335, Z_AX - 1.4, Z_AX + 1.4, make_emit("hole", P["hole"], 0, 4, prof_x=lambda x: 1.0, K=1.0))
    tl = area_light("tip_light", (0.25, 0.0, Z_AX - 0.1), (0, 90, 0), 0.5, 2.3, P["tip"], lin("#FFE9C2"), 140)
    tl2 = area_light("tip_light2", (0.6, -0.9, Z_AX + 0.9), (0, 0, 0), 1.0, 1.0, P.get("tip2", 0), lin("#FFE9C2"), 140); aim(tl2, (-1.7, 0, Z_AX + 0.5))
    common_lights(P, rim_loc=(-10, 6.0, 4.5), rim_tgt=(-8, 0, -1.5), fill_tgt=(-3, 0, -2.5))
    if P.get("keyfill", 0):
        kf = area_light("keyfill", (-18, 1.5, 9.0), (0, 0, 0), 24, 3, P["keyfill"], (1.0, 0.90, 0.78), 100); aim(kf, (-10, 0, -1.5))
    if P.get("keyfront", 0):
        kq = area_light("keyfront", (-14, -22.0, 1.0), (0, 0, 0), 30, 5, P["keyfront"], (1.0, 0.98, 0.95), 110); aim(kq, (-14, 0, -2.75))
    box("velvet", -120, 120, 18.0, 18.2, -40, 40, M["velvet"])
    look_cam((0, 0, Z_AX), 0, 22.0, 2.0, 85, P["fstop"], (X_TIP, 0, Z_AX), W, H_, 52.0, line_pt=(0.0, Z_AX), line_px=(0.50, 0.655))
    return sc


# ================================================================== постобработка: 16 бит -> 8 бит + зерно (дизеринг)
def load16(path):
    img = bpy.data.images.load(os.path.abspath(path)); img.colorspace_settings.name = "Non-Color"
    w, h = img.size; a = np.empty(w * h * 4, dtype=np.float32); img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    return a.reshape(h, w, 4)[::-1, :, :3]            # Blender хранит снизу вверх


def to8(arr, seed=SEED, grain=1.0):
    """треугольный дизеринг ±1 LSB: гасит бэндинг тёмных градиентов на LED"""
    rng = np.random.default_rng(seed)
    n = (rng.random(arr.shape) + rng.random(arr.shape) - 1.0) * grain
    return Image.fromarray(np.clip(np.rint(arr * 255.0 + n), 0, 255).astype(np.uint8), "RGB")


def finalize(src16, dst):
    im = to8(load16(src16)); im.save(dst, optimize=True); return im


def tweak(P_base, name):
    P = dict(P_base); P.update(json.loads(A.P)); return P


def run_blender(name, builder, W, H_, samples, P, out_name, **kw):
    path16 = os.path.join(A.scratch, name + "_16.png")
    builder(int(W * A.scale), int(H_ * A.scale), samples, P, **kw) if kw else builder(int(W * A.scale), int(H_ * A.scale), samples, P)
    render_png(path16)
    return finalize(path16, os.path.join(A.out, out_name + A.tag + ".png")) if A.out else None


# ================================================================== S4: карточка на ВРЕМЕННОМ шрифте Inter
FONT_DIR = "/usr/share/fonts/opentype/inter"
TXT, TXT_DIM = (0xDC, 0xD7, 0xCD), (0xAF, 0xAB, 0xA3)
NB = " "


def F(weight, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, "Inter-%s.otf" % weight), int(round(size * SS)), layout_engine=ImageFont.Layout.RAQM)


SS = 4                                        # суперсэмплинг текста


def tw(font, s):
    return font.getlength(s) / SS


def nbsp_fix(s):
    """неразрывный пробел после предлогов/союзов из 1–2 букв и перед тире"""
    import re
    s = re.sub(r"\b(\w{1,2}) ", lambda m: m.group(1) + NB, s)
    return s.replace(" —", NB + "—")


def wrap(text, font, width, hyphen=True):
    """перенос по пробелам (неразрывные не рвём) и после дефиса составной фамилии; возвращает строки"""
    toks = []
    for w in text.split(" "):
        if hyphen and "-" in w:
            parts = w.split("-"); toks += [p + "-" for p in parts[:-1]] + [parts[-1]]
            toks_join = True
        else:
            toks.append(w)
    # склейка: токены после дефиса не пробелом; реализуем по признаку конца на '-'
    lines, cur = [], ""
    for t in toks:
        glue = "" if cur.endswith("-") or cur == "" else " "
        trial = cur + glue + t
        if tw(font, trial) <= width or cur == "": cur = trial
        else: lines.append(cur); cur = t
    if cur: lines.append(cur)
    return [l.replace(NB, " ") if False else l for l in lines]


def card_layout(name, company, nom, width, sizes=(34.0, 22.5, 15.0), min_name=27.0):
    """Правило карточки: линия — ось. Имя растёт ВВЕРХ от линии (до 2 строк), компания и номинация — ВНИЗ.
    Имя: 34 px (модульная шкала ×1.5: 34 / 22.5 / 15), при длинной фамилии уменьшается до самого длинного слова, но не ниже min_name."""
    sn, sc_, sno = sizes
    name = nbsp_fix(name); company = nbsp_fix(company); nom = nbsp_fix(nom)
    # самый длинный неразрывный кусок имени должен влезть
    chunks = [c for w in name.split(" ") for c in (w.split("-")[:-1] and [p + "-" for p in w.split("-")[:-1]] + [w.split("-")[-1]] or [w])]
    while sn > min_name and max(tw(F("Medium", sn), c) for c in chunks) > width: sn -= 0.5
    fn, fc, fo = F("Medium", sn), F("Medium", sc_), F("Regular", sno)
    return dict(sn=sn, name=wrap(name, fn, width), company=wrap(company, fc, width), nom=wrap(nom, fo, width),
                fn=fn, fc=fc, fo=fo, sizes=(sn, sc_, sno))


def draw_card(layer_rgba, x0, line_y, lay, H_sq=384):
    """x0 — левый край блока, line_y — y линии; всё в px кадра 1:4. Рисуем в суперсэмпле на отдельном слое."""
    d = ImageDraw.Draw(layer_rgba)
    sn, sc_, sno = lay["sizes"]
    lead_n, lead_c, lead_o = 1.04, 1.18, 1.22
    # имя: нижняя кромка букв на 4 % высоты выше линии; строки растут вверх
    base = line_y - 0.04 * H_sq
    nl = lay["name"]
    for i, line in enumerate(reversed(nl)):
        y_bl = base - i * sn * lead_n
        d.text((x0 * SS, y_bl * SS), line.replace(NB, " "), font=lay["fn"], fill=TXT + (255,), anchor="ls")
    # компания: верх первой строки на 8 % ниже линии (y 46 %)
    y = line_y + 0.08 * H_sq
    for i, line in enumerate(lay["company"]):
        d.text((x0 * SS, (y + sc_ * 0.73 + i * sc_ * lead_c) * SS), line.replace(NB, " "), font=lay["fc"], fill=TXT + (255,), anchor="ls")
    y += len(lay["company"]) * sc_ * lead_c + sc_ * 0.55
    for i, line in enumerate(lay["nom"]):
        d.text((x0 * SS, (y + sno * 0.73 + i * sno * lead_o) * SS), line.replace(NB, " "), font=lay["fo"], fill=TXT_DIM + (255,), anchor="ls")
    end_y = y + len(lay["nom"]) * sno * lead_o
    return end_y


def compose_s4(wide_png, out_path):
    base = Image.open(wide_png).convert("RGB")
    W, Hh = base.size
    assert (W, Hh) == (2688, 384), (W, Hh)
    line_y = 0.38 * 384
    by_id = {r["id"]: r for r in rows}
    cards = [("left", "l01_hotels1"), ("right", "l14_culture4")]
    layer = Image.new("RGBA", (W * SS, Hh * SS), (0, 0, 0, 0))
    info = []
    for side, rid in cards:
        r = by_id[rid]
        sq0 = 0 if side == "left" else 2304
        x0 = sq0 + 0.10 * 384
        lay = card_layout(r["name"], r["company"], r["nomination"], 0.82 * 384)
        end_y = draw_card(layer, x0, line_y, lay)
        info.append(dict(side=side, id=rid, name=r["name"], company=r["company"], nom=r["nomination"], sizes=lay["sizes"],
                         name_lines=lay["name"], company_lines=lay["company"], nom_lines=lay["nom"], end_y=end_y, x0=x0,
                         widths=[tw(lay["fn"], l) for l in lay["name"]] + [tw(lay["fc"], l) for l in lay["company"]] + [tw(lay["fo"], l) for l in lay["nom"]]))
    text = layer.resize((W, Hh), Image.LANCZOS)
    comp = base.convert("RGBA"); comp.alpha_composite(text); comp = comp.convert("RGB")
    # мёртвые зоны стыков (12 px канвы = 3 px при 1/4): x 383..385 и 2303..2305
    px = comp.load()
    for x in (383, 384, 385, 2303, 2304, 2305):
        for y in range(Hh): px[x, y] = (0, 0, 0)
    # подпись-схема под кадром (вне экранов)
    band = 46
    out = Image.new("RGB", (W, Hh + band), (10, 12, 13)); out.paste(comp, (0, 0))
    d = ImageDraw.Draw(out)
    f1 = ImageFont.truetype(os.path.join(FONT_DIR, "Inter-Regular.otf"), 12)
    cap1 = "Схема стыка в масштабе 1:4. Слева экран 1536×1536 (типичная карточка), в центре 7680×1536 (кадр S1), справа 1536×1536 (худший случай из CSV: самое длинное имя и самая длинная компания, id l14). Чёрные полосы — мёртвые зоны стыков, 12 px канвы."
    cap2 = "Шрифт Inter — ВРЕМЕННО, выбор шрифта за владельцем. Линия идёт сквозь оба стыка на той же высоте 38 %; текст набран графикой поверх рендера, не светится."
    d.text((12, Hh + 8), cap1, font=f1, fill=(150, 148, 142)); d.text((12, Hh + 26), cap2, font=f1, fill=(150, 148, 142))
    out.save(out_path, optimize=True)
    comp.save(out_path.replace(".png", "_nocaption.png"), optimize=True)
    return info, base, comp


# ================================================================== замеры и лист
def tone_stats(path):
    im = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
    lum = im @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    h, w = lum.shape
    d = {}
    d["size"] = "%dx%d" % (w, h)
    d["dark<40"] = float(np.mean(lum < 40) * 100); d["mid40-150"] = float(np.mean((lum >= 40) & (lum < 150)) * 100)
    d["light150-235"] = float(np.mean((lum >= 150) & (lum <= 235)) * 100); d["peak>235"] = float(np.mean(lum > 235) * 100)
    d["over>250"] = float(np.mean(lum > 250) * 100); d["max_lum"] = float(lum.max())
    d["warm_R-B>=40"] = float(np.mean((im[..., 0] - im[..., 2]) >= 40) * 100)
    d["top25_mean"] = float(lum[: int(h * 0.25)].mean()); d["top25_p95"] = float(np.percentile(lum[: int(h * 0.25)], 95))
    # положение самого светлого 1 % пикселей
    thr = np.percentile(lum, 99); ys, xs = np.nonzero(lum >= thr)
    d["p99_thr"] = float(thr); d["p99_y_pct"] = [float(np.percentile(ys, 1) / h * 100), float(np.percentile(ys, 99) / h * 100)]
    d["p99_x_centroid_pct"] = float(xs.mean() / w * 100)
    d["p99_in_band_34_42"] = float(np.mean((ys / h >= 0.34) & (ys / h <= 0.42)) * 100)
    # линия: яркость вдоль кадра в полосе y 36-40 %
    band = lum[int(h * 0.36): int(h * 0.40)].max(axis=0)
    cols = np.array_split(band, 20); d["line_by_20"] = [float(c.max()) for c in cols]
    return d


def make_sheet(paths, out_path):
    labels = {"s1": "S1 Линия среза", "s2": "S2 Разрез", "s3": "S3 Ключ входит", "s4": "S4 Карточка (схема стыка)"}
    rows_ = []
    for key, p in paths:
        im = Image.open(p).convert("RGB"); w, h = im.size
        if key == "s4": im = im.crop((0, 0, w, 384)); w, h = im.size
        col = im.resize((1920, int(round(h * 1920 / w))), Image.LANCZOS)
        g = im.convert("L").resize((480, int(round(h * 480 / w))), Image.LANCZOS).convert("RGB")
        t = im.resize((240, int(round(h * 240 / w))), Image.LANCZOS)
        t = t.resize((240, t.size[1]), Image.LANCZOS)
        rows_.append((key, col, g, t))
    f = ImageFont.truetype(os.path.join(FONT_DIR, "Inter-Regular.otf"), 14)
    Wt = 1920 + 24 + 480 + 24
    Ht = sum(max(c.size[1], 20 + g.size[1] + 16 + t.size[1] + 12) + 34 for _, c, g, t in rows_) + 12
    sheet = Image.new("RGB", (Wt, Ht), (16, 18, 19)); d = ImageDraw.Draw(sheet); y = 8
    for key, col, g, t in rows_:
        d.text((8, y), labels[key], font=f, fill=(170, 168, 160)); y += 24
        sheet.paste(col, (0, y)); sheet.paste(g, (1920 + 24, y)); sheet.paste(t, (1920 + 24, y + g.size[1] + 10))
        d.text((1920 + 24 + 250, y + g.size[1] + 10 + 14), "1/8 (240 px)", font=f, fill=(120, 118, 112))
        y += max(col.size[1], g.size[1] + 10 + t.size[1]) + 10
    sheet.crop((0, 0, Wt, y)).save(out_path, optimize=True)


# ================================================================== запуск
def main():
    os.makedirs(A.out, exist_ok=True)
    stats = {}
    out = lambda n: os.path.join(A.out, n + A.tag + ".png")
    if "s1" in A.only:
        run_blender("s1", lambda W, H_, s, P: scene_s1(W, H_, s, P), 1920, 384, A.samples, tweak(S1P, "s1"), "s1_line")
    if "s1hi" in A.only:
        run_blender("s1hi", lambda W, H_, s, P: scene_s1(W, H_, s, P), 3840, 768, A.hi_samples, tweak(S1P, "s1"), "s1_line_hires")
    if "s2" in A.only:
        run_blender("s2", lambda W, H_, s, P: scene_s2(W, H_, s, P), 1920, 384, A.samples, tweak(S2P, "s2"), "s2_cut")
    if "s3" in A.only:
        run_blender("s3", lambda W, H_, s, P: scene_s3(W, H_, s, P), 1920, 384, A.samples, tweak(S3P, "s3"), "s3_enter")
    if "s4" in A.only:
        wide = os.path.join(A.scratch, "s4_wide.png")
        run_blender("s4w", lambda W, H_, s, P: scene_s1(W, H_, s, P, wide=True), 2688, 384, A.samples, tweak(S1P, "s1"), "_s4_wide_raw")
        info, base, comp = compose_s4(out("_s4_wide_raw"), out("s4_card"))
        json.dump(info, open(os.path.join(A.out, "_s4_layout.json"), "w"), ensure_ascii=False, indent=1, default=lambda o: list(o))
    if "sheet" in A.only:
        ps = [(k, out(n)) for k, n in (("s1", "s1_line"), ("s2", "s2_cut"), ("s3", "s3_enter"), ("s4", "s4_card")) if os.path.exists(out(n))]
        make_sheet(ps, out("_sheet"))
    if "stats" in A.only:
        for n in ("s1_line", "s1_line_hires", "s2_cut", "s3_enter", "s4_card_nocaption"):
            if os.path.exists(out(n)): stats[n] = tone_stats(out(n))
        json.dump(stats, open(os.path.join(A.out, "_stats.json"), "w"), indent=1)
        print(json.dumps(stats, indent=1))


if __name__ == "__main__" and not any(k == "test" for k in A.only):
    main()
