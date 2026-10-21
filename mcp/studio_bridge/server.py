#!/usr/bin/env python3
"""MCP-сервер студии «Дела полетели»: даёт Claude Code инструменты для программ.

Тонкая обёртка над tools/run.py и утилитами — вся логика живёт там, чтобы то же самое
можно было запустить руками из терминала. Подключается через .mcp.json в корне репозитория.
"""
import os
import subprocess
import sys

try:  # MCP SDK 2.x
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # MCP SDK 1.x
    from mcp.server.fastmcp import FastMCP

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY = sys.executable
mcp = FastMCP("studio-bridge")


def _run(args, timeout=None):
    proc = subprocess.run([PY] + args, cwd=ROOT, capture_output=True, text=True, timeout=timeout,
                          errors="replace")
    out = (proc.stdout + proc.stderr)[-12000:]
    return f"exit={proc.returncode}\n{out}"


def _kv(args: dict) -> list:
    return [f"{k}={v}" for k, v in (args or {}).items()]


@mcp.tool()
def doctor() -> str:
    """Проверить, какие программы и библиотеки найдены на этом компьютере."""
    return _run(["tools/run.py", "doctor"])


@mcp.tool()
def ae_script(script: str, args: dict | None = None) -> str:
    """Выполнить ExtendScript (.jsx) в After Effects. args → DP.args (screen=<профиль> подгрузит экран).
    Лог скрипта: tools/.run/logs/ae.log."""
    res = _run(["tools/run.py", "ae-script", script, "--args", *_kv(args)], timeout=3600)
    log = os.path.join(ROOT, "tools", ".run", "logs", "ae.log")
    if os.path.exists(log):
        with open(log, encoding="utf-8", errors="replace") as f:
            res += "\n--- ae.log (хвост) ---\n" + "".join(f.readlines()[-40:])
    return res


@mcp.tool()
def ae_render(project: str, comp: str | None = None, output: str | None = None) -> str:
    """Рендер проекта After Effects через aerender (вся очередь или одна композиция)."""
    cmd = ["tools/run.py", "ae-render", project]
    if comp:
        cmd += ["--comp", comp] + (["--output", output] if output else [])
    return _run(cmd)


@mcp.tool()
def blender(script: str, blend: str | None = None, script_args: list[str] | None = None) -> str:
    """Выполнить Python-скрипт в Blender в фоне (необязательно открыв .blend)."""
    cmd = ["tools/run.py", "blender", script] + (["--blend", blend] if blend else []) + ["--"] + (script_args or [])
    return _run(cmd)


@mcp.tool()
def blender_render(blend: str, frames: str, out: str) -> str:
    """Рендер .blend: frames '1-250', out — папка."""
    return _run(["tools/run.py", "blender-render", blend, "--frames", frames, "--out", out])


@mcp.tool()
def c4d_script(script: str, script_args: list[str] | None = None) -> str:
    """Выполнить Python-скрипт через c4dpy (Cinema 4D)."""
    return _run(["tools/run.py", "c4d-script", script, "--"] + (script_args or []))


@mcp.tool()
def unreal_script(uproject: str, script: str) -> str:
    """Выполнить Python-скрипт в Unreal Editor (без интерфейса)."""
    return _run(["tools/run.py", "ue-script", uproject, script])


@mcp.tool()
def unreal_remote(object_path: str, function: str, params_json: str = "{}") -> str:
    """Вызвать функцию объекта в ОТКРЫТОМ Unreal Editor через Remote Control API."""
    return _run(["tools/run.py", "ue-remote", object_path, function, params_json])


@mcp.tool()
def beatgrid(track: str, fps: float, out: str, bpm: float | None = None) -> str:
    """Анализ трека → бит-сетка json (темп, биты, такты, секции, громкость)."""
    return _run(["tools/audio/beats.py", track, "--fps", str(fps), "--out", out] + (["--bpm", str(bpm)] if bpm else []))


@mcp.tool()
def contact_sheet(src: str, out: str, every: float = 1.0) -> str:
    """Контактный лист из видео или папки рендеров для ревью. Затем открой PNG и оцени кадры."""
    return _run(["tools/contact_sheet.py", src, "--out", out, "--every", str(every)])


@mcp.tool()
def deliver(master: str, screen: str, out: str, name: str, check_only: bool = False) -> str:
    """Нарезка мастера по выходам профиля экрана + кодек площадки + проверка ffprobe."""
    return _run(["tools/deliver.py", master, "--screen", screen, "--out", out, "--name", name]
                + (["--check-only"] if check_only else []))


if __name__ == "__main__":
    mcp.run()
