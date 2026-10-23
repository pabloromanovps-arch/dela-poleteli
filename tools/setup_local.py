#!/usr/bin/env python3
"""Установка рабочего окружения студии на компьютере владельца. Запуск: python tools/setup_local.py
Ставит только проверенные пакеты, остальное проверяет и говорит, что поставить руками."""
import shutil, subprocess, sys

PIP = ["numpy", "scipy", "pillow", "pyyaml", "librosa", "python-pptx", "markitdown[pdf,docx,pptx,xlsx]",
       "graphifyy", "faster-whisper", "yt-dlp"]
TOOLS = {"ffmpeg": "https://ffmpeg.org/download.html", "node": "https://nodejs.org (для context-mode)",
         "git": "https://git-scm.com"}


def main():
    for p in PIP:
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", p])
        print(("ok    " if r.returncode == 0 else "FAIL  ") + p)
    for t, hint in TOOLS.items():
        print(("ok    " if shutil.which(t) else "НЕТ   ") + t + ("" if shutil.which(t) else f"  -> {hint}"))
    if shutil.which("graphify"):
        subprocess.run(["graphify", "install", "--platform", "claude"])
    print("Дальше: python tools/run.py doctor ; python tools/selftest.py")


if __name__ == "__main__":
    main()
