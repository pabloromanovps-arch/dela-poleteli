"""Версии из таблицы в Blender: объекты-тексты @колонка, картинки в материалах @колонка.

  python tools/run.py blender tools/blender/data_driven.py --blend scene.blend -- --csv data/players.csv --out renders/players/ [--still 120]
Для каждой строки: подстановка → рендер (анимация или один кадр --still) в <out>/<id>/.
Файл сцены не перезаписывается.
"""
import argparse
import csv
import os
import sys

import bpy


def args():
    argv = sys.argv[sys.argv.index("--") + 1:]
    p = argparse.ArgumentParser()
    p.add_argument("--csv", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--still", type=int, help="рендерить только этот кадр")
    return p.parse_args(argv)


def hex_rgba(h):
    h = h.lstrip("#")
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb]
    return (*lin, 1.0)


def apply_row(row, data_dir):
    for obj in bpy.data.objects:
        if obj.name.startswith("@") and obj.type == "FONT":
            col = obj.name[1:]
            if row.get(col):
                obj.data.body = row[col]
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if not node.name.startswith("@"):
                continue
            val = row.get(node.name[1:], "")
            if not val:
                continue
            if node.type == "TEX_IMAGE":
                node.image = bpy.data.images.load(os.path.join(data_dir, val), check_existing=True)
            elif node.type == "RGB":
                node.outputs[0].default_value = hex_rgba(val)


def main():
    a = args()
    data_dir = os.path.dirname(os.path.abspath(a.csv))
    with open(a.csv, encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r.get("skip") != "1"]
    sc = bpy.context.scene
    for row in rows:
        apply_row(row, data_dir)
        out_dir = os.path.join(os.path.abspath(a.out), row["id"])
        os.makedirs(out_dir, exist_ok=True)
        if a.still:
            sc.frame_set(a.still)
            sc.render.filepath = os.path.join(out_dir, f"{row['id']}_{a.still:04d}")
            bpy.ops.render.render(write_still=True)
        else:
            sc.render.filepath = os.path.join(out_dir, f"{row['id']}_")
            bpy.ops.render.render(animation=True)
        print(f"[data_driven] {row['id']} → {out_dir}")


main()
