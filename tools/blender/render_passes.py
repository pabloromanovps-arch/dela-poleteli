"""Проходы для управляемой генерации (ComfyUI): clay, depth, mask из блокинга в Blender.

  python tools/run.py blender tools/blender/render_passes.py --blend scene.blend -- \
      --shots shots.csv --out ai/passes [--passes clay,depth,mask] [--every 1] [--only 01,03] [--size 1280x720]

shots.csv: shot,cam,frame_start,frame_end (как в 05_plan/shotlist.csv)
Результат: <out>/<pass>/shot<NN>/f<кадр>.png
  clay  — серый объём со светом (для контуров и просто для глаз)
  depth — ближе = светлее, дальше = темнее (для ControlNet depth / IC-LoRA depth); near/far задаются --near/--far
  mask  — каждый объект своим плоским цветом (маски героев и предметов)
Рендер: Cycles на CPU (clay 24 сэмпла, depth/mask 4 сэмпла плоским emission). Видеокарта не нужна.
"""
import argparse, colorsys, csv, os, sys
import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--blend", default=""); ap.add_argument("--shots", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--passes", default="clay,depth,mask"); ap.add_argument("--every", type=int, default=1)
ap.add_argument("--only", default=""); ap.add_argument("--size", default="")
ap.add_argument("--near", type=float, default=0.5); ap.add_argument("--far", type=float, default=8.0)
a = ap.parse_args(argv)

if a.blend:
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(a.blend))
sc = bpy.context.scene
vl = sc.view_layers[0]
if a.size:
    sc.render.resolution_x, sc.render.resolution_y = map(int, a.size.lower().split("x"))
sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGB"
sc.view_settings.view_transform = "Standard"
sc.view_settings.look = "None"
shots = list(csv.DictReader(open(a.shots, encoding="utf-8")))
only = {s.strip() for s in a.only.split(",") if s.strip()}


def emission_mat(name, build):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission"); out = nt.nodes.new("ShaderNodeOutputMaterial")
    build(nt, em); nt.links.new(em.outputs[0], out.inputs[0])
    return m


def depth_build(nt, em):
    cd = nt.nodes.new("ShaderNodeCameraData"); mr = nt.nodes.new("ShaderNodeMapRange")
    mr.clamp = True
    mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = a.near, a.far
    mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = 1.0, 0.0
    nt.links.new(cd.outputs["View Z Depth"], mr.inputs["Value"])
    comb = nt.nodes.new("ShaderNodeCombineColor")
    for ch in ("Red", "Green", "Blue"):
        nt.links.new(mr.outputs["Result"], comb.inputs[ch])
    nt.links.new(comb.outputs["Color"], em.inputs["Color"])


def mask_build(nt, em):
    oi = nt.nodes.new("ShaderNodeObjectInfo")
    nt.links.new(oi.outputs["Color"], em.inputs["Color"])


depth_mat = emission_mat("pass_depth", depth_build)
mask_mat = emission_mat("pass_mask", mask_build)
for i, o in enumerate(sorted((o for o in bpy.data.objects if o.type == "MESH"), key=lambda o: o.name)):
    o.color = (*colorsys.hsv_to_rgb((i * 0.381966) % 1.0, 0.85, 1.0), 1.0)

world = sc.world or bpy.data.worlds.new("w"); sc.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")


def setup(kind):
    if kind == "clay":
        sc.render.engine = "CYCLES"          # Cycles и для clay: работает на любом компьютере без видеокарты и окна
        sc.cycles.device = "CPU"; sc.cycles.samples = 24; sc.cycles.use_denoising = False
        sc.cycles.max_bounces = 2
        vl.material_override = None
        if "clay_sun" not in bpy.data.objects:
            ld = bpy.data.lights.new("clay_sun", "SUN"); ld.energy = 2.5
            lo = bpy.data.objects.new("clay_sun", ld); sc.collection.objects.link(lo)
            lo.rotation_euler = (0.9, 0.2, 0.6)
        if bg: bg.inputs["Color"].default_value = (0.5, 0.5, 0.55, 1); bg.inputs["Strength"].default_value = 0.7
    else:
        sc.render.engine = "CYCLES"
        sc.cycles.device = "CPU"; sc.cycles.samples = 4; sc.cycles.use_denoising = False
        sc.cycles.max_bounces = 0
        vl.material_override = depth_mat if kind == "depth" else mask_mat
        if bg: bg.inputs["Color"].default_value = (0, 0, 0, 1); bg.inputs["Strength"].default_value = 0.0


for kind in [p.strip() for p in a.passes.split(",")]:
    setup(kind)
    for s in shots:
        if only and s["shot"] not in only:
            continue
        sc.camera = bpy.data.objects[s["cam"]]
        d = os.path.join(a.out, kind, f"shot{s['shot']}"); os.makedirs(d, exist_ok=True)
        f0, f1 = int(s["frame_start"]), int(s["frame_end"])
        frames = list(range(f0, f1 + 1, a.every))
        if frames[-1] != f1: frames.append(f1)
        for f in frames:
            sc.frame_set(f)
            sc.render.filepath = os.path.join(d, f"f{f:04d}.png")
            bpy.ops.render.render(write_still=True)
        print(f"[{kind}] shot{s['shot']}: {len(frames)} кадр(ов)")
