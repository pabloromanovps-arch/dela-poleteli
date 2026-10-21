"""Серые эскизы композиций 5:1 (1920x384) для pz26_nagrazhdenie. Стадия 03, ДО цвета/анимации/шрифтов.

Только тон: «глиняный» серый материал, один солнечный свет (+ тонкая эмиссия «линии» там, где это сюжет).
Запуск (любой из вариантов):
  blender -b -P make_thumbs.py -- [--only a1 a2 ...] [--samples 40]
  python make_thumbs.py [--only ...]        # если установлен модуль bpy (pip install bpy)
Кадры: a1..a6 («Линия среза»), b («Сквозь»), c («Эталон»). Высоты штифтов = md5(id) из data/laureates.csv,
НЕ рейтинг и НЕ номер. Выход: рядом со скриптом, <имя>.png.
"""
import argparse, csv, hashlib, math, os, sys
import bpy, bmesh
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(os.path.dirname(os.path.dirname(HERE)), "data", "laureates.csv")
ap = argparse.ArgumentParser()
ap.add_argument("--only", nargs="*"); ap.add_argument("--samples", type=int, default=40)
ap.add_argument("--w", type=int, default=1920); ap.add_argument("--h", type=int, default=384)
ap.add_argument("--out", default=HERE); ap.add_argument("--tag", default="")
A = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])

# ---------- данные: хэш от id -> 0..1 (порядок и рейтинг не участвуют) ----------
IDS = [r["id"] for r in csv.DictReader(open(CSV, encoding="utf-8"))]
assert len(IDS) == 35, len(IDS)
H = [int(hashlib.md5(i.encode()).hexdigest()[:8], 16) / 2**32 for i in IDS]

# ---------- базовые помощники ----------
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    r = sc.render; r.engine = "CYCLES"; r.resolution_x, r.resolution_y = A.w, A.h; r.resolution_percentage = 100
    sc.cycles.samples = A.samples; sc.cycles.use_denoising = True; sc.cycles.device = "CPU"
    sc.cycles.max_bounces = 5; sc.cycles.preview_samples = 8
    try: sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception: pass
    sc.view_settings.view_transform = "Standard"
    try: sc.view_settings.look = "None"
    except Exception: pass
    sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0, 0, 0, 1)
    return sc

def clay(name, v, rough=0.82):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (v, v, v, 1); b.inputs["Roughness"].default_value = rough
    for k in ("Specular IOR Level", "Specular"):
        if k in b.inputs: b.inputs[k].default_value = 0.25
    return m

def glow(name, v):
    m = bpy.data.materials.new(name); m.use_nodes = True; t = m.node_tree
    for n in list(t.nodes): t.nodes.remove(n)
    e = t.nodes.new("ShaderNodeEmission"); e.inputs["Color"].default_value = (1, 1, 1, 1); e.inputs["Strength"].default_value = v
    o = t.nodes.new("ShaderNodeOutputMaterial"); t.links.new(e.outputs[0], o.inputs["Surface"]); return m

def glow_ramp(name, stops, axis="Z", scale=1.0, offset=0.0):
    """эмиссия с градиентом по оси объекта (серые значения); stops=[(pos, value)]"""
    m = bpy.data.materials.new(name); m.use_nodes = True; t = m.node_tree
    for n in list(t.nodes): t.nodes.remove(n)
    tc = t.nodes.new("ShaderNodeTexCoord"); sp = t.nodes.new("ShaderNodeSeparateXYZ")
    mp = t.nodes.new("ShaderNodeMapRange"); mp.inputs["From Min"].default_value = -scale; mp.inputs["From Max"].default_value = scale
    mp.inputs["To Min"].default_value = 0; mp.inputs["To Max"].default_value = 1
    cr = t.nodes.new("ShaderNodeValToRGB"); cr.color_ramp.interpolation = "LINEAR"
    el = cr.color_ramp.elements
    while len(el) < len(stops): el.new(0.5)
    for e, (p, v) in zip(el, stops): e.position = p; e.color = (v, v, v, 1)
    em = t.nodes.new("ShaderNodeEmission"); o = t.nodes.new("ShaderNodeOutputMaterial")
    t.links.new(tc.outputs["Object"], sp.inputs[0]); t.links.new(sp.outputs[{"X": 0, "Y": 1, "Z": 2}[axis]], mp.inputs["Value"])
    t.links.new(mp.outputs["Result"], cr.inputs["Fac"]); t.links.new(cr.outputs["Color"], em.inputs["Color"])
    t.links.new(em.outputs[0], o.inputs["Surface"]); return m

def finish(me):
    bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.recalc_face_normals(bm, faces=bm.faces); bm.to_mesh(me); bm.free()

def mk(name, verts, faces, mat, smooth=()):
    me = bpy.data.meshes.new(name); me.from_pydata(verts, [], faces); me.update(); finish(me)
    for i in smooth: me.polygons[i].use_smooth = True
    o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
    if mat: o.data.materials.append(mat)
    return o

def box_vf(x0, x1, y0, y1, z0, z1):
    v = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return v, f

def box(name, x0, x1, y0, y1, z0, z1, mat, bevel=0.0):
    v, f = box_vf(x0, x1, y0, y1, z0, z1); o = mk(name, v, f, mat)
    if bevel:
        b = o.modifiers.new("bv", "BEVEL"); b.width = bevel; b.segments = 2; b.limit_method = "ANGLE"
    return o

def cyl_vf(cx, cy, z0, z1, r, seg=28, split=False, axis="Z"):
    """цилиндр; split=True: у торцов свои вершины (для гладких боков)"""
    v, f = [], []
    ring = lambda z: [(cx + r * math.cos(2 * math.pi * k / seg), cy + r * math.sin(2 * math.pi * k / seg), z) for k in range(seg)]
    if not split:
        v = ring(z0) + ring(z1) + [(cx, cy, z0), (cx, cy, z1)]
        for k in range(seg):
            n = (k + 1) % seg
            f += [(k, n, seg + n, seg + k), (n, k, 2 * seg, 2 * seg) if False else (2 * seg, n, k), (seg + k, seg + n, 2 * seg + 1)]
        return v, f, []
    v = ring(z0) + ring(z1) + ring(z0) + ring(z1) + [(cx, cy, z0), (cx, cy, z1)]
    for k in range(seg):
        n = (k + 1) % seg
        f.append((k, n, seg + n, seg + k))
    sm = list(range(seg))
    for k in range(seg):
        n = (k + 1) % seg
        f.append((4 * seg, 2 * seg + n, 2 * seg + k)); f.append((4 * seg + 1, 3 * seg + k, 3 * seg + n))
    return v, f, sm

def merge(parts):
    V, F = [], []
    for v, f in parts:
        o = len(V); V += v; F += [tuple(i + o for i in fc) for fc in f]
    return V, F

def cylinder(name, cx, cy, z0, z1, r, mat, seg=28):
    v, f, sm = cyl_vf(cx, cy, z0, z1, r, seg, split=True); return mk(name, v, f, mat, sm)

def poly_prism(name, pts, y0, y1, mat, bevel=0.0):
    """многоугольник в плоскости XZ, выдавлен по Y"""
    n = len(pts); area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    if area < 0: pts = pts[::-1]
    v = [(x, y0, z) for x, z in pts] + [(x, y1, z) for x, z in pts]
    f = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))] + [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    o = mk(name, v, f, mat)
    if bevel:
        b = o.modifiers.new("bv", "BEVEL"); b.width = bevel; b.segments = 2; b.limit_method = "ANGLE"
    return o

def prism_x(name, prof, x0, x1, mat):
    """профиль (y,z) выдавлен по X"""
    n = len(prof)
    v = [(x0, y, z) for y, z in prof] + [(x1, y, z) for y, z in prof]
    f = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))] + [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    return mk(name, v, f, mat)

def bool_diff(obj, cutter, solver="MANIFOLD"):
    cutter.hide_render = True; cutter.hide_viewport = True
    m = obj.modifiers.new("cut", "BOOLEAN"); m.operation = "DIFFERENCE"; m.object = cutter
    try: m.solver = solver
    except Exception: m.solver = "EXACT"
    return m

def sun(direction, strength, angle_deg=6):
    d = bpy.data.lights.new("sun", "SUN"); d.energy = strength; d.angle = math.radians(angle_deg)
    o = bpy.data.objects.new("sun", d); bpy.context.scene.collection.objects.link(o)
    o.rotation_euler = Vector(direction).normalized().to_track_quat("-Z", "Y").to_euler(); return o

def spot(loc, target, power, cone_deg=70, blend=1.0, soft=2.5):
    d = bpy.data.lights.new("spot", "SPOT"); d.energy = power; d.spot_size = math.radians(cone_deg); d.spot_blend = blend; d.shadow_soft_size = soft
    o = bpy.data.objects.new("spot", d); bpy.context.scene.collection.objects.link(o); o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler(); return o

def cam_ortho(width, loc, rot_deg=(90, 0, 0)):
    c = bpy.data.cameras.new("cam"); c.type = "ORTHO"; c.ortho_scale = width
    o = bpy.data.objects.new("cam", c); bpy.context.scene.collection.objects.link(o)
    o.location = loc; o.rotation_euler = [math.radians(a) for a in rot_deg]; bpy.context.scene.camera = o; return o

def cam_persp(loc, target, lens=50):
    c = bpy.data.cameras.new("cam"); c.lens = lens
    o = bpy.data.objects.new("cam", c); bpy.context.scene.collection.objects.link(o); o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler(); bpy.context.scene.camera = o; return o

def render(name):
    sc = bpy.context.scene; r = sc.render; r.image_settings.file_format = "PNG"; r.image_settings.color_mode = "RGB"
    r.filepath = os.path.join(A.out, name + A.tag + ".png"); bpy.ops.render.render(write_still=True); print("->", r.filepath)

# =====================================================================================
# A. «Линия среза»: разрез цилиндра вдоль экрана. z=0 — линия среза, камера смотрит +Y.
# =====================================================================================
PITCH, SEC_GAP = 1.1, 1.6
PX = []
x = 0.0
for i in range(35):
    if i and i % 5 == 0: x += SEC_GAP
    PX.append(x); x += PITCH
PX = [p - (PX[0] + PX[-1]) / 2 for p in PX]           # центрируем: ±23.1
GAPH = 0.08                                            # полу-зазор линии среза
FLOOR = -3.7                                           # упор штифтов в покое
LEN = [1.0 + 1.9 * h for h in H]                       # длина нижнего штифта = хэш id
CAMZ = -1.2                                            # линия среза на ~38% высоты кадра сверху

def lock_section(lift, key_pts=None, strip=None, opened=0.0, rail_from=None, name_suffix=""):
    """lift[i] 0..1; key_pts — полигон ключа (XZ); strip=(x0,x1) — светящаяся линия; opened — раздвиг половин"""
    M = dict(shell=clay("shell", 0.05), plug=clay("plug", 0.15), keypin=clay("keypin", 0.40), drv=clay("drv", 0.30),
             spring=clay("spring", 0.25), key=clay("key", 0.34), rail=clay("rail", 0.12))
    up, dn = [], []
    # корпус (над линией) и сердечник (под ней): каналы — полуцилиндры в плоскости разреза
    cutters = merge([cyl_vf(px, 0, -1.2, 4.6, 0.46, 20)[:2] for px in PX])
    cut = mk("cut_ch", *cutters, None)
    shell = box("shell", -30, 30, 0.0, 4, GAPH, 8, M["shell"]); bool_diff(shell, cut); up.append(shell)
    plug = box("plug", -30, 30, 0.0, 4, -9, -GAPH, M["plug"])
    pocket = box("pocket", -31, 31, -1, 1.25, -4.6, -0.95, None); pocket.hide_render = True
    bool_diff(plug, pocket); bool_diff(plug, cut); dn.append(plug)
    # штифты и пружины
    helix = bpy.data.curves.new("springs", "CURVE"); helix.dimensions = "3D"; helix.bevel_depth = 0.05; helix.bevel_resolution = 2
    for i, px in enumerate(PX):
        join = (1 - lift[i]) * (FLOOR + LEN[i])
        bottom = FLOOR + lift[i] * (-LEN[i] - FLOOR)
        kp = cylinder("kp%02d" % i, px, 0, bottom, join - GAPH, 0.36, M["keypin"]); dn.append(kp)
        dtop = join + 2.1
        dp = cylinder("dp%02d" % i, px, 0, join + GAPH, dtop, 0.36, M["drv"]); up.append(dp)
        sp = helix.splines.new("POLY"); n = 56; sp.points.add(n - 1)
        for k in range(n):
            t = k / (n - 1); a = t * 2 * math.pi * 7
            sp.points[k].co = (px + 0.27 * math.cos(a), 0.27 * math.sin(a), dtop + 0.02 + t * (4.4 - dtop), 1)
    so = bpy.data.objects.new("springs", helix); bpy.context.scene.collection.objects.link(so); so.data.materials.append(M["spring"]); up.append(so)
    if key_pts:
        k = poly_prism("key", key_pts, 0.30, 1.10, M["key"], 0.03); dn.append(k)
    if rail_from is not None:
        r = box("rail", rail_from, 30, 0.45, 1.0, FLOOR - 0.12, FLOOR - 0.02, M["rail"]); dn.append(r)
    if strip:
        s = box("strip", strip[0], strip[1], 0.5, 1.0, -GAPH, GAPH, glow("strip", 9)); up.append(s)
    for o in up: o.location.z += opened
    for o in dn: o.location.z -= opened
    return M

def key_polygon(n_full, x_tip=None):
    """контур ключа: верх = -длина штифта над каждым поднятым штифтом, дальше скос к острию"""
    pts = [(-30, -4.4)]
    pts.append((-30, -LEN[0]))
    for i in range(n_full):
        pts += [(PX[i] - 0.45, -LEN[i]), (PX[i] + 0.45, -LEN[i])]
    if x_tip is not None:
        xl = PX[n_full - 1] + 0.45
        pts += [(x_tip + 1.0, -4.4)]
    else:
        pts += [(30, -LEN[34]), (30, -4.4)]
    return pts

def A_scene():
    sc = reset()
    spot((6, -34, 12), (6, 0, -1.5), 62000, 100, 1.0, 4)
    cam_ortho(50, (0, -40, CAMZ))
    return sc

def a3():
    A_scene(); lock_section([0] * 35, None, None, rail_from=-30); render("a3_rest")

def a4():
    A_scene(); nf = 18; tip = PX[nf - 1] + 3.0
    # штифт nf (следующий) сидит на скосе: частично поднят
    xs = PX[nf]; ramp = lambda x: -LEN[nf - 1] + (-4.0 + LEN[nf - 1]) * (x - (PX[nf - 1] + 0.45)) / (tip - (PX[nf - 1] + 0.45))
    lift = [1] * nf + [0] * (35 - nf)
    zb = min(-LEN[nf], max(FLOOR, ramp(xs))); lift[nf] = (zb - FLOOR) / (-LEN[nf] - FLOOR)
    lock_section(lift, key_polygon(nf, tip), strip=(-30, PX[nf - 1] + 0.6), rail_from=tip + 0.6); render("a4_lift")

def a5():
    A_scene(); lock_section([1] * 35, key_polygon(35), strip=(-30, 30)); render("a5_line")

def a6():
    sc = A_scene()
    M = lock_section([1] * 35, key_polygon(35), strip=None, opened=2.8)
    wall = box("hall", -40, 40, 6, 6.2, -4, 4, glow_ramp("hall", [(0.0, 0.12), (0.49, 0.28), (0.5, 0.66), (1.0, 0.50)], "Z", 3.0)); wall.location.z = 0
    # корректируем: у градиента порядок стопов — снизу вверх: пол (тёмный→светлый к горизонту), потом стена (светлая→тёмная)
    render("a6_open")

def a1():
    """макро металла: профиль ключа (канавки) идёт от края до края; единственный «слом» — ступень бородки"""
    sc = reset()
    spot((-8, -12, 9), (4, 0, 0), 9500, 60, 0.9, 1.0)
    m = clay("metal", 0.40, 0.38)
    zs = [-2.4, 1.2]; grooves = [-1.25, -0.6, 0.05]
    prof = [(1.0, zs[0]), (0.0, zs[0])]
    for g in grooves: prof += [(0.0, g - 0.22), (0.13, g), (0.0, g + 0.22)]
    prof += [(0.0, zs[1]), (1.0, zs[1])]
    blade = prism_x("blade", prof, -60, 60, m)
    X0 = 9.0
    cutter = poly_prism("cutter", [(X0, 1.5), (X0 + 0.55, 0.55), (80, 0.55), (80, 4), (X0, 4)], -1, 2, None)
    bool_diff(blade, cutter, "EXACT")
    b = blade.modifiers.new("bv", "BEVEL"); b.width = 0.07; b.segments = 3; b.limit_method = "ANGLE"
    cam = cam_persp((-2, -8.5, 0.2), (14, 0, 0.0), 40)
    cam.data.dof.use_dof = True; cam.data.dof.focus_distance = (Vector((X0, 0, 0)) - cam.location).length; cam.data.dof.aperture_fstop = 1.2
    render("a1_macro")

def a2():
    """ключ входит в скважину: плоскость торца сердечника во всю высоту кадра, острие ключа в щели"""
    sc = reset()
    spot((-18, -30, 12), (-3, 0, 0), 52000, 62, 1.0, 3)
    mshell, mplug, mkey = clay("shell", 0.10), clay("plug", 0.34), clay("key", 0.55, 0.45)
    R_OUT, R_IN = 4.8, 3.9
    def cyl_x(name, r, x0, x1, mat, seg=96):
        bpy.ops.mesh.primitive_cylinder_add(vertices=seg, radius=r, depth=x1 - x0, location=((x0 + x1) / 2, 0, 0), rotation=(0, math.pi / 2, 0))
        o = bpy.context.active_object; o.name = name
        if mat: o.data.materials.append(mat)
        bpy.ops.object.shade_smooth(); return o
    shell = cyl_x("shell", R_OUT, 0, 70, mshell)
    hole = cyl_x("hole", R_IN + 0.14, -1, 70, None); bool_diff(shell, hole)
    plug = cyl_x("plug", R_IN, -0.35, 70, mplug)
    slot = box("slot", -1, 8, -0.34, 0.34, -2.3, 2.0, None); bool_diff(plug, slot)
    # ключ: плоская пластина высотой 2.6, острие внутри щели; бородка по нижней кромке (хэш), верх ровный
    top, bot = 1.4, -1.2
    pts = [(-60, top), (-60, bot - 0.2), (-14.0, bot - 0.2)]
    xx = -13.6
    for i in range(7):
        d = 0.15 + 0.85 * H[i * 5]
        pts += [(xx, bot - 0.2), (xx, bot + d), (xx + 0.95, bot + d), (xx + 0.95, bot - 0.2)]
        xx += 1.3
    pts += [(-1.2, bot - 0.2), (-0.5, bot + 0.3), (-0.5, top - 0.3), (-1.2, top)]
    key = poly_prism("key", pts, -0.2, 0.2, mkey, 0.03)
    cam_persp((-20, -29, 2.0), (0, 0, 0.3), 50); render("a2_enter")

# =====================================================================================
# B. «Сквозь»: четыре замка слева направо; горизонталь z=0 — один и тот же жест
# =====================================================================================
def b():
    sc = reset(); spot((-26, -34, 14), (-4, 0, 0), 70000, 120, 1.0, 5)
    cam_ortho(48, (0, -40, 0))
    w = clay("wood", 0.58, 0.9); br = clay("brass", 0.55, 0.5); dk = clay("dark", 0.36); sk = clay("skin", 0.55)
    def ell(name, c, sc3, mat):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=40, ring_count=20, location=c); o = bpy.context.active_object
        o.name = name; o.scale = sc3; o.data.materials.append(mat); bpy.ops.object.shade_smooth(); return o
    X = [-18, -6, 6, 18]
    box("gesture", -26, 26, 3, 3.2, -0.04, 0.04, glow("g", 3.5))          # один и тот же жест — горизонталь z=0
    # 1) ФОРМА: деревянный засов в стойке; ключ-гребёнка с тремя зубьями подпирает засов снизу
    x0 = X[0]
    box("post", x0 - 1.5, x0 + 1.5, -1.0, 1.0, -4.2, 4.2, w, 0.06)
    box("bolt", x0 - 7.0, x0 + 1.5, -1.3, 1.3, -0.8, 0.8, w, 0.06)
    for k in range(3): box("hole%d" % k, x0 - 5.4 + k * 1.3, x0 - 4.9 + k * 1.3, -1.35, -1.28, -0.5, 0.3, clay("holem", 0.02))
    poly_prism("wkey", [(x0 - 8, -2.9), (x0 + 1.0, -2.9), (x0 + 1.0, -2.3), (x0 - 4.8, -2.3), (x0 - 4.8, -1.5), (x0 - 5.4, -1.5), (x0 - 5.4, -2.3), (x0 - 6.1, -2.3), (x0 - 6.1, -1.5), (x0 - 6.7, -1.5), (x0 - 6.7, -2.3), (x0 - 8, -2.3)], 1.1, 1.6, w, 0.03)
    # 2) ЧЕЛОВЕК: портье по грудь, протянутая рука с ключом и тяжёлой грушей
    x1 = X[1] - 2.2
    box("torso", x1 - 2.3, x1 + 2.3, -0.9, 0.9, -5.5, 0.15, dk, 0.9)
    cylinder("neck", x1, 0, 0.1, 0.9, 0.38, sk, 20)
    ell("head", (x1, 0, 1.55), (0.82, 0.8, 0.92), sk)
    cylinder("cap", x1, 0, 2.2, 2.55, 0.98, dk, 32); cylinder("cap2", x1, 0, 2.55, 2.68, 0.72, dk, 32)
    bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=0.42, depth=3.6, location=(x1 + 3.3, 0, -0.05), rotation=(0, math.pi / 2, 0)); a = bpy.context.active_object; a.data.materials.append(dk); bpy.ops.object.shade_smooth()
    ell("hand", (x1 + 5.2, 0, -0.05), (0.55, 0.45, 0.5), sk)
    box("ky", x1 + 5.2, x1 + 8.4, -0.12, 0.12, -0.12, 0.12, br, 0.02)
    ell("ring", (x1 + 5.6, 0, -0.55), (0.18, 0.1, 0.18), br)
    ell("pear", (x1 + 5.6, 0, -2.4), (0.85, 0.5, 1.45), br)
    # 3) КОД: ридер и карта
    x2 = X[2] + 1.0
    box("reader", x2 - 1.6, x2 + 1.6, -0.8, 0.8, -3.8, 3.8, dk, 0.1)
    box("slit", x2 - 1.1, x2 + 1.1, -0.9, -0.5, -0.07, 0.07, clay("slitm", 0.0))
    for k in range(3): cylinder("led%d" % k, x2, -0.83, 1.9 + k * 0.55, 1.9 + k * 0.55 + 0.05, 0.14, glow("led", 2.0 if k == 0 else 0.35), 12)
    box("card", x2 - 5.2, x2 - 0.9, -0.5, -0.3, -0.95, 0.95, clay("card", 0.55), 0.05)
    # 4) ПРАВО: дверь без замка — только контур; ни ручки, ни скважины
    x3 = X[3] + 0.5
    for nm, (a0, b0, c0, c1) in dict(l=(x3 - 3.2, x3 - 2.8, -4.2, 4.2), r=(x3 + 2.8, x3 + 3.2, -4.2, 4.2), t=(x3 - 3.2, x3 + 3.2, 3.8, 4.2)).items():
        box("jamb_" + nm, a0, b0, -0.3, 0.3, c0, c1, glow("jamb", 1.1))
    box("opening", x3 - 2.8, x3 + 2.8, 1.0, 1.2, -4.2, 3.8, glow_ramp("op", [(0.0, 0.10), (0.5, 0.30), (1.0, 0.55)], "Z", 4.0))
    render("b_skvoz")

# =====================================================================================
# C. «Эталон»: каретка копировального станка вдоль кадра
# =====================================================================================
def c():
    sc = reset(); spot((4, -34, 12), (4, 0, 0), 62000, 125, 1.0, 3)
    cam_ortho(48, (0, -40, 0))
    mk_, bk_, ma, st = clay("master", 0.32, 0.5), clay("blank", 0.21, 0.5), clay("mach", 0.06), clay("steel", 0.72, 0.35)
    n = 35; x0, step = -21.0, 1.2
    D = [0.25 + 0.95 * h for h in H]
    xs = [x0 + i * step for i in range(n)]
    XC = 7.0
    Zm, Zb = 3.0, -3.0
    def outline(base, sign, cut_until):
        p = [(-24, base + sign * 1.6), (-24, base)]
        for i in range(n):
            d = D[i] if xs[i] + 0.5 < cut_until else 0.0
            if d: p += [(xs[i] - 0.5, base), (xs[i] - 0.5, base - sign * d), (xs[i] + 0.5, base - sign * d), (xs[i] + 0.5, base)]
            else: p += [(xs[i] - 0.5, base), (xs[i] + 0.5, base)]
        p += [(24, base), (24, base + sign * 1.6)]
        return [q for k, q in enumerate(p) if k == 0 or q != p[k - 1]]
    poly_prism("master", outline(Zm, 1, 99), -0.5, 0.5, mk_, 0.03)         # эталон: рез виден по всей длине
    poly_prism("blank", outline(Zb, -1, XC), -0.5, 0.5, bk_, 0.03)         # копия: готова слева от каретки, справа — гладкая заготовка
    box("bed_top", -26, 26, 0.9, 1.4, Zm + 1.6, Zm + 2.6, ma); box("bed_bot", -26, 26, 0.9, 1.4, Zb - 2.6, Zb - 1.6, ma)
    box("rail", -26, 26, 1.0, 1.4, -0.22, 0.22, ma)
    zst = Zm - D[int((XC - x0) / step)]; zcu = Zb + D[int((XC - x0) / step)]
    box("carriage", XC - 1.8, XC + 1.8, -1.2, 1.2, -0.9, 0.9, st, 0.1)
    box("arm_up", XC - 0.35, XC + 0.35, -0.35, 0.35, 0.9, zst - 0.3, st, 0.04)
    box("arm_dn", XC - 0.3, XC + 0.3, -0.35, 0.35, zcu + 0.3, -0.9, st, 0.04)
    bpy.ops.mesh.primitive_cone_add(vertices=20, radius1=0.38, radius2=0.05, depth=0.7, location=(XC, 0, zst - 0.2)); bpy.context.active_object.data.materials.append(st)
    bpy.ops.mesh.primitive_cylinder_add(vertices=18, radius=1.25, depth=0.3, location=(XC, -0.7, zcu + 0.15), rotation=(math.pi / 2, 0, 0)); bpy.context.active_object.data.materials.append(clay('cutter', 0.95, 0.3))
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.28, depth=0.4, location=(XC, -0.72, zcu + 0.15), rotation=(math.pi / 2, 0, 0)); bpy.context.active_object.data.materials.append(clay('hub', 0.04))
    for k, r in enumerate([0.31, 0.62, 0.17, 0.88, 0.45, 0.73, 0.5]):
        bpy.ops.mesh.primitive_cube_add(size=0.22 + 0.12 * r, location=(XC + 1.8 + 1.0 * k, -0.2, Zb + 0.25 + 0.2 * r + 0.0 * k), rotation=(r * 3, r * 5, r * 7)); bpy.context.active_object.data.materials.append(bk_)
    render("c_etalon")

TASKS = dict(a1=a1, a2=a2, a3=a3, a4=a4, a5=a5, a6=a6, b=b, c=c)
for k in (A.only or TASKS):
    TASKS[k]()
