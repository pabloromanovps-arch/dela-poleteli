# Профили экранов

Каждый проект ссылается на профиль. Все разрешения, fps, зоны и форматы сдачи
берутся отсюда (скилл `led-delivery`).

`status`:
- `verified` — данные подтверждены площадкой (ТЗ, пиксельная карта);
- `standard` — стандартный формат (UHD, FHD), годится как есть;
- `example` — пример-образец для структуры, не для сдачи;
- `draft` — заполнен частично, см. `open_questions`.

Схема:
```yaml
id, title, status, source         # откуда данные (ТЗ, письмо, дата)
canvas: {width, height}           # полный холст, px
fps
pixel_pitch_mm                    # шаг пикселя (для расчёта читаемости)
physical_m: {width, height}
viewing_distance_m: {near, far}
safe_area: {x, y, w, h}           # зона гарантированной видимости текста, px
dead_zones: [{x, y, w, h, note}]  # стыки, колонны, вырезы — не ставить важное
outputs: [{name, x, y, w, h}]     # нарезка по выходам процессоров/медиасервера
media_server
delivery: {codec, container, alpha, color, bit_depth, naming}
max_brightness_note
open_questions: []
```
