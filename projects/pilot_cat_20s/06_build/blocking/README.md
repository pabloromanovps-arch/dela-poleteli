# Блокинг пилота «Ждёт у окна»

Файлы: `build_blocking.py` строит сцену, `blocking.blend` готовый результат (откройте в Blender, камеры `cam_01..04`, маркеры по шотам).
Проверено в облаке: сцена строится, проходы рендерятся (clay, depth, mask) на CPU. В вашем Blender 5.2 на Windows ещё не запускалось.

## Проходы на вашем компьютере (PowerShell, среда `dela`)
```
cd $HOME\dela-poleteli
python tools/run.py blender tools/blender/render_passes.py --blend projects/pilot_cat_20s/06_build/blocking/blocking.blend -- --shots projects/pilot_cat_20s/05_plan/shotlist.csv --out projects/pilot_cat_20s/ai/passes --every 1
```
Сначала для проверки: добавьте `--every 24 --size 640x360`, это займёт несколько минут. Полный прогон (480 кадров × 3 прохода) на CPU займёт долго: ночью.
Результат: `ai/passes/<clay|depth|mask>/shotNN/fNNNN.png` (в git не коммитим).
