# md2gost

Конвертер Markdown → DOCX по ГОСТ 7.32. Пишешь отчёт в Markdown, получаешь готовый `.docx` с правильным оформлением: нумерация разделов, таблиц, формул, листинги кода в приложениях, оглавление.

## Установка

### macOS (Homebrew) — рекомендуется

```bash
brew tap WithSoull/md2gost https://github.com/WithSoull/md2gost
brew install md2gost
```

Всё. Pandoc, pandoc-crossref и Python-зависимости подтянутся автоматически.

### Ручная установка

Если не используешь Homebrew:

1. Поставь зависимости:

```bash
# macOS
brew install pandoc pandoc-crossref

# Ubuntu/Debian
sudo apt install pandoc
# pandoc-crossref: скачай бинарник с https://github.com/lierdakil/pandoc-crossref/releases
```

2. Установи md2gost:

```bash
git clone https://github.com/WithSoull/md2gost.git
cd md2gost
python3 -m venv .venv
.venv/bin/pip install -e .
source .venv/bin/activate
```

## Использование

```bash
# Базовая конвертация
md2gost convert report.md

# Указать выходной файл
md2gost convert report.md -o ~/Desktop/отчёт.docx

# Без оглавления
md2gost convert report.md --no-toc

# Свой шаблон
md2gost convert report.md -t my_template.docx

# Пропустить валидацию
md2gost convert report.md --no-validate

# Watch-режим — пересобирает при каждом сохранении
md2gost watch report.md
```

## Как писать Markdown для ГОСТ

### Шапка файла (обязательна)

```yaml
---
title: "Название отчёта"
author: "Иванов И.И."
date: "2026-04-25"
lang: ru
---
```

### Структура заголовков

```markdown
# Введение              ← ненумерованный, ЗАГЛАВНЫЕ в DOCX, с новой страницы
## Теоретическая часть   ← станет «1 Теоретическая часть»
### Подраздел            ← станет «1.1 Подраздел»
## Практическая часть    ← станет «2 Практическая часть»
# Заключение            ← ненумерованный
# Список использованных источников
# Приложение А
```

**Правила:**
- `#` — только для спец-разделов без номера (Введение, Заключение, Реферат, Список источников, Приложение)
- `##` и `###` — нумерованные разделы, номера добавляются автоматически
- Не пиши номера вручную — фильтр сделает это сам

### Рисунки

```markdown
На @fig:schema показана архитектура системы.

![Архитектура системы](images/schema.png){#fig:schema}
```

> `@fig:schema` автоматически превратится в «рис. 1». Не пиши «на рисунке @fig:schema» — получится «на рисунке рис. 1».

### Таблицы

```markdown
Результаты приведены в @tbl:results.

: Результаты эксперимента {#tbl:results}

| Метод   | Точность |
|---------|----------|
| GCN     | 0.82     |
| GAT     | 0.85     |
```

### Формулы

```markdown
Оценка внимания вычисляется по @eq:attention.

$$
\text{Attention}(Q, K, V) = \text{softmax}\!\left(\frac{QK^\top}{\sqrt{d_k}}\right)V
$$ {#eq:attention}
```

### Листинги кода (в приложениях)

Первая строка блока кода — подпись листинга:

````markdown
# Приложение А

Исходный код на Python.

```
Листинг А.1 – Основной модуль
import torch
import torch.nn as nn

class Model(nn.Module):
    def __init__(self):
        super().__init__()
        ...
```
````

Длинные листинги автоматически разбиваются на страницы с подписями «Продолжение» и «Окончание».

### Список литературы

```markdown
# Список использованных источников

1. Иванов И.И. Название книги. — М.: Издательство, 2024. — 200 с.
2. Петров П.П. Название статьи // Журнал. — 2023. — Т. 5, № 2. — С. 10–15.
```

## Использование с Claude Code

[Claude Code](https://claude.ai/code) — AI-ассистент в терминале, который умеет писать и редактировать отчёты за тебя.

### Установи скилл (один раз)

Скилл — это инструкция для Claude, как правильно писать отчёт по ГОСТ. Добавь alias в `~/.zshrc` (или `~/.bashrc`):

```bash
echo 'alias gost-skill="mkdir -p .claude/commands && curl -sL https://raw.githubusercontent.com/WithSoull/md2gost/main/.claude/commands/write-report.md -o .claude/commands/write-report.md && echo write-report skill installed"' >> ~/.zshrc
source ~/.zshrc
```

### Используй

1. Перейди в директорию с проектом, где нужен отчёт:

```bash
cd ~/my-project
```

2. Установи скилл в этот проект:

```bash
gost-skill
```

3. Запусти Claude Code и вызови скилл:

```bash
claude
```

В чате набери:

```
/write-report
```

Claude задаст вопросы про тему, автора, разделы — и сгенерирует готовый `.md` файл, а затем сам сконвертирует его в `.docx`.

### Что умеет скилл

- Задаёт вопросы и генерирует полноценный `.md` по ГОСТ 7.32
- Правильно оформляет рисунки, таблицы, формулы, листинги
- Автоматически запускает `md2gost convert` после генерации
- Можно попросить отредактировать уже существующий отчёт
