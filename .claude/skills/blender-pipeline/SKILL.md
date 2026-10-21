---
name: blender-pipeline
description: Blender через Python (bpy) — построение сцен из спецификации, коллекции и именование, Geometry Nodes, материалы, свет, камеры под экран, Cycles/EEVEE, рендер без интерфейса, многослойный EXR. Используй для 3D в Blender.
---
# Blender пайплайн

## Запуск
- `python tools/run.py blender <script.py> [--blend scene.blend] -- <args>` — фоновый режим.
- Новая сцена из спеки: `python tools/run.py blender tools/blender/build_scene.py -- --spec 06_build/<shot>/spec.json --out 06_build/<shot>/<shot>.blend`
- Рендер: `python tools/run.py blender-render <file.blend> --frames 1-250 --out 06_build/<shot>/render/`

## Структура сцены
Коллекции: `CAM`, `LGT`, `GEO_hero`, `GEO_env`, `FX`, `REF` (не рендерится).
Объекты — `snake_case` с префиксом коллекции: `geo_logo`, `lgt_key`, `cam_main`.
Всё, что меняется данными, — префикс `@`.

## Спека шота (`spec.json`)
```json
{"shot":"sc01_sh010","screen":"uhd_16x9","frames":[1,250],
 "camera":{"lens":35,"location":[0,-12,2],"target":[0,0,1.5]},
 "look":"agx_high_contrast","engine":"CYCLES","samples":256,
 "objects":[{"type":"text","name":"@title","body":"ДЕЛА ПОЛЕТЕЛИ","extrude":0.08,"material":"mat_chrome"}],
 "lights":[{"type":"AREA","name":"lgt_key","power":1200,"size":4,"location":[4,-6,6]}]}
```
`build_scene.py` поддерживает базовые типы; расширяй его, а не пиши разовые скрипты.

## Правила
- Разрешение и fps — из профиля экрана. Если экран > 16K — рендер тайлами
  (`--tiles NxM`, стыкуем в композе) или в масштабе.
- Цвет: View Transform `AgX` (Blender 4+), для кино/VFX — ACES через OCIO
  (см. `color-pipeline`). Не `Standard`.
- Рендер в EXR multilayer (DWAA для превью, ZIP/PIZ для финала) с проходами
  `Combined, Depth, Mist, Normal, Cryptomatte, Emit, Glossy/Diffuse` — что нужно в композе.
- Тест перед финалом: 3 кадра в 50% → время/кадр в `plan.md`.
- Seed шума анимирован, Denoise — OpenImageDenoise; для анимации проверять
  мерцание денойза.
- Geometry Nodes: группы называются `GN_<что>`, входы — с понятными именами,
  чтобы человек мог править в модификаторе.
