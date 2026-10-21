---
name: ae-pipeline
description: After Effects через скрипты — ExtendScript (.jsx), сборка .aep из спецификации, структура и именование проекта, выражения, контроллеры, Essential Graphics, очередь рендера и aerender. Используй для любой работы с After Effects.
---
# After Effects пайплайн

## Запуск
- Скрипт: `python tools/run.py ae-script <file.jsx> [--args key=value ...]`
  (Windows: `AfterFX.exe -r`, macOS: AppleScript `DoScriptFile`). Аргументы
  передаются через файл `tools/.run/args.json` — скрипт читает их через
  `DP.init(File($.fileName))` и `DP.args` из `tools/ae/lib/dp.jsxinc`.
- Рендер: `python tools/run.py ae-render <project.aep> [--comp NAME] [--rqindex N]`
  (обёртка над `aerender`, логи в `tools/.run/logs/`).
- В AE должно быть включено: Settings → Scripting & Expressions →
  «Allow Scripts to Write Files and Access Network».

## Правила скриптов
- ExtendScript = ES3: нет `let/const`, стрелок, `JSON` (используем `DP.json` из
  библиотеки), `Array.prototype.forEach` и т.п. Пиши в стиле ES3.
- Всё в `app.beginUndoGroup()/endUndoGroup()`, ошибки ловим и пишем в лог
  (`DP.log`), окна `alert` не используем (ломают пакетный режим).
- **Идемпотентность**: перед созданием ищем элемент по имени (`DP.findComp`,
  `DP.findFolder`) и пересобираем, а не плодим копии.
- Подключение библиотеки: `#include "lib/dp.jsxinc"` (путь относительно скрипта в `tools/ae/`),
  первой строкой после include — `DP.init(File($.fileName));`.

## Структура проекта (`DP.ensureFolders`)
```
00_MASTER/      мастер-композиции под сдачу (по одной на выход/нарезку)
01_SHOTS/       sc01_sh010 ...
02_PRECOMPS/    элементы, переиспользуемые блоки
03_TEMPLATES/   мастер-шаблоны для данных (TPL_*)
04_ASSETS/      footage, audio, logos, fonts-preview
05_RENDER/      версии из таблиц (OUT_*)
99_REF/         референсы, стайлфреймы (guide layers)
```
## Именование
- Композиции: `MASTER_<screen>`, `sc01_sh010`, `PRE_<что>`, `TPL_<шаблон>`,
  `OUT_<шаблон>_<rowId>`.
- Слои, которые меняются данными: префикс `@` + имя колонки таблицы:
  `@name`, `@number`, `@photo`, `@team_color`. Это контракт с
  `data-driven-templates`.
- Контроллеры: нули `CTRL_motion`, `CTRL_audio`, `CTRL_color`.

## Композиции
- Размер/fps/длительность — **только** из профиля экрана: `--args screen=<profile>` →
  `tools/run.py` кладёт профиль в args, скрипт берёт его через `DP.screen()`.
- Глубина цвета проекта: 16 bpc минимум, 32 bpc для свечения/градиентов/HDR.
- Огромные холсты (> 8K по стороне): AE ограничен 30000 px. Если экран шире —
  собирай в масштабе 1:2 и рендерь с нарезкой, либо делай секции (см. `led-delivery`).

## Выражения — правила
- Выражения ссылаются на контроллеры по имени, не по индексу.
- Тяжёлые выражения (loops по всем слоям) — запекать перед финальным рендером
  (Animation → Keyframe Assistant → Convert Expression to Keyframes), иначе
  aerender идёт часами.

## Очередь рендера
- Шаблоны вывода (Output Module) создаются один раз вручную в AE
  (Edit → Templates → Output Module) с именами `DP_ProRes4444`, `DP_PNG_Seq`,
  `DP_EXR_Seq`. Скрипты используют их по имени; если шаблона нет — в лог
  пишется предупреждение и остаётся шаблон по умолчанию.
