"""Блокинг пилота «Ждёт у окна»: серые объёмы, 4 камеры, 480 кадров при 24 fps, 1280x720.
Запуск: python tools/run.py blender projects/pilot_cat_20s/06_build/blocking/build_blocking.py -- --out projects/pilot_cat_20s/06_build/blocking/blocking.blend
Всё редактируется руками: объекты в коллекциях ROOM / HEROES / CAM, шоты по маркерам."""
import argparse, math, sys
import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True)
a = ap.parse_args(argv)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = 1280, 720
sc.render.fps = 24
sc.frame_start, sc.frame_end = 1, 480


def col(name):
    c = bpy.data.collections.new(name); sc.collection.children.link(c); return c


def mat(name, rgb, rough=0.8):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1); b.inputs["Roughness"].default_value = rough
    return m


def add(kind, name, loc, scale=(1, 1, 1), rot=(0, 0, 0), m=None, c=None):
    getattr(bpy.ops.mesh, f"primitive_{kind}_add")(location=loc)
    o = bpy.context.active_object
    o.name = name; o.scale = scale; o.rotation_euler = rot
    if m: o.data.materials.append(m)
    for cc in list(o.users_collection): cc.objects.unlink(o)
    (c or sc.collection).objects.link(o)
    return o


ROOM, HER, CAM = col("ROOM"), col("HEROES"), col("CAM")
wall = mat("wall", (0.55, 0.55, 0.55)); floor = mat("floor", (0.35, 0.35, 0.35))
cat_m = mat("cat", (0.45, 0.45, 0.48)); wom_m = mat("woman", (0.6, 0.6, 0.62))
# комната 6 x 5 м, высота 2,8 м; окно в дальней стене (y=+2.5), дверь в стене справа (x=+3)
add("plane", "floor", (0, 0, 0), (3, 2.5, 1), m=floor, c=ROOM)
add("cube", "wall_back_l", (-1.7, 2.55, 1.4), (1.3, 0.05, 1.4), m=wall, c=ROOM)
add("cube", "wall_back_r", (1.7, 2.55, 1.4), (1.3, 0.05, 1.4), m=wall, c=ROOM)
add("cube", "wall_back_top", (0, 2.55, 2.35), (0.4, 0.05, 0.45), m=wall, c=ROOM)
add("cube", "wall_back_bot", (0, 2.55, 0.5), (0.4, 0.05, 0.5), m=wall, c=ROOM)
add("cube", "wall_left", (-3, 0, 1.4), (0.05, 2.5, 1.4), m=wall, c=ROOM)
add("cube", "wall_front", (0, -2.5, 1.4), (3, 0.05, 1.4), m=wall, c=ROOM)
add("cube", "wall_right_a", (3, 1.6, 1.4), (0.05, 0.9, 1.4), m=wall, c=ROOM)
add("cube", "wall_right_b", (3, -1.7, 1.4), (0.05, 0.8, 1.4), m=wall, c=ROOM)
add("cube", "wall_right_top", (3, -0.1, 2.5), (0.05, 0.8, 0.3), m=wall, c=ROOM)
add("cube", "sill", (0, 2.3, 1.0), (0.55, 0.22, 0.04), m=wall, c=ROOM)
add("cube", "table", (-1.6, 0.8, 0.4), (0.7, 0.4, 0.4), m=wall, c=ROOM)
# дверь на петле: pivot в краю проёма
door = add("cube", "door", (3, -0.45, 1.05), (0.04, 0.45, 1.05), m=mat("door", (0.4, 0.4, 0.4)), c=ROOM)
door.parent = None
bpy.context.view_layer.update()
# кот: тело, голова, уши, хвост
body = add("uv_sphere", "cat_body", (0, 2.2, 1.18), (0.18, 0.28, 0.16), m=cat_m, c=HER)
head = add("uv_sphere", "cat_head", (0, 2.38, 1.3), (0.11, 0.11, 0.1), m=cat_m, c=HER)
ear_l = add("cone", "cat_ear_l", (-0.06, 2.36, 1.4), (0.04, 0.04, 0.07), m=cat_m, c=HER)
ear_r = add("cone", "cat_ear_r", (0.06, 2.36, 1.4), (0.04, 0.04, 0.07), m=cat_m, c=HER)
tail = add("cylinder", "cat_tail", (0.14, 2.0, 1.12), (0.03, 0.03, 0.18), rot=(0.9, 0, 0.5), m=cat_m, c=HER)
for o in (head, ear_l, ear_r, tail):
    o.parent = body; o.matrix_parent_inverse = body.matrix_world.inverted()
# хозяйка
wb = add("cylinder", "woman_body", (3.8, -0.45, 0.85), (0.22, 0.14, 0.7), m=wom_m, c=HER)
wh = add("uv_sphere", "woman_head", (3.8, -0.45, 1.68), (0.11, 0.11, 0.13), m=wom_m, c=HER)
wh.parent = wb; wh.matrix_parent_inverse = wb.matrix_world.inverted()


def key(o, f, **kw):
    for k, v in kw.items():
        setattr(o, k, v); o.keyframe_insert(k, frame=f)


# --- анимация
for f, z in ((1, 1.18), (60, 1.19), (120, 1.18)):          # дыхание кота в шоте 01
    key(body, f, location=(0, 2.2, z))
key(ear_l, 121, rotation_euler=(0, 0, 0)); key(ear_l, 170, rotation_euler=(0, 0, 0.5)); key(ear_l, 240, rotation_euler=(0, 0, 0.5))
key(ear_r, 121, rotation_euler=(0, 0, 0)); key(ear_r, 190, rotation_euler=(0, 0, -0.3)); key(ear_r, 240, rotation_euler=(0, 0, -0.3))
key(door, 241, location=(3, -0.45, 1.05), rotation_euler=(0, 0, 0))
key(door, 300, location=(3.4, -0.1, 1.05), rotation_euler=(0, 0, math.radians(-80)))
key(wb, 241, location=(3.8, -0.45, 0.85)); key(wb, 330, location=(3.3, -0.45, 0.85)); key(wb, 360, location=(2.2, -0.45, 0.85))
key(body, 361, location=(0, 2.2, 1.18))                      # прыжок и бег
key(body, 385, location=(0, 1.7, 1.35)); key(body, 405, location=(0, 0.9, 0.2)); key(body, 480, location=(1.6, -0.2, 0.2))
key(wb, 480, location=(2.0, -0.45, 0.85))

# --- камеры
def cam(name, f0, f1, p0, p1, tgt0, tgt1, lens):
    cd = bpy.data.cameras.new(name); cd.lens = lens
    o = bpy.data.objects.new(name, cd); CAM.objects.link(o)
    t = bpy.data.objects.new(name + "_target", None); CAM.objects.link(t)
    c = o.constraints.new("TRACK_TO"); c.target = t; c.track_axis = "TRACK_NEGATIVE_Z"; c.up_axis = "UP_Y"
    for f, p, q in ((f0, p0, tgt0), (f1, p1, tgt1)):
        o.location = p; o.keyframe_insert("location", frame=f)
        t.location = q; t.keyframe_insert("location", frame=f)
    for ob in (o, t):
        for fc in ob.animation_data.action.layers[0].strips[0].channelbags[0].fcurves if hasattr(ob.animation_data.action, "layers") else ob.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "BEZIER"
    m = sc.timeline_markers.new(name, frame=f0); m.camera = o
    return o


cam("cam_01", 1, 120, (0.1, -1.6, 1.35), (0.05, -0.2, 1.3), (0, 2.2, 1.2), (0, 2.2, 1.2), 35)
cam("cam_02", 121, 240, (0.0, 0.85, 1.36), (0.0, 1.05, 1.38), (0, 2.38, 1.35), (0, 2.38, 1.38), 50)
cam("cam_03", 241, 360, (-1.8, -0.8, 1.2), (-1.2, -0.7, 1.25), (3.2, -0.3, 1.1), (3.3, -0.3, 1.2), 28)
cam("cam_04", 361, 480, (-0.4, -1.8, 1.0), (1.0, -1.9, 1.0), (0, 2.0, 1.0), (1.8, -0.2, 0.8), 32)
sc.camera = bpy.data.objects["cam_01"]
bpy.ops.wm.save_as_mainfile(filepath=a.out)
print("saved", a.out)
