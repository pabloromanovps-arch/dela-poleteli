"""Загрузка brands/<name>/brand.yaml — общий модуль для инструментов."""
import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(name):
    base = os.path.join(ROOT, "brands", name)
    with open(os.path.join(base, "brand.yaml"), encoding="utf-8") as f:
        data = yaml.safe_load(f)
    data["_dir"] = base
    return data


def color(brand, role, screen=False):
    c = brand["colors"][role]
    return (c.get("screen") if screen and c.get("screen") else c["hex"])


def rgb(hex_str):
    h = hex_str.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
