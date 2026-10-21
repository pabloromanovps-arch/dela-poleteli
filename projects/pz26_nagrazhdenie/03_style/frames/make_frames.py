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
GAP = 0.03                     # полу-зазор шва, u (0.06 u = 0.3 мм)
FIL = 0.03                     # фаска/скругление торцов (0.15 мм)
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
        vo = nd(t, "ShaderNodeTexVoronoi", feature="DISTANCE_TO_EDGE", **{"Scale": 1.0})
        t.links.new(mapping(scratch[:3]).outputs[0], vo.inputs["Vector"])
        sc_mask = ramp(t, vo.outputs["Distance"], [(0.0, 1.0), (scratch[3], 0.0)])
    # 3. полированные площадки износа
    wr_mask = None
    if wear > 0:
        wn = nd(t, "ShaderNodeTexNoise", **{"Scale": 1.0, "Detail": 3.0, "Roughness": 0.6}); wsc = (0.9, 0.9, 0.9) if not brass else (0.7, 0.7, 0.7)
        t.links.new(mapping(wsc).outputs[0], wn.inputs["Vector"])
        wr_mask = ramp(t, wn.outputs["Fac"], [(1 - wear - 0.04, 0.0), (1 - wear + 0.04, 1.0)])
    # roughness
    r0 = maprange(t, nz.outputs["Fac"], 0.35, 0.65, rough_lo, rough_hi, True)
    rough_out = r0.outputs[0]
    if sc_mask is not None:
        rs = mth(t, "SUBTRACT", rough_out, mth(t, "MULTIPLY", sc_mask, 0.12)); rough_out = rs.outputs[0]
    if wr_mask is not None:
        rm = nd(t, "ShaderNodeMix", data_type="FLOAT"); t.links.new(wr_mask.outputs[0], rm.inputs[0]); t.links.new(rough_out, rm.inputs[2]); rm.inputs[3].default_value = wear_rough; rough_out = rm.outputs[0]
    # bump
    hmix = mth(t, "SUBTRACT", nz.outputs["Fac"], mth(t, "MULTIPLY", sc_mask, 0.6) if sc_mask is not None else 0.0)
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


def make_velvet(name="velvet"):
    m = bpy.data.materials.new(name); m.use_nodes = True; t = m.node_tree
    bs = t.nodes["Principled BSDF"]
    bs.inputs["Base Color"].default_value = lin("#002935"); bs.inputs["Roughness"].default_value = 0.9
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


def profile(f):
    """профиль яркости линии вдоль кадра (доля пика): пик 38 %, слева 60 %, справа 40 %"""
    if f <= PEAK_F: return LEFT_F + (1 - LEFT_F) * (f / PEAK_F)
    return 1 - (1 - RIGHT_F) * (f - PEAK_F) / (1 - PEAK_F) if f <= 1 else RIGHT_F


def make_emit(name, peak, x0=-25.0, x1=25.0, color="#FFE9C2", prof=None):
    """эмиссия шва с яркостью вдоль X по профилю; x0..x1 — ширина кадра в мировых u."""
    m = bpy.data.materials.new(name); m.use_nodes = True; t = m.node_tree
    for n in list(t.nodes): t.nodes.remove(n)
    tc = nd(t, "ShaderNodeTexCoord"); sep = nd(t, "ShaderNodeSeparateXYZ"); t.links.new(tc.outputs["Object"], sep.inputs[0])
    fx = maprange(t, sep.outputs[0], x0, x1, 0.0, 1.0, True)
    prof = prof or profile
    r = ramp(t, fx, [(i / 10, prof(i / 10)) for i in range(11)])
    mul = mth(t, "MULTIPLY", r.outputs[0], peak)
    em = nd(t, "ShaderNodeEmission"); em.inputs["Color"].default_value = lin(color); t.links.new(mul.outputs[0], em.inputs["Strength"])
    out = nd(t, "ShaderNodeOutputMaterial"); t.links.new(em.outputs[0], out.inputs["Surface"]); return m


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


def look_cam(target, dist, yaw, pitch, lens, fstop, focus, W, H, width_u, line_px=None, line_pt=None, lens_scale=20.0, roll=0.0):
    """Камера: yaw° вокруг вертикали от нормали к плоскости разреза (камера левее цели), pitch° вниз.
    Реальный объектив lens мм (экв. 36 мм), сцена 1u=5мм: оптика масштабируется (K) для корректной ГРИП.
    line_pt=(x,z) мировая точка, line_px=(fx,fy) куда она должна лечь в кадре (доли от левого/верхнего края)."""
    K = lens_scale
    c = bpy.data.cameras.new("cam"); c.sensor_fit = "HORIZONTAL"; c.sensor_width = 36.0 * K; c.lens = lens * K
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
    r.filepath = path; bpy.ops.render.render(write_still=True)


# ------------------------------------------------------------------ общий «замок»: секции в плоскости разреза
SEC_GRAPH = [0.7, 1.0, 0.45, 0.9, 0.3, 0.8, 0.55]     # покрытие графитом по 7 секциям (неравномерно)


def materials(scale="s1"):
    M = {}
    M["brass"] = make_metal("brass", "#8A6A2E", 0.22, 0.38, 0.6, (0, 0, 1), (60, 60, 3), 0.12,
                            scratch=(2.2, 2.2, 0.06, 0.012), oil=0.16, wear=0.35, brass=True, graphite=0.0)
    M["pin"] = make_metal("pin", "#8D9695", 0.18, 0.34, 0.5, (0, 0, 1), (60, 60, 3), 0.12,
                          scratch=(2.0, 2.0, 0.05, 0.010), patina=True, wear=0.0)
    M["body"] = make_metal("body", "#6E7A7B", 0.26, 0.40, 0.8, (1, 0, 0), (2.0, 60, 60), 0.10,
                           scratch=(0.035, 0.7, 0.7, 0.007), graphite=0.18, oil=0.10, sec_ramp=SEC_GRAPH, per_object=False)
    M["spring"] = make_metal("spring", "#8D9695", 0.30, 0.42, 0.0, (0, 0, 1), (20, 20, 20), 0.05, patina=False, per_object=True)
    M["graphite"] = make_matte("graphite", "#070E11", 0.92, 0.1)
    M["velvet"] = make_velvet()
    return M


class Lock:
    """Строит один ряд: секции (корпус над швом, сердечник под швом), штифты, пружины, ключ."""

    def __init__(self, M, rng, y_off=0.0, x_off=0.0, ghost=False):
        self.M, self.rng, self.y, self.x, self.ghost = M, rng, y_off, x_off, ghost

    def sections(self, kmax=7, key=True):
        M, rng = self.M, self.rng
        for k in range(kmax):
            xs = [PX[5 * k + j] + self.x for j in range(5)]
            x0, x1 = xs[0] - 0.65, xs[-1] + 0.65
            # корпус: нижняя полоска с каналами + задняя стенка (окно пружин открыто вверх и вперёд)
            up = box("shell%d" % k, x0, x1, self.y + 0.0, self.y + 2.2, GAP, 8.0, M["body"])
            win = box("win", x0 - 1, x1 + 1, self.y - 1.5, self.y + 1.0, D_LEN + 0.04, 9.0, None, hidden=True); boolean(up, win)
            ch = merged_cutters("ch", xs, self.y, 0.0, 1.5, RP + 0.10); boolean(up, ch); bevel(up)
            dn = box("plug%d" % k, x0, x1, self.y + 0.0, self.y + 2.2, -5.3, -GAP, M["body"])
            pk = box("pocket", x0 - 1, x1 + 1, self.y - 1.5, self.y + 1.0, -4.7, -0.95, None, hidden=True); boolean(dn, pk)
            ch2 = merged_cutters("ch2", xs, self.y, -1.6, 0.0, RP + 0.10); boolean(dn, ch2); bevel(dn)
            for j in range(5):
                i = 5 * k + j; px = xs[j]
                tilt = rng.uniform(-0.3, 0.3)
                L = LEN[i]
                kp = lathe("keypin%02d" % i, pin_profile(-L, -GAP), M["brass"], (px, self.y, 0)); kp.rotation_euler[1] = math.radians(tilt)
                dp = lathe("drv%02d" % i, pin_profile(GAP, D_LEN), M["pin"], (px, self.y, 0)); dp.rotation_euler[1] = math.radians(tilt)
                if not self.ghost or True:
                    spring_obj("sp%02d" % i, px, self.y, D_LEN + 0.01, 4.6, M["spring"], rng)
        # ключ (профиль по хэш-высотам) и ряд ниже
        if key:
            xs_all = [p + self.x for p in PX]
            kpoly = poly_prism("key", key_polygon(xs_all, LEN, -4.4), self.y + 0.28, self.y + 0.92, M["brass"], 0.03)
        return self


def build_seam(x0=-30, x1=30, y0=-0.10, y1=3.0, mat=None):
    return box("seam", x0, x1, y0, y1, -GAP * 0.93, GAP * 0.93, mat)


def spill_lights(peak, color=(1.0, 0.88, 0.70), x_lo=-30, x_hi=30, seg=4.0, y0=-1.6, y1=10.0, f_range=(-25, 25), z=0.0, prof=None):
    prof = prof or profile
    n = int((x_hi - x_lo) / seg)
    for i in range(n):
        xc = x_lo + seg * (i + 0.5)
        f = (xc - f_range[0]) / (f_range[1] - f_range[0])
        p = prof(min(max(f, 0), 1))
        for sgn, nm in ((1, "up"), (-1, "dn")):
            area_light("spill_%s%02d" % (nm, i), (xc, (y0 + y1) / 2, z), (0 if sgn < 0 else 180, 0, 0), seg, y1 - y0, peak * p, color)


# ================================================================== S1
def scene_s1(W, H, samples, P):
    sc = reset(W, H, samples, P.get("exposure", 0.0)); M = materials()
    rng = random.Random(SEED)
    lock = Lock(M, rng).sections()
    ghost = Lock(M, random.Random(SEED + 1), y_off=8.0, x_off=3.55, ghost=True).sections(key=False)
    seam = build_seam(mat=make_emit("seam", P["seam"]))
    spill_lights(P["spill"], y0=P.get("spill_y0", -0.8), y1=P.get("spill_y1", 0.6))
    # холодный контровой сверху-сзади (<=12 % ключевого)
    area_light("rim", (-4, 5.0, 7.5), (-120, 0, 0), 24, 3, P["rim"], lin("#5FA3B3"), 120)
    world_fill(P["fill"])
    # бархат на 80 мм позади
    v = box("velvet", -90, 90, 16.0, 16.2, -40, 40, M["velvet"])
    focus = (-6.0, 0, 0)
    look_cam((-6.0, 0, 0), 50 * 0.0 + 1, 7.0, 2.5, 100, P["fstop"], focus, W, H, 50.0 * 1.0, line_pt=(-6.0, 0.0), line_px=(0.38 + 0.0, 0.38))
    return sc



import json
S1P = dict(seam=6.0, spill=300.0, rim=60.0, fill=0.03, fstop=4.0, exposure=0.0)
S1P.update(json.loads(A.P))


def run_s1(path, W, H, samples, P=S1P):
    scene_s1(W, H, samples, P); render_png(path)


if __name__ == "__main__" and "test" in A.only:
    run_s1(os.path.join(A.scratch, "t_s1.png"), int(1920 * A.scale), int(384 * A.scale), A.samples)
