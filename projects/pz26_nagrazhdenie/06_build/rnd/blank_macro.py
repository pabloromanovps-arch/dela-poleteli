"""R&D v2 по протоколу art-direction-taste. Предмет: латунная заготовка ключа (материал гостиничного мира).
Тональная структура: 85% тьмы, один скользящий (raking) свет проявляет рельеф металла и граничные фаски.
Один герой, один свет, пустота справа — место для 35 будущих зубцов вдоль кадра.
  python 06_build/rnd/blank_macro.py --out 06_build/rnd/blank.blend --still 06_build/rnd/blank_test.png
"""
import argparse, math, os, sys
import bpy

p = argparse.ArgumentParser(); p.add_argument("--out", required=True); p.add_argument("--still")
p.add_argument("--w", type=int, default=1920); p.add_argument("--h", type=int, default=384); p.add_argument("--samples", type=int, default=96)
a = p.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
bpy.ops.wm.read_factory_settings(use_empty=True); sc = bpy.context.scene

def principled(name, **kw):
    m = bpy.data.materials.new(name); m.use_nodes = True; t = m.node_tree; b = t.nodes["Principled BSDF"]
    for k, v in kw.items():
        if k in b.inputs: b.inputs[k].default_value = v
    return m, t, b

# --- латунь: анизотропная, с микрорельефом вдоль длины (следы обработки), без «идеального глянца»
brass, bt, bb = principled("mat_brass", **{"Base Color": (0.62, 0.43, 0.17, 1), "Metallic": 1.0, "Roughness": 0.30})
if "Anisotropic" in bb.inputs: bb.inputs["Anisotropic"].default_value = 0.7
noise = bt.nodes.new("ShaderNodeTexNoise"); noise.inputs["Scale"].default_value = 90; noise.inputs["Detail"].default_value = 8
mapn = bt.nodes.new("ShaderNodeMapping"); mapn.inputs["Scale"].default_value = (0.03, 14, 14)  # растянуто вдоль X → «царапины» вдоль заготовки
tc = bt.nodes.new("ShaderNodeTexCoord"); bt.links.new(tc.outputs["Object"], mapn.inputs["Vector"]); bt.links.new(mapn.outputs["Vector"], noise.inputs["Vector"])
bump = bt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.35; bump.inputs["Distance"].default_value = 0.01
bt.links.new(noise.outputs["Fac"], bump.inputs["Height"]); bt.links.new(bump.outputs["Normal"], bb.inputs["Normal"])
rough = bt.nodes.new("ShaderNodeMapRange"); rough.inputs["To Min"].default_value = 0.22; rough.inputs["To Max"].default_value = 0.46
bt.links.new(noise.outputs["Fac"], rough.inputs["Value"]); bt.links.new(rough.outputs["Result"], bb.inputs["Roughness"])

# --- поверхность: тёмное сукно/кожа, почти чёрная
cloth, ct, cb = principled("mat_cloth", **{"Base Color": (0.002, 0.005, 0.006, 1), "Roughness": 0.95})
if "Sheen Weight" in cb.inputs: cb.inputs["Sheen Weight"].default_value = 0.6
cn = ct.nodes.new("ShaderNodeTexNoise"); cn.inputs["Scale"].default_value = 400; cn.inputs["Detail"].default_value = 6
cbump = ct.nodes.new("ShaderNodeBump"); cbump.inputs["Strength"].default_value = 0.6
ct.links.new(cn.outputs["Fac"], cbump.inputs["Height"]); ct.links.new(cbump.outputs["Normal"], cb.inputs["Normal"])

def link(o): bpy.context.scene.collection.objects.link(o); return o
# заготовка: профиль с фасками, на правой части кадра — длинная, без бородки
L = 18.0
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.0)); blank = bpy.context.active_object; blank.name = "key_blank"
blank.scale = (L, 0.22, 0.9); bpy.ops.object.transform_apply(scale=True)
bv = blank.modifiers.new("bevel", "BEVEL"); bv.width = 0.035; bv.segments = 4; bv.limit_method = "ANGLE"
blank.data.materials.append(brass)
# головка (bow): овальное кольцо с отверстием — слева, частично уходит за кадр
bpy.ops.mesh.primitive_torus_add(major_radius=1.15, minor_radius=0.2, location=(-L / 2 - 0.7, 0, 0.05)); bow = bpy.context.active_object
bow.name = "key_bow"; bow.rotation_euler = (math.radians(90), 0, 0); bow.scale = (1.0, 1.0, 1.0); bow.data.materials.append(brass)
# единственный зубец — первый надрез (история «каждый добавляет по зубцу»)
bpy.ops.mesh.primitive_cube_add(size=1, location=(-L / 2 + 8.4, 0, -0.45)); cut = bpy.context.active_object; cut.name = "notch_01"
cut.scale = (0.7, 0.6, 0.5)
bm = blank.modifiers.new("notch", "BOOLEAN"); bm.operation = "DIFFERENCE"; bm.object = cut; cut.hide_render = True; cut.hide_viewport = True
# поверхность
bpy.ops.mesh.primitive_plane_add(size=80, location=(0, 0, -0.6)); floor = bpy.context.active_object; floor.name = "env_cloth"; floor.data.materials.append(cloth); floor.hide_render = True  # пол убран: чёрный = выключенные диоды LED

# камера: низкая точка, длинный объектив, малая глубина резкости; фокус на надрезе
cd = bpy.data.cameras.new("cam"); cd.lens = 50; cd.dof.use_dof = True; cd.dof.aperture_fstop = 1.6
cam = bpy.data.objects.new("cam_main", cd); link(cam); cam.location = (-1.0, -18, 0.0)
tgt = bpy.data.objects.new("focus", None); link(tgt); tgt.location = (-L / 2 + 8.4, 0, -0.1); cd.dof.focus_object = tgt
cam.rotation_euler = (math.radians(90), 0, 0); sc.camera = cam
# свет: один низкий скользящий слева (рельеф), крошечный холодный контур справа сзади; пол НЕ освещаем
def area(name, power, size, loc, rot, color):
    d = bpy.data.lights.new(name, "AREA"); d.energy = power; d.size = size; d.color = color
    o = bpy.data.objects.new(name, d); link(o); o.location = loc; o.rotation_euler = [math.radians(v) for v in rot]; return o
k = area("lgt_rake", 2600, 1.2, (-16, -5.5, 0.9), (90, 0, -72), (1.0, 0.80, 0.55)); k.data.shape = "RECTANGLE"; k.data.size_y = 6
area("lgt_rim", 260, 2.0, (8, 5, 3.5), (-60, 0, 20), (0.55, 0.78, 0.9))
sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.0, 0.006, 0.009, 1)
r = sc.render; r.engine = "CYCLES"; sc.cycles.samples = a.samples; sc.cycles.use_denoising = True
r.resolution_x, r.resolution_y = a.w, a.h
sc.view_settings.view_transform = "AgX"
try: sc.view_settings.look = "AgX - High Contrast"
except TypeError: pass
bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out)); print("[blank_macro] →", a.out)
if a.still:
    ims = r.image_settings
    if hasattr(ims, "media_type"): ims.media_type = "IMAGE"
    ims.file_format = "PNG"; r.filepath = os.path.abspath(a.still)
    bpy.ops.render.render(write_still=True); print("[blank_macro] кадр →", a.still)
