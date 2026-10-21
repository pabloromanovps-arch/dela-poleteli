#!/bin/bash
# Пилот «игроки из таблицы» одной кнопкой (macOS). Двойной клик (один раз: chmod +x).
cd "$(dirname "$0")/../.." || exit 1
set -e
python3 tools/run.py ae-script tools/ae/demo_players_template.jsx --args screen=uhd_16x9 project=examples/players/players.aep
python3 tools/run.py ae-script tools/ae/data_driven.jsx --args project=examples/players/players.aep template=TPL_players csv=examples/players/players.csv render=1 out=examples/players/out
echo "Готово: examples/players/players.aep. Рендер: python3 tools/run.py ae-render examples/players/players.aep"
read -r -p "Enter — закрыть"
