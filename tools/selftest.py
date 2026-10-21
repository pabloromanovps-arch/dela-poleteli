#!/usr/bin/env python3
"""Самопроверка студии без внешних программ: python tools/selftest.py

Проверяет инструменты, которые не требуют AE/C4D/UE: бит-сетку, сдачу (ffmpeg),
контактные листы, презентации, бренды, сборку сцены Blender (если доступен bpy
или Blender найден), синтаксис .jsx (если есть Node.js).
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
results = []


def check(name, fn):
    try:
        note = fn() or ""
        results.append(("OK", name, note))
    except Exception as e:  # noqa: BLE001 — нужен отчёт по каждой проверке
        results.append(("FAIL", name, str(e).strip().splitlines()[-1] if str(e).strip() else repr(e)))


def sh(args, **kw):
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, errors="replace", **kw)
    if r.returncode:
        raise RuntimeError((r.stdout + r.stderr)[-400:])
    return r.stdout


def skip(name, why):
    results.append(("SKIP", name, why))


def main():
    tmp = tempfile.mkdtemp(prefix="dp_selftest_")

    check("Python-модули компилируются", lambda: sh([PY, "-m", "compileall", "-q", "tools", "mcp"]) and "")

    if shutil.which("node"):
        def jsx():
            for f in glob.glob(os.path.join(ROOT, "tools", "ae", "**", "*.js*"), recursive=True):
                src = "".join(l for l in open(f, encoding="utf-8") if not l.startswith("#include"))
                p = os.path.join(tmp, "x.js")
                open(p, "w", encoding="utf-8").write(src)
                sh(["node", "--check", p])
            return "синтаксис ES; запуск в самом AE не проверяется"
        check("After Effects .jsx — синтаксис", jsx)
    else:
        skip("After Effects .jsx — синтаксис", "нет Node.js")

    def grid():
        out = os.path.join(tmp, "grid.json")
        sh([PY, "tools/audio/beats.py", "--bpm", "120", "--duration", "8", "--fps", "50", "--out", out])
        g = json.load(open(out))
        assert len(g["downbeats"]) == 4 and g["beats_frames"][1] == 25, "неверная сетка"
        return "120 BPM → 4 такта"
    check("Бит-сетка", grid)

    if shutil.which("ffmpeg"):
        def deliver():
            master = os.path.join(tmp, "m.mov")
            sh(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=7680x1536:rate=50",
                "-t", "1", "-c:v", "prores_ks", "-profile:v", "3", master])
            sh([PY, "tools/deliver.py", master, "--screen", "example_stage_triptych", "--out",
                os.path.join(tmp, "d"), "--name", "t"])
            sh([PY, "tools/contact_sheet.py", master, "--every", "0.5", "--out", os.path.join(tmp, "s.png")])
            return "нарезка 3 выходов HAP Q + контактный лист"
        check("Сдача на LED и контактные листы", deliver)
    else:
        skip("Сдача на LED и контактные листы", "нет ffmpeg")

    def deck():
        out = os.path.join(tmp, "deck.pptx")
        args = [PY, "tools/deck/build_deck.py", "examples/deck/concept_deck.yaml", "--out", out]
        if shutil.which("soffice") or shutil.which("libreoffice"):
            args.append("--pdf")
        sh(args)
        return "PPTX" + (" + PDF" if "--pdf" in args else " (PDF: нет LibreOffice)")
    check("Презентация из deck.yaml", deck)

    check("Бренд: контрольный лист", lambda: sh([PY, "tools/brand_sheet.py", "studio", "--out",
                                                 os.path.join(tmp, "brand.png")]) and "")

    def blender():
        spec = "examples/blender/logo_spec.json"
        out = os.path.join(tmp, "demo.blend")
        try:
            import bpy  # noqa: F401
            sys.path.insert(0, os.path.join(ROOT, "tools"))
            import run
            run.export_screens_json()
            sh([PY, "tools/blender/build_scene.py", "--", "--spec", spec, "--out", out],
               env={**os.environ, "DP_STUDIO_ROOT": ROOT})
            return "через модуль bpy"
        except ImportError:
            sh([PY, "tools/run.py", "blender", "tools/blender/build_scene.py", "--", "--spec", spec, "--out", out])
            return "через установленный Blender"
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import run as _run
    try:
        import bpy  # noqa: F401
        has_bpy = True
    except ImportError:
        has_bpy = False
    if has_bpy or _run.find_app("blender"):
        check("Blender: сцена из спеки", blender)
    else:
        skip("Blender: сцена из спеки", "Blender не найден")

    shutil.rmtree(tmp, ignore_errors=True)
    print()
    for status, name, note in results:
        mark = {"OK": "✅", "FAIL": "❌", "SKIP": "➖"}[status]
        print(f"{mark} {name}" + (f" — {note}" if note else ""))
    print("\nНе проверяется здесь: запуск скриптов внутри After Effects, Cinema 4D, Unreal, Premiere.")
    sys.exit(1 if any(r[0] == "FAIL" for r in results) else 0)


if __name__ == "__main__":
    main()
