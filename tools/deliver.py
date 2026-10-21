#!/usr/bin/env python3
"""Сдача на экран: мастер → нарезка по выходам профиля экрана + кодек площадки + проверка ffprobe.

  python tools/deliver.py master.mov --screen uhd_16x9 --out projects/<id>/08_delivery/ --name <project>_v01
  python tools/deliver.py master.mov --screen <profile> --out ... --check-only
Кодек/контейнер/альфа берутся из screens/<profile>.yaml → delivery.
"""
import argparse
import json
import os
import subprocess
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CODECS = {
    "hap":          (["-c:v", "hap", "-format", "hap"], ".mov"),
    "hap_q":        (["-c:v", "hap", "-format", "hap_q"], ".mov"),
    "hap_alpha":    (["-c:v", "hap", "-format", "hap_alpha"], ".mov"),
    "prores_422hq": (["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"], ".mov"),
    "prores_4444":  (["-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le"], ".mov"),
    "h264":         (["-c:v", "libx264", "-crf", "14", "-preset", "slow", "-pix_fmt", "yuv420p"], ".mp4"),
    "h265":         (["-c:v", "libx265", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p10le"], ".mp4"),
    "png_seq":      (["-c:v", "png"], "_%06d.png"),
}


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,codec_name,pix_fmt,r_frame_rate,nb_frames:format=duration",
                          "-of", "json", path], capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    s = data["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    s["fps"] = round(float(num) / float(den), 3)
    s["duration"] = float(data["format"].get("duration", 0))
    return s


def check(path, w, h, fps):
    s = probe(path)
    problems = []
    if (s["width"], s["height"]) != (w, h):
        problems.append(f"разрешение {s['width']}x{s['height']} ≠ {w}x{h}")
    if abs(s["fps"] - fps) > 0.01:
        problems.append(f"fps {s['fps']} ≠ {fps}")
    status = "OK" if not problems else "ОШИБКА: " + "; ".join(problems)
    print(f"  {os.path.basename(path)}: {s['width']}x{s['height']} {s['fps']}fps {s['codec_name']} "
          f"{s.get('pix_fmt', '')} {s['duration']:.2f}s — {status}")
    return not problems


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("master")
    p.add_argument("--screen", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--name", default="out")
    p.add_argument("--check-only", action="store_true")
    a = p.parse_args()

    with open(os.path.join(ROOT, "screens", a.screen + ".yaml"), encoding="utf-8") as f:
        scr = yaml.safe_load(f)
    if scr.get("status") != "verified":
        print(f"ВНИМАНИЕ: профиль {a.screen} не подтверждён площадкой (status: {scr.get('status')})")
    W, H, fps = scr["canvas"]["width"], scr["canvas"]["height"], scr["fps"]
    codec = scr.get("delivery", {}).get("codec", "prores_422hq")
    args, ext = CODECS[codec]

    print("Мастер:")
    ok = check(a.master, W, H, fps)
    if a.check_only:
        sys.exit(0 if ok else 1)

    os.makedirs(a.out, exist_ok=True)
    outputs = scr.get("outputs") or [{"name": "full", "x": 0, "y": 0, "w": W, "h": H}]
    print(f"Нарезка: {len(outputs)} выход(ов), кодек {codec}")
    all_ok = ok
    for o in outputs:
        dst = os.path.join(a.out, f"{a.name}_{o['name']}{ext}")
        vf = f"crop={o['w']}:{o['h']}:{o['x']}:{o['y']}"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.master, "-vf", vf, "-an", *args, dst], check=True)
        if not ext.endswith(".png"):
            all_ok &= check(dst, o["w"], o["h"], fps)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
