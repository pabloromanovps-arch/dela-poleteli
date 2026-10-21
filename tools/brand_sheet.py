#!/usr/bin/env python3
"""Контрольный лист бренда: палитра по ролям, шрифты, логотипы (png-превью) → PNG.

  python tools/brand_sheet.py <client> [--out brands/<client>/brand_sheet.png]
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brand as B  # noqa: E402


def font(family, size):
    for cand in (family, family.replace(" ", ""), "DejaVuSans"):
        try:
            return ImageFont.truetype(cand, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("client")
    p.add_argument("--out")
    a = p.parse_args()
    br = B.load(a.client)
    out = a.out or os.path.join(br["_dir"], "brand_sheet.png")
    W, H = 1920, 1080
    bg = B.rgb(B.color(br, "bg"))
    fg = B.rgb(B.color(br, "text"))
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    small = font("DejaVuSans", 20)
    d.text((80, 50), f"{br.get('name')} · status: {br.get('status')}", fill=fg, font=font("DejaVuSans", 34))

    x = 80
    for role, c in br["colors"].items():
        d.rectangle([x, 140, x + 300, 440], fill=B.rgb(c["hex"]), outline=fg)
        d.text((x, 455), role, fill=fg, font=small)
        d.text((x, 485), c["hex"] + (f"  screen {c['screen']}" if c.get("screen") else ""), fill=fg, font=small)
        x += 340

    y = 560
    for role, f in br.get("fonts", {}).items():
        fam = f.get("file") and os.path.join(br["_dir"], f["file"]) or f.get("family", "")
        d.text((80, y), f"{role}: {f.get('family')} {f.get('weight', '')} · лицензия: {f.get('license') or '?'}",
               fill=fg, font=small)
        d.text((80, y + 30), "Дела полетели — Съешь же ещё этих мягких булок 0123456789", fill=fg, font=font(fam, 48))
        y += 120

    x = 80
    for role, lg in (br.get("logos") or {}).items():
        path = os.path.join(br["_dir"], lg.get("file") or "")
        if lg.get("file") and path.lower().endswith((".png", ".jpg")) and os.path.exists(path):
            logo = Image.open(path).convert("RGBA")
            logo.thumbnail((360, 160))
            im.paste(logo, (x, 860), logo)
            d.text((x, 1030), role, fill=fg, font=small)
            x += 420
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    im.save(out)
    print(f"Лист бренда → {out}")


if __name__ == "__main__":
    main()
