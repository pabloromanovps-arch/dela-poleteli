"""Бит-сетка → маркеры таймлайна и свойство сцены env (громкость 0..1) с ключами.

  python tools/run.py blender tools/blender/import_beatgrid.py --blend scene.blend -- --beatgrid beatgrid.json [--marks beats]
В драйверах: var = scene["env"].
"""
import argparse
import json
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
p = argparse.ArgumentParser()
p.add_argument("--beatgrid", required=True)
p.add_argument("--marks", default="downbeats", choices=["downbeats", "beats"])
a = p.parse_args(argv)

grid = json.load(open(a.beatgrid, encoding="utf-8"))
sc = bpy.context.scene
fps = sc.render.fps / sc.render.fps_base
offset = sc.frame_start

for m in [m for m in sc.timeline_markers if m.name.startswith(("bar ", "beat ", "SECTION"))]:
    sc.timeline_markers.remove(m)
for i, t in enumerate(grid[a.marks]):
    sc.timeline_markers.new(("bar " if a.marks == "downbeats" else "beat ") + str(i + 1), frame=offset + round(t * fps))
for i, t in enumerate(grid["sections"]):
    sc.timeline_markers.new(f"SECTION {i + 1}", frame=offset + round(t * fps))

sc["env"] = 0.0
for t, v in zip(grid["envelope"]["times"], grid["envelope"]["values"]):
    sc["env"] = v
    sc.keyframe_insert(data_path='["env"]', frame=offset + t * fps)
bpy.ops.wm.save_mainfile()
print(f"[beatgrid] {len(grid[a.marks])} маркеров, темп {grid['tempo']:.1f}")
