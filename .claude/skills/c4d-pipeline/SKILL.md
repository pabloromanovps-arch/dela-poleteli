---
name: c4d-pipeline
description: Cinema 4D через Python — c4dpy, сборка сцен, MoGraph (клонеры, эффекторы), рендер через Commandline, Redshift. Используй, когда проект или исходники в Cinema 4D.
---
# Cinema 4D пайплайн

## Запуск
- Скрипт без интерфейса: `python tools/run.py c4d-script <script.py> -- <args>` (c4dpy).
  c4dpy при первом запуске требует логин Maxon — один раз вручную.
- Рендер: `python tools/run.py c4d-render <scene.c4d> --frames 0-250 --out <path>`
  (`Commandline -render ... -frame A B -oimage ...`).

## Правила
- Иерархия: нули `CAM`, `LGT`, `GEO`, `FX`, `MOGRAPH`; имена латиницей.
- MoGraph — главное преимущество C4D для моушна: клонеры + эффекторы с
  параметрами, вынесенными в User Data на нуле `CTRL` — для правок без
  копания в иерархии.
- Цвет: OCIO (ACEScg) в проекте, Redshift — ACES view.
- Обмен с Blender/UE — Alembic (анимация) или USD; с AE — Cineware или
  многопроходный EXR + экспорт камеры (`.aec` / через json камеры).
- Скрипты для c4dpy проверять на версии пользователя (API меняется между
  R-версиями и 2023+) — указывать версию в шапке скрипта.
