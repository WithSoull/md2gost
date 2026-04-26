# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is md2gost

CLI-утилита для конвертации Markdown в DOCX по ГОСТ 7.32 (научные/учебные отчёты). Обёртка над pandoc + pandoc-crossref с Lua-фильтрами для нумерации разделов, таблиц, формул и листингов кода.

## Commands

```bash
# Установка (Homebrew)
brew tap WithSoull/md2gost https://github.com/WithSoull/md2gost && brew install md2gost

# Установка (dev)
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# Конвертация
md2gost convert report.md                    # → report.docx
md2gost convert report.md -o out.docx        # кастомный выход
md2gost convert report.md --no-toc           # без оглавления
md2gost convert report.md --no-validate      # без валидации

# Watch-режим (пересобирает при сохранении)
md2gost watch report.md

# Тесты
.venv/bin/pytest tests/ -v
```

Внешние зависимости (должны быть в PATH): `pandoc`, `pandoc-crossref`.

## Architecture

**Пайплайн конвертации** (`converter.py`):
1. `validator.py` проверяет .md (YAML-шапка, уровни заголовков, пути картинок, crossref-ссылки)
2. `build_command()` собирает вызов pandoc с Lua-фильтрами и pandoc-crossref
3. Pandoc генерирует .docx по шаблону `md2gost/templates/gost-7.32.docx`
4. Post-processing на уровне OOXML: `_fix_equations()` (формулы с нумерацией через табуляцию) и `_fix_keep_with_media()` (keepNext для привязки рисунков к тексту)

**Lua-фильтры** (`md2gost/filters/`):
- `uppercase-h1.lua` — H1 → заглавные буквы + page break + без нумерации; H2+ → автонумерация (1, 1.1, ...)
- `gost-tables.lua` — нумерация таблиц в формате «Таблица X.Y – Название», замена `@tbl:` ссылок
- `appendix-listing.lua` — блоки кода с первой строкой «Листинг ...» → OOXML-таблицы с Courier New 10pt, авторазбиение по 42 строки с подписями «Продолжение»/«Окончание»
- `gost-equations.lua` — формулы с `\qquad{(N)}` → OOXML с табуляцией (формула по центру, номер справа)

**Порядок фильтров критичен**: Lua-фильтры идут ДО pandoc-crossref в командной строке pandoc.

## Markdown conventions

- YAML-шапка обязательна: `title`, `author`, `date`, `lang: ru`
- `#` (H1) — только ненумерованные: Введение, Заключение, Реферат, Список источников, Приложение X
- `##` / `###` — нумерованные разделы/подразделы (номера добавляются Lua-фильтром)
- Рисунки: `![Caption](path){#fig:name}`, ссылки `@fig:name`
- Таблицы: `: Caption {#tbl:name}` перед таблицей, ссылки `@tbl:name`
- Формулы: `$$ ... $$ {#eq:name}`, ссылки `@eq:name`
- Листинги в приложениях: блок кода, первая строка `Листинг А.1 – Описание`
- Абзац со ссылкой на медиа ставится непосредственно ПЕРЕД медиа-элементом
- Не ставить два медиа подряд без текста между ними
