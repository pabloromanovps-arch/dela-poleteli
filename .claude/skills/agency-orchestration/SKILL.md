---
name: agency-orchestration
description: Как работает ИИ-агентство «Дела полетели» — оргструктура, кто за что отвечает на каждой стадии, порядок передачи работы между ролями, кто принимает решения и что согласует клиент. Используй в начале любого проекта и всякий раз, когда нужно решить, какой роли поручить задачу.
---
# Оркестрация агентства

## Как это устроено технически
Главная сессия Claude — **дирекция агентства**: она ведёт проект и поручает
задачи ролям (субагентам из `.claude/agents/`) через инструмент Agent. Субагенты
не вызывают друг друга — передача работы всегда идёт через дирекцию и файлы
проекта. Каждая роль получает в задаче: id проекта, стадию, какие файлы прочитать,
какой файл создать, критерий готовности.

Независимые задачи одной стадии запускаются **параллельно** (напр. на 01 —
стратег, концепт-художник и звукорежиссёр одновременно), зависимые — по очереди.

## Оргструктура
| Блок | Роли |
|---|---|
| Клиент и бизнес | account-manager, producer, rights-manager |
| Креатив | strategist, creative-director, art-director, copywriter |
| Препродакшен | concept-artist, designer, storyboard-artist |
| Продакшен | motion-designer, cg-generalist, compositor |
| Постпродакшен | editor, colorist, sound-designer |
| Технологии и качество | technical-director, qc-supervisor |
| Арт-директорат (ИИ) | art-director (глава), look-developer, prompt-director, ai-cinematographer, continuity-supervisor, design-controller |

Для ИИ-проектов (клипы, фильмы, анимационные сцены на нейросетях) стадии 02–06
ведёт арт-директорат по цепочке из скилла `ai-art-direction`.

## Кто что делает на стадиях (О — отвечает, У — участвует, С — согласует)
| Стадия | О | У | С |
|---|---|---|---|
| Запрос, вопросы | account-manager | producer | — |
| 00 Бриф, смета-вилка, КП | producer | account-manager, TD | клиент |
| 01 Стратегия, ресёрч | strategist | art-director, concept-artist, sound-designer | creative-director |
| 02 Идеи и концепт, сценарий | creative-director | art-director, copywriter, concept-artist, producer (реализуемость) | клиент |
| 03 Стиль, библия, стайлфреймы, тексты | art-director | designer, concept-artist, copywriter, cg-generalist | creative-director → клиент |
| 04 Раскадровка, музыка, аниматик | storyboard-artist | motion-designer, sound-designer, copywriter (VO) | creative-director → клиент |
| 05 План, точная смета, права | producer | TD, rights-manager, все исполнители (оценки) | клиент (смета) |
| 06 Производство | motion-designer / cg-generalist | compositor, designer, TD | art-director |
| 06 Пост | editor | colorist, sound-designer | creative-director |
| 07 Ревью | qc-supervisor | art-director, TD, copywriter (корректура), rights-manager | creative-director → клиент |
| 08 Сдача, закрывающие | technical-director | account-manager, producer | клиент |

## Передача работы
В `project.yaml` есть список `tasks`. Каждая роль, закончив работу, отмечает свою
задачу `done` и добавляет следующую тому, кому передаёт:
```yaml
tasks:
  - {id: t003, role: producer, task: "бриф по intake.md", in: [00_brief/intake.md],
     out: [00_brief/brief.md], status: todo, from: account-manager}
```
Статусы: `todo` → `doing` → `done` (или `blocked` + причина). Дирекция берёт
задачи `todo` и раздаёт их ролям; параллельно — все, у кого готовы входы.

## Что и с чьим одобрением уходит клиенту
| Тип | Примеры | Нужно |
|---|---|---|
| Служебное | вопросы, сроки созвона, подтверждение получения | одобрение владельца |
| Коммерческое | КП, смета, допработы, акт | producer + владелец |
| Творческое | концепт, стайлфреймы, аниматик, версии, финал | qc-supervisor «пропускаем» + creative-director «да» + владелец |

Письма: `client/letters/NN_<тема>.md` (NN — сквозной номер), в шапке: статус
(черновик / одобрено / отправлено + дата), кому, тема.

## Правила
- Клиенту пишет только account-manager, по таблице одобрений выше.
- Творческое решение принимает creative-director, визуальное исполнение —
  art-director, деньги и сроки — producer, техника — technical-director.
- Каждая роль пишет результат в файл проекта; устные «договорились» не считаются.
- Человек (владелец агентства) утверждает ворота и всё, что уходит клиенту.

## Типовой запуск
«Новый проект: …» → new-project → account-manager (intake + письмо с
вопросами: что не хватает для брифа, формулирует для клиента) → [владелец
одобряет, ответы клиента] → producer (бриф, смета-вилка) → strategist ∥ concept-artist ∥ sound-designer →
creative-director (идеи) → art-director + copywriter (концепт, сценарий) →
designer (презентация концепта) → qc-supervisor → account-manager (отправка).
