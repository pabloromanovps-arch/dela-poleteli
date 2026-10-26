# Передача дел локальному Claude (на компьютере владельца)

Облачная сессия не имеет доступа к компьютеру владельца. Локальный Claude (Claude Desktop или `claude` в терминале в этой папке)
имеет доступ к After Effects, Blender, Cinema 4D, Unreal и файлам. Он НЕ видит облачного разговора — всё нужное здесь и в `CLAUDE.md`.

## Запуск (владельцу, один раз)
1. Установить Claude Desktop (или Claude Code) на компьютер, где стоят программы.
2. `git clone https://github.com/pabloromanovps-arch/dela-poleteli` (если папка уже есть — `git pull`), открыть папку в Claude.
3. Вставить локальному Claude первый запрос:

> Прочитай HANDOFF.md и CLAUDE.md, затем выполни раздел «Первые задачи» по порядку. После каждой задачи коротко отчитайся.
> Правила студии обязательны: сначала дизайн и одобрение владельца, потом анимация; не выдавай умолчания за решения.

## Состояние проекта «Путеводная звезда 2026» (`projects/pz26_nagrazhdenie/`)
- Реальные рамки: `00_brief/REAL_PROJECT.md` (бюджет: фильм 450 тыс., 35 клипов 450 тыс.; съёмка 23–27.11 делается своими силами; гала 9.12; потолок вне бюджета).
- Готово: бриф, стратегия, идеи, **три концепции события** (`02_concept/show_concepts.md`), направление «Зазор» (`03_style/direction.md`), серые эскизы (`03_style/thumbs/`).
- Ворота 02 (выбор идеи) **ждут владельца**; рабочая рекомендация — B «Линия среза». Анимацию без одобрения кадров НЕ делать.
- Кадры S1–S4 («Зазор») строятся: `03_style/frames/make_frames.py`; если PNG нет — запустить `python 03_style/frames/make_frames.py` (нужен Blender/bpy), посмотреть кадры, замерить `tools/frame_stats.py`, оценить по `design-critique`.
- Незакрытое: референсы владельца (`references/_inbox/`), шрифты (FontHound), форма ключа-награды и вектор логотипа, профиль экрана, 24 вопроса технической службе (`show_concepts.md`).

## Первые задачи (на компьютере владельца)
1. `git pull`; `python -m pip install -r tools/requirements.txt`; `python tools/run.py doctor`; `python tools/selftest.py`. Привести в порядок то, что не нашлось (пути — `studio.config.json` по образцу `studio.config.example.json`).
2. **After Effects**: ранее на компьютере владельца скрипт падал с «Unable to execute script. The Scripting plugin is not installed». В `tools/run.py` теперь запуск ждёт полной загрузки AE. Проверить: открыть AE вручную, дождаться стартового экрана, `File → Scripts` — есть ли пункт; включить `Settings → Scripting & Expressions → Allow Scripts to Write Files and Access Network` (владелец включает вручную, затем перезапуск AE). Затем: `python tools/run.py ae-script tools/ae/demo_players_template.jsx --args screen=uhd_16x9 project=examples/players/players.aep`. Если снова ошибка — не обходить молча, записать точный текст и версию AE, сообщить владельцу (возможна неполная установка AE).
3. Пилот «таблица → версии»: `examples/players/README.md` (шаблон заставки + версии из CSV + очередь рендера). Показать результат владельцу; ошибки .jsx исправлять в `tools/ae/`.
4. Blender: `python tools/run.py blender tools/blender/camera_rig.py -- --spec examples/blender/camera_flythrough.json --report` — проверить на установленном Blender (версию записать).
5. Только после ответа владельца по воротам 02/03: сборка редактируемых проектов стадии 06 по `PROJECT_MAP.md`.

## Что не делать
Не менять `CLAUDE.md` и роли без запроса владельца; не коммитить тяжёлые рендеры и книги владельца (см. `.gitignore`); ничего не слать клиенту без одобрения владельца.


## Экономия токенов
См. `references/token_tools.md`: markitdown и graphify поставить локально, context-mode и headroom — по инструкции там; перед установкой проверить README и лицензию.


## Переезд с облака на компьютер владельца (полный набор)
Владелец хочет работать локально. Порядок для локального Claude:
1. `git pull`, затем `python tools/setup_local.py` (ставит markitdown, graphify, faster-whisper, yt-dlp, librosa и др.; проверяет ffmpeg, node, git).
2. context-mode: `/plugin marketplace add mksglu/claude-context-mode`, затем `/plugin install context-mode@claude-context-mode`. Перед headroom открыть README репозитория и показать владельцу, что он меняет.
3. Изучение сайтов и видео: `python tools/video_notes.py <файл или ссылка> --name <кейс>` даёт лист кадров и расшифровку речи в `references/cases/`. Заметку дописать (что увидел, что берём), статус ВИДЕЛ. Сами ролики в git не кладём (`references/_inbox/`).
4. Сайты читать через WebFetch или браузер. Каждый разбор писать в `references/cases/<имя>.md`.
5. Сервисы генерации (картинки, видео): спросить владельца, какие у него есть, ключи хранить в `studio.config.json` (в git не попадает), не в репозитории.


## Windows и ComfyUI
- На Windows всё то же: Python, ffmpeg, Node, git ставятся через winget (`winget install Python.Python.3.12 Gyan.FFmpeg OpenJS.NodeJS Git.Git`), затем `python tools/setup_local.py` и `python tools/run.py doctor`.
- ComfyUI: `tools/comfy/comfy_run.py` — пакетная генерация из таблицы (workflow в API-формате + карта колонок + CSV), результат в `ai/renders/`, запись в `ai/prompts/library.yaml`. Пример: `examples/comfy/`. Проверено только на имитации сервера, на настоящем ComfyUI не запускалось. Первым делом: `python tools/comfy/comfy_run.py --dry-run ...` и один реальный прогон.
