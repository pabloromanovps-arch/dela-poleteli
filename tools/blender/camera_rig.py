"""Камера по видимой траектории (аналог AutoCam / Dolly Rig, но скриптом) — всё правится руками в Blender.

  python tools/run.py blender tools/blender/camera_rig.py [--blend сцена.blend] -- --spec cam.json --out shot.blend
Спека cam.json:
  {"points": [[x,y,z], ...],          # ключевые точки пути (кривая Безье строится гладкой)
   "frames": [1, 250], "ease": "cinematic",       # пресет из lib/easing.py (скорость вдоль пути)
   "target": [0,0,1.2] | [[x,y,z], ...],          # куда смотрит камера (точка или своя траектория той же длины)
   "lens": 50, "shake": 0.0,                      # shake — «рука оператора», 0…1 (см. ниже)
   "name": "cam_main"}
Что создаётся в сцене (всё редактируемо):
  cam_path     — кривая Безье: ТРАЕКТОРИЯ видна во viewport; точки двигаются руками.
  cam_rig      — empty на пути (Follow Path); ключи на offset_factor с кривой скорости пресета.
  cam_main     — камера, ребёнок cam_rig; TRACK_TO на cam_target; здесь же «рука» (шум на локации/повороте).
  cam_target   — empty, на который смотрит камера (можно анимировать/двигать).
Скорость правится в Graph Editor (канал offset_factor у cam_rig); сглаживание — handle'ы точек кривой.
"""
import argparse
import json
import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import easing  # noqa: E402


def build(spec):
    sc = bpy.context.scene
    f0, f1 = spec.get("frames", [1, 250])
    name = spec.get("name", "cam_main")
    col = bpy.data.collections.get("CAM") or bpy.data.collections.new("CAM")
    if col.name not in sc.collection.children:
        sc.collection.children.link(col)

    # --- траектория: гладкая кривая Безье (видна во viewport)
    cu = bpy.data.curves.new("cam_path", "CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new("BEZIER")
    pts = spec["points"]
    sp.bezier_points.add(len(pts) - 1)
    for bp, co in zip(sp.bezier_points, pts):
        bp.co = co
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    path = bpy.data.objects.new("cam_path", cu)
    col.objects.link(path)
    cu.path_duration = f1 - f0

    # --- рельс: empty едет по пути, скорость — кривая пресета на offset_factor
    rig = bpy.data.objects.new("cam_rig", None)
    col.objects.link(rig)
    con = rig.constraints.new("FOLLOW_PATH")
    con.target = path
    con.use_fixed_location = True
    con.use_curve_follow = False
    for frame, val in ((f0, 0.0), (f1, 1.0)):
        con.offset_factor = val
        rig.keyframe_insert(data_path='constraints["Follow Path"].offset_factor', frame=frame)
    for fc in easing.fcurves(rig):
        if fc.data_path.endswith("offset_factor"):
            easing.apply(fc, spec.get("ease", "cinematic"))
    rig["ease"] = spec.get("ease", "cinematic")

    # --- камера
    cd = bpy.data.cameras.new(name)
    cd.lens = spec.get("lens", 50)
    cam = bpy.data.objects.new(name, cd)
    col.objects.link(cam)
    cam.parent = rig
    sc.camera = cam

    # --- цель (точка или своя траектория того же числа кадров)
    tgt = bpy.data.objects.new("cam_target", None)
    col.objects.link(tgt)
    t = spec.get("target", [0, 0, 0])
    if t and isinstance(t[0], (list, tuple)):
        n = len(t)
        for i, co in enumerate(t):
            tgt.location = co
            tgt.keyframe_insert("location", frame=f0 + (f1 - f0) * i / max(n - 1, 1))
        for fc in easing.fcurves(tgt):
            easing.apply(fc, spec.get("ease", "cinematic"))
    else:
        tgt.location = t
    tr = cam.constraints.new("TRACK_TO")
    tr.target = tgt
    tr.track_axis, tr.up_axis = "TRACK_NEGATIVE_Z", "UP_Y"

    # --- «рука оператора»: низкочастотный шум на локации и повороте камеры (0 = штатив)
    k = float(spec.get("shake", 0.0))
    if k > 0:
        cam.location = (0, 0, 0)
        cam.keyframe_insert("location", frame=f0)
        cam.keyframe_insert("rotation_euler", frame=f0)
        for fc in easing.fcurves(cam):
            for old in list(fc.modifiers):
                fc.modifiers.remove(old)
            m = fc.modifiers.new("NOISE")
            is_rot = fc.data_path == "rotation_euler"
            m.strength = k * (0.012 if is_rot else 0.06)
            m.scale = 24.0
            m.phase = fc.array_index * 13.7
            m.depth = 1
    sc.frame_start, sc.frame_end = f0, f1
    return rig, cam


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out")
    ap.add_argument("--report", action="store_true", help="напечатать положение камеры по кадрам")
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
    spec = json.load(open(a.spec, encoding="utf-8"))
    rig, cam = build(spec)
    sc = bpy.context.scene
    if a.report:
        f0, f1 = sc.frame_start, sc.frame_end
        prev = None
        for fr in [f0 + round((f1 - f0) * i / 10) for i in range(11)]:
            sc.frame_set(fr)
            p = cam.matrix_world.translation
            step = 0 if prev is None else (p - prev).length
            print(f"[camera_rig] кадр {fr:4d}  x={p.x:7.2f} y={p.y:7.2f} z={p.z:6.2f}  шаг={step:5.2f}")
            prev = p.copy()
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
        print("[camera_rig] →", a.out)


main()
