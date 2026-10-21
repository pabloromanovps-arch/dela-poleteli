"""Контактный лист: все эскизы столбиком (без подписей), зазор — тёмно-серый. python make_sheet.py"""
import os
from PIL import Image
d = os.path.dirname(os.path.abspath(__file__))
names = "a1_macro a2_enter a3_rest a4_lift a5_line a6_open b_skvoz c_etalon".split()
ims = [Image.open(os.path.join(d, n + ".png")).convert("RGB") for n in names]
g = 14
s = Image.new("RGB", (1920, (384 + g) * len(ims) - g), (40, 40, 40))
for i, im in enumerate(ims): s.paste(im, (0, i * (384 + g)))
s.save(os.path.join(d, "_contact_sheet.png"))
