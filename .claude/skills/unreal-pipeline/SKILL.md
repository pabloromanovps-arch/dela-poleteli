---
name: unreal-pipeline
description: Unreal Engine через Python и Remote Control — сборка уровней, Sequencer, Movie Render Queue для offline-рендера, nDisplay для LED-стен и real-time показов. Используй для real-time графики, огромных сцен и интерактивных экранов.
---
# Unreal Engine пайплайн

## Когда UE, а не Blender/AE
- Огромные экраны с большой длительностью: real-time рендер быстрее offline на порядки.
- Живой показ (nDisplay на кластере, реакция на звук/данные/камеру).
- Большие окружения, атмосфера, Lumen/Nanite.

## Запуск
- Скрипт: `python tools/run.py ue-script <project.uproject> <script.py>`
  (`UnrealEditor-Cmd ... -ExecutePythonScript=...`). Включить плагины
  Python Editor Script Plugin, Movie Render Queue, Remote Control API.
- Живое управление открытым редактором: Remote Control API (HTTP, порт 30010) —
  `python tools/run.py ue-remote <object_path> <function> [json]`.
- Рендер: Movie Render Queue с пресетом `MRQ_<project>` (сохранить как ассет) —
  `python tools/run.py ue-render <uproject> --map <map> --sequence <seq> --preset <preset>`.

## Правила
- Sequencer: один Level Sequence на шот, мастер-секвенция собирает шоты
  (имена как в шот-листе).
- MRQ для финала: anti-aliasing через temporal samples (8–32), отключить
  motion blur артефакты на стыках тайлов, вывод EXR 16-bit или ProRes 4444.
- Цвет: OCIO в MRQ (ACES) для композа, либо Rec.709/sRGB для прямой сдачи —
  согласовать с `color-pipeline`.
- nDisplay: конфиг строится от пиксельной карты экрана (`screens/<profile>.yaml`):
  viewports = выходы процессоров. Точка зрителя — для анаморфных эффектов.
- Огромные разрешения: high-res tiling в MRQ.
