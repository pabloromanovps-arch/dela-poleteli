# Инструменты экономии токенов

Запрошено владельцем: markitdown, headroom, context-mode, graphify, AI-память.
Статус на момент записи. Цифры экономии — из README самих проектов, нами не проверены.

| Инструмент | Что делает | Статус |
|---|---|---|
| **markitdown** (Microsoft, MIT) | PDF/DOCX/PPTX/XLSX → компактный Markdown. Проверено: брифовый PDF 1,1 МБ → 7 КБ текста | Установлен в облачной сессии (`pip install 'markitdown[pdf,docx,pptx,xlsx]'`). Правило: документы клиента читаем через `markitdown`, не целиком |
| **graphify** (safishamsi/graphify) | Папка → граф знаний (`graphify-out/GRAPH_REPORT.md`), код разбирается локально без LLM | Пакет `graphifyy` и скилл установлены в облаке. Граф проекта ещё не строили |
| **context-mode** (mksglu/claude-context-mode, лицензия Elastic-2.0) | Большой вывод инструментов обрабатывается в песочнице, в контекст идёт только нужное | НЕ установлен: ставится плагином в Claude Code на компьютере владельца (команды ниже) |
| **headroom** (chopratejas/headroom, Apache-2.0) | Прокси сжимает логи и ответы инструментов; `headroom wrap claude` | НЕ установлен: меняет путь API-трафика, в управляемой облачной сессии не ставим. Для локальной машины владельца |
| **AI-память** | Не ясно, какой именно проект имеется в виду | Ждём название от владельца. Пока память — файлы репозитория (`project.yaml`, `okno_decisions.md`, `HANDOFF.md`) |

## Команды для компьютера владельца (в терминале Claude Code)
```
/plugin marketplace add mksglu/claude-context-mode
/plugin install context-mode@claude-context-mode
pip install headroom-ai   # имя пакета проверить в README репозитория перед установкой
pip install "markitdown[all]" graphifyy && graphify install
```
Каждый внешний пакет перед установкой читаем по README и лицензии; код из них в репозиторий студии не копируем.
