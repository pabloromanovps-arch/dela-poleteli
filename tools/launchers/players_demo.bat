@echo off
rem Пилот «игроки из таблицы» одной кнопкой (Windows). Двойной клик.
cd /d "%~dp0\..\.."
python tools\run.py ae-script tools\ae\demo_players_template.jsx --args screen=uhd_16x9 project=examples/players/players.aep || goto :err
python tools\run.py ae-script tools\ae\data_driven.jsx --args project=examples/players/players.aep template=TPL_players csv=examples/players/players.csv render=1 out=examples/players/out || goto :err
echo Готово: проект examples\players\players.aep, версии в 05_RENDER, очередь рендера заполнена.
echo Рендер: python tools\run.py ae-render examples\players\players.aep
pause
exit /b 0
:err
echo Ошибка — смотрите tools\.run\logs
pause
