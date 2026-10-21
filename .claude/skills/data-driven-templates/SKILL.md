---
name: data-driven-templates
description: Генерация версий из таблиц — один мастер-шаблон в After Effects или Blender, таблица CSV/Excel/Google Sheets (имена, фото, номера, цвета), автоматическая подстановка и пакетный рендер N роликов. Используй для заставок игроков, спикеров, номинантов, табло, титров и любых серий.
---
# Шаблоны из данных

## Контракт
1. Таблица `data/<template>.csv` (UTF-8, первая строка — заголовки).
   Обязательная колонка `id` (латиница, уникальна — пойдёт в имя файла).
2. В шаблоне `TPL_<template>` слои с именами `@<колонка>`:
   - текстовый слой → подставляется текст;
   - слой футажа → заменяется файлом по пути из ячейки (относительно `data/`);
   - солид/шейп с эффектом Fill или слой-нуль с Color Control → цвет `#RRGGBB`;
   - колонка с префиксом `ctrl_` → значение слайдера `ctrl_<имя>` на `CTRL_data`.
3. Колонка `skip` = 1 → строка пропускается. Колонка `dur` (секунды) → длина версии.

## Порядок работы
1. Сделай мастер и проверь его на **крайних данных**: самое длинное имя,
   двойная фамилия, пустое поле, вертикальное и горизонтальное фото.
   Правило поведения текста — `DP.fitText(layer, maxWidth, minScale)`: сначала
   уменьшение до minScale, потом перенос.
2. Сгенерируй версии:
   `python tools/run.py ae-script tools/ae/data_driven.jsx --args project=<aep> template=TPL_players csv=data/players.csv render=1 om=DP_ProRes4444`
   Результат: композиции `OUT_players_<id>` в `05_RENDER/`, очередь рендера,
   сохранённый проект. Повторный запуск пересоздаёт OUT-композиции.
3. Рендер: `python tools/run.py ae-render <aep>` (вся очередь) — ночной пакет.
4. Контактный лист по всем версиям → `qc-review`. Проверь каждую строку.

## Google Sheets / Excel
- Google Sheets: «Файл → Скачать → CSV» или публичная ссылка
  `.../export?format=csv` — `python tools/fetch_sheet.py <url> data/<t>.csv`.
- Excel: `python tools/fetch_sheet.py file.xlsx data/<t>.csv --sheet "Лист1"`.

## Blender
`python tools/run.py blender tools/blender/data_driven.py --blend <scene.blend> -- --csv data/<t>.csv --out 08_delivery/<t>/`
Объекты-тексты с именами `@<колонка>`, материалы с изображением `@photo`.
