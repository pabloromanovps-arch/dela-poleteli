"""R&D (не производство): ключ «Заготовка» — по одному зубцу на каждую строку data/laureates.csv.
Проверка реализуемости идеи в Blender: зубцы строятся из таблицы, перегенерация = перезапуск.
  python 06_build/rnd/key_from_csv.py --csv data/laureates.csv --out 06_build/rnd/key.blend [--still frame.png]
"""
import argparse, csv, hashlib, math, os, sys
import bpy

p = argparse.ArgumentParser()
p.add_argument("--csv", required=True); p.add_argument("--out", required=True)
p.add_argument("--still"); p.add_argument("--width", type=int, default=1920); p.add_argument("--height", type=int, default=384)
a = p.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])

rows = [r for r in csv.DictReader(open(a.csv, encoding="utf-8-sig")) if r.get("skip") != "1"]
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
col = {n: bpy.data.collections.new(n) for n in ("CAM", "LGT", "KEY", "ENV")}
for c in col.values(): sc.collection.children.link(c)

def mat(name, base, metal, rough):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = base
    b.inputs["Metallic"].default_value = metal; b.inputs["Roughness"].default_value = rough
    return m
gold = mat("mat_gold", (0.85, 0.66, 0.30, 1), 1.0, 0.18)
dark = mat("mat_bg", (0.0, 0.025, 0.035, 1), 0.0, 0.25)

def add(obj, c):
    for x in obj.users_collection: x.objects.unlink(obj)
    col[c].objects.link(obj); return obj

N = len(rows); pitch = 0.42; L = N * pitch
# стержень (blank)
bpy.ops.mesh.primitive_cylinder_add(radius=0.16, depth=L + 1.2, rotation=(0, math.radians(90), 0), location=(L / 2 - 0.2, 0, 0))
shaft = add(bpy.context.active_object, "KEY"); shaft.name = "key_shaft"; shaft.data.materials.append(gold)
# головка (bow) — кольцо
bpy.ops.mesh.primitive_torus_add(major_radius=0.9, minor_radius=0.17, rotation=(math.radians(90), 0, 0), location=(-1.35, 0, 0))
bow = add(bpy.context.active_object, "KEY"); bow.name = "key_bow"; bow.data.materials.append(gold)
# зубцы: высота из id лауреата (детерминированно), по одному на строку
for i, r in enumerate(rows):
    h = 0.25 + (int(hashlib.md5(r["id"].encode()).hexdigest()[:4], 16) % 100) / 100 * 0.75
    bpy.ops.mesh.primitive_cube_add(size=1, location=(i * pitch + 0.1, 0, -0.16 - h / 2 + 0.05))
    t = add(bpy.context.active_object, "KEY"); t.name = f"tooth_{r['id']}"
    t.scale = (pitch * 0.62, 0.30, h); t.data.materials.append(gold)
    bev = t.modifiers.new("bevel", "BEVEL"); bev.width = 0.02; bev.segments = 2
# фон и пол
bpy.ops.mesh.primitive_plane_add(size=60, location=(L / 2, 0, -2.4)); fl = add(bpy.context.active_object, "ENV"); fl.name = "env_floor"; fl.data.materials.append(dark)
# камера: длинный ключ вдоль ультрашироко кадра
cam_d = bpy.data.cameras.new("cam"); cam_d.lens = 40
cam = add(bpy.data.objects.new("cam_main", cam_d), "CAM"); cam.location = (L / 2 - 1.2, -24, -0.55); cam.rotation_euler = (math.radians(90), 0, 0)
sc.camera = cam
def light(name, pw, size, loc, color):
    d = bpy.data.lights.new(name, "AREA"); d.energy = pw; d.size = size; d.color = color
    o = add(bpy.data.objects.new(name, d), "LGT"); o.location = loc
    o.rotation_euler = (math.radians(70), 0, 0) if loc[1] < 0 else (math.radians(110), 0, 0)
light("lgt_key", 6000, 12, (L / 2 - 3, -9, 7), (1.0, 0.9, 0.7))
light("lgt_rim", 5000, 14, (L / 2, 9, 5), (1.0, 0.8, 0.5))
light("lgt_fill", 1500, 16, (L / 2, -10, -3), (0.5, 0.8, 0.9))
sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.0, 0.03, 0.04, 1)
r = sc.render; r.engine = "CYCLES"; sc.cycles.samples = 48; sc.cycles.use_denoising = True
r.resolution_x, r.resolution_y = a.width, a.height
sc.view_settings.view_transform = "AgX"
try: sc.view_settings.look = "AgX - High Contrast"
except TypeError: pass
bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
print(f"[key_from_csv] зубцов: {N}, длина ключа {L:.1f} → {a.out}")
if a.still:
    ims = r.image_settings
    if hasattr(ims, "media_type"): ims.media_type = "IMAGE"
    ims.file_format = "PNG"; r.filepath = os.path.abspath(a.still)
    bpy.ops.render.render(write_still=True); print("[key_from_csv] кадр →", a.still)
