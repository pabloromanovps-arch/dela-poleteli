# Пилот: заставки игроков из таблицы

Крайние данные специально: двойная длинная фамилия (p02), короткая (p03), строка с `skip=1` (p04).
Фото: положите `photos/<id>.png` и впишите путь `photos/p01_ivanov.png` в колонку `photo`.

```bash
# 1. Собрать шаблон под экран
python tools/run.py ae-script tools/ae/demo_players_template.jsx --args screen=uhd_16x9 project=examples/players/players.aep
# 2. Версии из таблицы + очередь рендера
python tools/run.py ae-script tools/ae/data_driven.jsx --args project=examples/players/players.aep template=TPL_players csv=examples/players/players.csv render=1 out=examples/players/out
# 3. Рендер всей очереди
python tools/run.py ae-render examples/players/players.aep
# 4. Контактный лист
python tools/contact_sheet.py examples/players/out --out examples/players/sheet.png
```
Или одной кнопкой: `tools/launchers/players_demo.bat` (Windows) / `players_demo.command` (Mac).
