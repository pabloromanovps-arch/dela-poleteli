#!/usr/bin/env python3
"""Новый бренд из brands/_template: python tools/new_brand.py <client>"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if len(sys.argv) != 2:
    sys.exit(__doc__)
dst = os.path.join(ROOT, "brands", sys.argv[1])
if os.path.exists(dst):
    sys.exit(f"Бренд уже есть: {dst}")
shutil.copytree(os.path.join(ROOT, "brands", "_template"), dst)
print(f"Создан {dst}\nПоложите брендбук в source/, логотипы в logos/, шрифты в fonts/ и заполните brand.yaml.")
