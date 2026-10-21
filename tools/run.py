#!/usr/bin/env python3
"""Мост студии к программам: After Effects, Blender, Cinema 4D, Unreal Engine.

Примеры:
  python tools/run.py doctor
  python tools/run.py ae-script tools/ae/data_driven.jsx --args project=x.aep csv=data/p.csv
  python tools/run.py ae-render projects/x/06_build/x.aep --comp MASTER_uhd
  python tools/run.py blender tools/blender/build_scene.py -- --spec spec.json --out shot.blend
  python tools/run.py blender tools/blender/data_driven.py --blend scene.blend -- --csv data/p.csv --out out/
  python tools/run.py blender-render shot.blend --frames 1-250 --out render/
  python tools/run.py c4d-script script.py -- --foo 1
  python tools/run.py ue-script Game.uproject script.py
  python tools/run.py ue-remote /Game/Map.Map:PersistentLevel.Actor SetActorHiddenInGame '{"bNewHidden":true}'

Пути к программам ищутся автоматически; переопределяются в studio.config.json.
"""
import argparse
import datetime
import glob
import json
import os
import platform
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_DIR = os.path.join(ROOT, "tools", ".run")
LOG_DIR = os.path.join(ROOT, "tools", ".run", "logs")
IS_WIN = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"

# Шаблоны поиска программ: последний по сортировке = самая новая версия.
SEARCH = {
    "afterfx": [
        r"C:\Program Files\Adobe\Adobe After Effects *\Support Files\AfterFX.exe",
        "/Applications/Adobe After Effects */Adobe After Effects *.app",
    ],
    "aerender": [
        r"C:\Program Files\Adobe\Adobe After Effects *\Support Files\aerender.exe",
        "/Applications/Adobe After Effects */aerender",
    ],
    "blender": [
        r"C:\Program Files\Blender Foundation\Blender *\blender.exe",
        "/Applications/Blender.app/Contents/MacOS/Blender",
    ],
    "c4dpy": [
        r"C:\Program Files\Maxon Cinema 4D *\c4dpy.exe",
        "/Applications/Maxon Cinema 4D */c4dpy.app/Contents/MacOS/c4dpy",
    ],
    "c4d_commandline": [
        r"C:\Program Files\Maxon Cinema 4D *\Commandline.exe",
        "/Applications/Maxon Cinema 4D */Commandline.app/Contents/MacOS/Commandline",
    ],
    "unreal_cmd": [
        r"C:\Program Files\Epic Games\UE_*\Engine\Binaries\Win64\UnrealEditor-Cmd.exe",
        "/Users/Shared/Epic Games/UE_*/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor",
    ],
}


def load_config():
    path = os.path.join(ROOT, "studio.config.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


CONFIG = load_config()


def find_app(key):
    configured = CONFIG.get("apps", {}).get(key)
    if configured:
        return configured
    hits = []
    for pattern in SEARCH[key]:
        hits += glob.glob(pattern)
    hits = [h for h in hits if os.path.exists(h)]
    return sorted(hits)[-1] if hits else None


def require_app(key):
    path = find_app(key)
    if not path:
        sys.exit(f"[run] Не найдено: {key}. Укажите путь в studio.config.json → apps.{key}")
    return path


def log_path(name):
    os.makedirs(LOG_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(LOG_DIR, f"{stamp}_{name}.log")


def run(cmd, name, env=None):
    """Запускает команду, дублирует вывод в лог, возвращает код выхода."""
    path = log_path(name)
    print(f"[run] {' '.join(cmd)}\n[run] лог: {path}")
    full_env = dict(os.environ)
    ocio = CONFIG.get("ocio")
    if ocio:
        full_env["OCIO"] = ocio
    full_env.update(env or {})
    with open(path, "w", encoding="utf-8") as log:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                env=full_env, text=True, errors="replace")
        for line in proc.stdout:
            sys.stdout.write(line)
            log.write(line)
        return proc.wait()


def load_screen(name):
    """Читает screens/<name>.yaml (нужен PyYAML) и возвращает dict."""
    import yaml
    path = os.path.join(ROOT, "screens", f"{name}.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def parse_kv(pairs):
    out = {}
    for pair in pairs or []:
        key, _, value = pair.partition("=")
        out[key] = value
    return out


# ---------- After Effects ----------

def write_ae_args(args_dict):
    """Скрипты .jsx читают аргументы из tools/.run/args.json (см. DP.args())."""
    os.makedirs(RUN_DIR, exist_ok=True)
    args_dict = dict(args_dict)
    args_dict["studio_root"] = ROOT.replace("\\", "/")
    screen = args_dict.get("screen")
    if screen:
        args_dict["screen_profile"] = load_screen(screen)
    with open(os.path.join(RUN_DIR, "args.json"), "w", encoding="utf-8") as f:
        json.dump(args_dict, f, ensure_ascii=False, indent=2)


def cmd_ae_script(a):
    script = os.path.abspath(a.script)
    write_ae_args(parse_kv(a.args))
    if IS_WIN:
        return run([require_app("afterfx"), "-r", script], "ae_script")
    if IS_MAC:
        app = os.path.basename(require_app("afterfx")).replace(".app", "")
        apple = f'tell application "{app}" to DoScriptFile "{script}"'
        return run(["osascript", "-e", apple], "ae_script")
    sys.exit("[run] After Effects доступен только на Windows и macOS")


def cmd_ae_render(a):
    cmd = [require_app("aerender"), "-project", os.path.abspath(a.project)]
    if a.comp:
        cmd += ["-comp", a.comp]
        if a.output:
            cmd += ["-output", os.path.abspath(a.output)]
    if a.rqindex:
        cmd += ["-rqindex", str(a.rqindex)]
    if a.mp:
        cmd += ["-mfr", "ON", "100"]
    return run(cmd, "ae_render")


# ---------- Blender ----------

def export_screens_json():
    """Python в Blender обычно без PyYAML — кладём профили экранов как json в tools/.run/screens/."""
    out = os.path.join(RUN_DIR, "screens")
    os.makedirs(out, exist_ok=True)
    for name in os.listdir(os.path.join(ROOT, "screens")):
        if name.endswith(".yaml"):
            with open(os.path.join(out, name[:-5] + ".json"), "w", encoding="utf-8") as f:
                json.dump(load_screen(name[:-5]), f, ensure_ascii=False)


def cmd_blender(a):
    export_screens_json()
    cmd = [require_app("blender"), "-b"]
    if a.blend:
        cmd.append(os.path.abspath(a.blend))
    cmd += ["--python-exit-code", "1", "-P", os.path.abspath(a.script), "--"] + a.rest
    return run(cmd, "blender", env={"DP_STUDIO_ROOT": ROOT})


def cmd_blender_render(a):
    start, _, end = a.frames.partition("-")
    out = os.path.join(os.path.abspath(a.out), a.prefix + "####")
    cmd = [require_app("blender"), "-b", os.path.abspath(a.blend), "-o", out,
           "-s", start, "-e", end or start, "-a"]
    return run(cmd, "blender_render")


# ---------- Cinema 4D ----------

def cmd_c4d_script(a):
    return run([require_app("c4dpy"), os.path.abspath(a.script)] + a.rest, "c4d_script")


def cmd_c4d_render(a):
    start, _, end = a.frames.partition("-")
    cmd = [require_app("c4d_commandline"), "-nogui", "-render", os.path.abspath(a.scene),
           "-frame", start, end or start, "-oimage", os.path.abspath(a.out)]
    return run(cmd, "c4d_render")


# ---------- Unreal Engine ----------

def cmd_ue_script(a):
    cmd = [require_app("unreal_cmd"), os.path.abspath(a.uproject),
           f"-ExecutePythonScript={os.path.abspath(a.script)}", "-stdout", "-unattended"]
    return run(cmd, "ue_script")


def cmd_ue_render(a):
    cmd = [require_app("unreal_cmd"), os.path.abspath(a.uproject), a.map, "-game",
           f"-LevelSequence={a.sequence}", f"-MoviePipelineConfig={a.preset}",
           "-windowed", "-log", "-stdout", "-unattended", "-NoTextureStreaming"]
    return run(cmd, "ue_render")


def cmd_ue_remote(a):
    """Вызов функции в открытом редакторе через Remote Control API."""
    port = CONFIG.get("unreal_remote_port", 30010)
    body = {"objectPath": a.object_path, "functionName": a.function,
            "parameters": json.loads(a.params or "{}"), "generateTransaction": True}
    req = urllib.request.Request(f"http://127.0.0.1:{port}/remote/object/call",
                                 data=json.dumps(body).encode(), method="PUT",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        print(resp.read().decode())
    return 0


# ---------- Диагностика ----------

def cmd_doctor(_a):
    print(f"ОС: {platform.system()} {platform.release()}  Python {sys.version.split()[0]}")
    for key in SEARCH:
        print(f"  {key:16} {find_app(key) or '— не найдено'}")
    for tool in ("ffmpeg", "ffprobe"):
        found = any(os.access(os.path.join(p, tool + (".exe" if IS_WIN else "")), os.X_OK)
                    for p in os.environ.get("PATH", "").split(os.pathsep))
        print(f"  {tool:16} {'ok' if found else '— не найдено (нужно для сдачи и контактных листов)'}")
    for mod in ("yaml", "librosa", "PIL", "openpyxl", "mcp"):
        try:
            __import__(mod)
            status = "ok"
        except ImportError:
            status = "— pip install -r tools/requirements.txt"
        print(f"  py:{mod:13} {status}")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)

    s = sub.add_parser("ae-script")
    s.add_argument("script")
    s.add_argument("--args", nargs="*", help="key=value; screen=<профиль> подгрузит профиль экрана")
    s.set_defaults(fn=cmd_ae_script)

    s = sub.add_parser("ae-render")
    s.add_argument("project")
    s.add_argument("--comp")
    s.add_argument("--output")
    s.add_argument("--rqindex", type=int)
    s.add_argument("--mp", action="store_true", help="многокадровый рендер")
    s.set_defaults(fn=cmd_ae_render)

    s = sub.add_parser("blender")
    s.add_argument("script")
    s.add_argument("--blend", help="открыть .blend перед скриптом")
    s.add_argument("rest", nargs=argparse.REMAINDER)
    s.set_defaults(fn=cmd_blender)

    s = sub.add_parser("blender-render")
    s.add_argument("blend")
    s.add_argument("--frames", default="1-1")
    s.add_argument("--out", required=True)
    s.add_argument("--prefix", default="frame_")
    s.set_defaults(fn=cmd_blender_render)

    s = sub.add_parser("c4d-script")
    s.add_argument("script")
    s.add_argument("rest", nargs=argparse.REMAINDER)
    s.set_defaults(fn=cmd_c4d_script)

    s = sub.add_parser("c4d-render")
    s.add_argument("scene")
    s.add_argument("--frames", default="0-0")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_c4d_render)

    s = sub.add_parser("ue-script")
    s.add_argument("uproject")
    s.add_argument("script")
    s.set_defaults(fn=cmd_ue_script)

    s = sub.add_parser("ue-render")
    s.add_argument("uproject")
    s.add_argument("--map", required=True)
    s.add_argument("--sequence", required=True)
    s.add_argument("--preset", required=True)
    s.set_defaults(fn=cmd_ue_render)

    s = sub.add_parser("ue-remote")
    s.add_argument("object_path")
    s.add_argument("function")
    s.add_argument("params", nargs="?")
    s.set_defaults(fn=cmd_ue_remote)

    a = p.parse_args()
    if getattr(a, "rest", None) and a.rest[:1] == ["--"]:
        a.rest = a.rest[1:]
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
