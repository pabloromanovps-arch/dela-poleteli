#!/usr/bin/env python3
"""Новый проект из projects/_template.

  python tools/new_project.py 2026_vtb_forum --title "Форум ВТБ" --screen uhd_16x9 --client "ВТБ"
"""
import argparse
import datetime
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("id")
    p.add_argument("--title", required=True)
    p.add_argument("--screen", default="custom")
    p.add_argument("--client", default="")
    a = p.parse_args()

    dst = os.path.join(ROOT, "projects", a.id)
    if os.path.exists(dst):
        sys.exit(f"Проект уже существует: {dst}")
    if a.screen != "custom" and not os.path.exists(os.path.join(ROOT, "screens", a.screen + ".yaml")):
        sys.exit(f"Нет профиля экрана screens/{a.screen}.yaml (или укажите --screen custom)")
    shutil.copytree(os.path.join(ROOT, "projects", "_template"), dst)

    path = os.path.join(dst, "project.yaml")
    text = open(path, encoding="utf-8").read()
    text = (text.replace("{{id}}", a.id).replace("{{title}}", a.title).replace("{{client}}", a.client)
            .replace("{{screen}}", a.screen).replace("{{date}}", datetime.date.today().isoformat()))
    open(path, "w", encoding="utf-8").write(text)
    print(f"Создан проект {dst}\nСледующий шаг: стадия 00 — бриф (агент producer).")


if __name__ == "__main__":
    main()
