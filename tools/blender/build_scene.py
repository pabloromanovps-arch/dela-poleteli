"""Сцена Blender из spec.json (скилл blender-pipeline).

  python tools/run.py blender tools/blender/build_scene.py -- --spec <spec.json> --out <shot.blend> [--screen <profile>]
Создаёт коллекции CAM/LGT/GEO_hero/GEO_env/FX/REF, камеру, свет, объекты, материалы,
настройки рендера и цвета. Повторный запуск собирает файл заново (идемпотентно).
"""
import argparse
import json
import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import easing  # noqa: E402

ROOT = os.environ.get("DP_STUDIO_ROOT", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
COLLECTIONS = ["CAM", "LGT", "GEO_hero", "GEO_env", "FX", "REF"]

LOOKS = {  # view transform + look; AgX — по умолчанию студии (Blender 4+)
    "agx": ("AgX", "None"),
    "agx_high_contrast": ("AgX", "AgX - High Contrast"),
    "agx_punchy": ("AgX", "AgX - Punchy"),
    "filmic": ("Filmic", "None"),
}


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--spec", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--screen")
    return p.parse_args(argv)


def load_screen(name):
    # tools/run.py перед запуском Blender выгружает профили экранов в json (в Blender нет PyYAML)
    with open(os.path.join(ROOT, "tools", ".run", "screens", name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    cols = {}
    for name in COLLECTIONS:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
        cols[name] = c
    cols["REF"].hide_render = True
    return cols


def link(obj, col):
    for c in obj.users_collection:
        c.objects.unlink(obj)
    col.objects.link(obj)


def material(name, spec):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    presets = {
        "mat_chrome": {"Base Color": (0.9, 0.9, 0.92, 1), "Metallic": 1.0, "Roughness": 0.08},
        "mat_matte_black": {"Base Color": (0.02, 0.02, 0.02, 1), "Metallic": 0.0, "Roughness": 0.6},
        "mat_glass": {"Base Color": (1, 1, 1, 1), "Roughness": 0.02, "Transmission Weight": 1.0, "IOR": 1.45},
    }
    for key, val in {**presets.get(name, {}), **spec.get("materials", {}).get(name, {})}.items():
        if key == "Emission":
            bsdf.inputs["Emission Color"].default_value = val[:3] + [1] if isinstance(val, list) else val
            bsdf.inputs["Emission Strength"].default_value = spec.get("emission_strength", 5)
        elif key in bsdf.inputs:
            bsdf.inputs[key].default_value = tuple(val) if isinstance(val, list) else val
    return mat


def build_object(o, spec, cols):
    t = o["type"]
    if t == "text":
        curve = bpy.data.curves.new(o["name"], "FONT")
        curve.body = o.get("body", o["name"])
        curve.extrude = o.get("extrude", 0.05)
        curve.bevel_depth = o.get("bevel", 0.005)
        curve.align_x = "CENTER"
        curve.align_y = "CENTER"
        if o.get("font"):
            curve.font = bpy.data.fonts.load(os.path.join(ROOT, o["font"]))
        obj = bpy.data.objects.new(o["name"], curve)
        obj.rotation_euler = (math.radians(90), 0, 0)
    elif t in ("cube", "sphere", "plane", "cylinder", "torus"):
        ops = {"cube": bpy.ops.mesh.primitive_cube_add, "sphere": bpy.ops.mesh.primitive_uv_sphere_add,
               "plane": bpy.ops.mesh.primitive_plane_add, "cylinder": bpy.ops.mesh.primitive_cylinder_add,
               "torus": bpy.ops.mesh.primitive_torus_add}
        ops[t]()
        obj = bpy.context.active_object
        obj.name = o["name"]
        if t != "plane" and o.get("smooth", True):
            bpy.ops.object.shade_smooth()
    elif t == "import":
        path = os.path.join(ROOT, o["file"])
        ext = os.path.splitext(path)[1].lower()
        {".glb": bpy.ops.import_scene.gltf, ".gltf": bpy.ops.import_scene.gltf, ".fbx": bpy.ops.import_scene.fbx,
         ".obj": bpy.ops.wm.obj_import, ".abc": bpy.ops.wm.alembic_import, ".usd": bpy.ops.wm.usd_import,
         ".usdc": bpy.ops.wm.usd_import}[ext](filepath=path)
        obj = bpy.context.selected_objects[0]
        obj.name = o["name"]
    else:
        raise ValueError(f"Неизвестный тип объекта: {t}")

    if obj.name not in bpy.context.scene.objects:
        bpy.context.scene.collection.objects.link(obj)
    link(obj, cols[o.get("collection", "GEO_hero")])
    obj.location = o.get("location", (0, 0, 0))
    if "rotation" in o:
        obj.rotation_euler = [math.radians(v) for v in o["rotation"]]
    obj.scale = o.get("scale", (1, 1, 1)) if isinstance(o.get("scale", 1), list) else [o.get("scale", 1)] * 3
    if o.get("material") and obj.type in ("MESH", "FONT", "CURVE"):
        obj.data.materials.clear()
        obj.data.materials.append(material(o["material"], spec))
    for anim in o.get("animate", []):  # {"path":"location","keys":[[1,[0,0,-2]],[40,[0,0,0]]],"ease":"confident"}
        easing.animate(obj, anim["path"], anim["keys"], anim.get("ease", "confident"), anim.get("index", -1))
    return obj


def build_camera(c, cols, spec):
    cam_data = bpy.data.cameras.new("cam_main")
    cam_data.lens = c.get("lens", 35)
    if c.get("dof_target"):
        cam_data.dof.use_dof = True
        cam_data.dof.aperture_fstop = c.get("fstop", 2.8)
    cam = bpy.data.objects.new("cam_main", cam_data)
    cols["CAM"].objects.link(cam)
    cam.location = c.get("location", (0, -10, 2))
    target = bpy.data.objects.new("cam_target", None)
    cols["CAM"].objects.link(target)
    target.location = c.get("target", (0, 0, 0))
    track = cam.constraints.new("TRACK_TO")
    track.target = target
    track.track_axis, track.up_axis = "TRACK_NEGATIVE_Z", "UP_Y"
    if c.get("dof_target"):
        cam_data.dof.focus_object = bpy.data.objects.get(c["dof_target"]) or target
    for anim in c.get("animate", []):
        easing.animate(cam, anim["path"], anim["keys"], anim.get("ease", "cinematic"), anim.get("index", -1))
    bpy.context.scene.camera = cam


def build_light(l, cols):
    data = bpy.data.lights.new(l["name"], l.get("type", "AREA"))
    data.energy = l.get("power", 1000)
    data.color = l.get("color", (1, 1, 1))
    if data.type == "AREA":
        data.size = l.get("size", 2)
    obj = bpy.data.objects.new(l["name"], data)
    cols["LGT"].objects.link(obj)
    obj.location = l.get("location", (3, -3, 4))
    obj.visible_glossy = l.get("visible_glossy", True)  # false — свет не бликует в глянце
    if "target" in l:
        tgt = bpy.data.objects.new(l["name"] + "_target", None)
        cols["LGT"].objects.link(tgt)
        tgt.location = l["target"]
        con = obj.constraints.new("TRACK_TO")
        con.target = tgt
        con.track_axis, con.up_axis = "TRACK_NEGATIVE_Z", "UP_Y"


def render_settings(spec, screen):
    sc = bpy.context.scene
    r = sc.render
    canvas = (screen or {}).get("canvas") or spec.get("canvas", {"width": 3840, "height": 2160})
    fps = (screen or {}).get("fps") or spec.get("fps", 50)
    r.resolution_x, r.resolution_y = canvas["width"], canvas["height"]
    r.resolution_percentage = spec.get("resolution_percentage", 100)
    r.fps = int(fps)
    sc.frame_start, sc.frame_end = spec.get("frames", [1, 250])
    engine = spec.get("engine", "CYCLES")
    r.engine = "BLENDER_EEVEE_NEXT" if engine == "EEVEE" else engine
    if r.engine == "CYCLES":
        sc.cycles.samples = spec.get("samples", 256)
        sc.cycles.use_denoising = True
        sc.cycles.seed = 0
        sc.cycles.use_animated_seed = True
    view, look = LOOKS[spec.get("look", "agx")]
    sc.view_settings.view_transform = view
    try:
        sc.view_settings.look = look
    except TypeError:
        print(f"[build_scene] look «{look}» недоступен в этой версии Blender")
    ims = r.image_settings
    if hasattr(ims, "media_type"):  # Blender 5+: сначала тип медиа, потом формат
        ims.media_type = "MULTI_LAYER_IMAGE"
    ims.file_format = "OPEN_EXR_MULTILAYER"
    r.image_settings.color_depth = "16"
    r.image_settings.exr_codec = spec.get("exr_codec", "DWAA")
    vl = sc.view_layers[0]
    for pas in spec.get("passes", ["z", "mist", "normal", "emit"]):
        setattr(vl, f"use_pass_{pas}", True)
    if spec.get("cryptomatte", True):
        vl.use_pass_cryptomatte_object = True
        vl.use_pass_cryptomatte_material = True
    world = bpy.data.worlds.new("world")
    sc.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = tuple(spec.get("world_color", [0.005, 0.005, 0.007])) + (1,)


def main():
    a = args()
    with open(a.spec, encoding="utf-8") as f:
        spec = json.load(f)
    screen = load_screen(a.screen or spec["screen"]) if (a.screen or spec.get("screen")) and not spec.get("canvas") else None
    cols = reset()
    for o in spec.get("objects", []):
        build_object(o, spec, cols)
    for l in spec.get("lights", []):
        build_light(l, cols)
    build_camera(spec.get("camera", {}), cols, spec)
    render_settings(spec, screen)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
    print(f"[build_scene] {spec.get('shot')} → {a.out}")


main()
