"""Кривые движения студии для Blender: cubic-bezier → хэндлы ключей. См. скилл motion-language."""

PRESETS = {
    "precise": (0.7, 0, 0.2, 1),
    "confident": (0.3, 0, 0, 1),
    "soft": (0.45, 0, 0.25, 1),
    "punchy": (0.9, 0, 0.1, 1),
    "cinematic": (0.4, 0, 0.1, 1),
    "enter": (0, 0, 0.2, 1),
    "exit": (0.6, 0, 1, 1),
}


def apply_segment(k0, k1, bezier):
    """Задаёт хэндлы между двумя ключами FCurve так, чтобы сегмент повторял cubic-bezier."""
    x1, y1, x2, y2 = bezier
    (t0, v0), (t1, v1) = k0.co, k1.co
    dt, dv = t1 - t0, v1 - v0
    k0.interpolation = "BEZIER"
    k0.handle_right_type = "FREE"
    k1.handle_left_type = "FREE"
    k0.handle_right = (t0 + x1 * dt, v0 + y1 * dv)
    k1.handle_left = (t0 + x2 * dt, v0 + y2 * dv)


def apply(fcurve, preset):
    bezier = PRESETS[preset] if isinstance(preset, str) else preset
    pts = fcurve.keyframe_points
    for i in range(len(pts) - 1):
        apply_segment(pts[i], pts[i + 1], bezier)


def animate(obj, path, keys, preset, index=-1):
    """keys: [(кадр, значение)], значение — число или вектор для свойства целиком."""
    for frame, value in keys:
        setattr_path(obj, path, value, index)
        obj.keyframe_insert(data_path=path, frame=frame, index=index)
    for fc in fcurves(obj):
        if fc.data_path == path and (index < 0 or fc.array_index == index):
            apply(fc, preset)


def setattr_path(obj, path, value, index):
    if index >= 0:
        getattr(obj, path)[index] = value
    else:
        setattr(obj, path, value)


def fcurves(id_data):
    """FCurve'ы объекта: Blender 4.4+ (слотовые экшены) и старые версии."""
    ad = id_data.animation_data
    act = ad.action
    if hasattr(act, "fcurves"):  # Blender < 4.4 (в 4.4 ещё есть как прокси)
        return act.fcurves
    for layer in act.layers:
        for strip in layer.strips:
            bag = strip.channelbag(ad.action_slot)
            if bag:
                return bag.fcurves
    return []
