from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class ValidationWarning:
    line: int | None
    message: str


class ValidationError(Exception):
    pass


def validate(input_path: str | Path) -> list[ValidationWarning]:
    input_path = Path(input_path)
    text = _read_utf8(input_path)
    lines = text.splitlines()
    warnings: list[ValidationWarning] = []
    warnings += _check_rules(lines)
    warnings += _check_yaml_header(lines)
    warnings += _check_heading_levels(lines)
    warnings += _check_image_paths(lines, input_path.parent)
    warnings += _check_crossref_syntax(lines)
    warnings += _check_reference_words(text)
    warnings += _check_formula_punctuation(lines)
    warnings += _check_typography(lines)
    warnings += _check_lists(lines)
    warnings += _check_sources_and_appendices(lines)
    return warnings


def _read_utf8(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"Файл не является UTF-8: {exc}") from exc


def _check_yaml_header(lines: list[str]) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    if not lines or lines[0].strip() != "---":
        warnings.append(ValidationWarning(line=1, message="Отсутствует YAML-шапка (---) в начале файла"))
        return warnings

    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() in ("---", "..."):
            end = i
            break

    if end is None:
        warnings.append(ValidationWarning(line=1, message="YAML-шапка не закрыта"))
        return warnings

    try:
        meta = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError:
        warnings.append(ValidationWarning(line=1, message="Ошибка парсинга YAML-шапки"))
        return warnings

    if not isinstance(meta, dict):
        meta = {}

    for field in ("title", "author", "date"):
        if field not in meta:
            warnings.append(ValidationWarning(line=1, message=f"Отсутствует поле '{field}' в YAML-шапке"))

    return warnings


def _check_heading_levels(lines: list[str]) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    heading_re = re.compile(r"^(#{1,6}) ")
    prev_level = 0

    for i, line in enumerate(lines, start=1):
        m = heading_re.match(line)
        if not m:
            continue
        level = len(m.group(1))
        if prev_level > 0 and level > prev_level + 1:
            warnings.append(ValidationWarning(
                line=i,
                message=f"Пропущен уровень заголовка: H{prev_level} → H{level}",
            ))
        prev_level = level

    return warnings


def _check_image_paths(lines: list[str], base_dir: Path) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    image_re = re.compile(r"!\[.*?\]\(([^)]+)\)")

    for i, line in enumerate(lines, start=1):
        for m in image_re.finditer(line):
            path_str = m.group(1).split(" ")[0]  # убрать alt-текст после пробела
            if path_str.startswith(("http://", "https://")):
                continue
            if not (base_dir / path_str).exists():
                warnings.append(ValidationWarning(
                    line=i,
                    message=f"Изображение '{path_str}' не найдено",
                ))

    return warnings


def _check_crossref_syntax(lines: list[str]) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    ref_re = re.compile(r"@(fig|tbl|eq):([\w.-]*[\w-])")
    anchor_re = re.compile(r"\{#(fig|tbl|eq):([\w.-]+)(?=\s|\})")

    text = "\n".join(lines)
    anchors = {(t, n) for t, n in anchor_re.findall(text)}

    for i, line in enumerate(lines, start=1):
        for kind, name in ref_re.findall(line):
            if (kind, name) not in anchors:
                warnings.append(ValidationWarning(
                    line=i,
                    message=f"Ссылка @{kind}:{name} не имеет определения {{#{kind}:{name}}}",
                ))

    return warnings


_REFERENCE_WORDS = {"fig": ("Рисун", "Рисунок"), "tbl": ("Табли", "Таблица")}
_CONNECTORS = {"и", "или", "а", "также"}


def _check_reference_words(text: str) -> list[ValidationWarning]:
    """@fig:/@tbl: render as a bare number, so the noun must precede them."""
    warnings: list[ValidationWarning] = []
    ref_re = re.compile(r"@(fig|tbl|eq):([\w.-]*[\w-])")
    for m in ref_re.finditer(text):
        kind, name = m.groups()
        if kind == "eq":
            continue
        # Look within the paragraph only. Grouped references share one noun:
        # «Таблицы @tbl:a и @tbl:b», «Рисунки [@fig:a; @fig:b]».
        before = text[max(0, m.start() - 200):m.start()].rsplit("\n\n", 1)[-1]
        before = ref_re.sub(" ", before)
        words = re.findall(r"[^\W\d_]+", before)
        while words and words[-1].lower() in _CONNECTORS:
            words.pop()
        prefix, noun = _REFERENCE_WORDS[kind]
        if not words or not words[-1].startswith(prefix):
            warnings.append(ValidationWarning(
                line=text.count("\n", 0, m.start()) + 1,
                message=f"Перед @{kind}:{name} нет слова «{noun}» в нужном падеже: "
                        f"ссылка выводится только номером",
            ))
    return warnings


def print_warnings(warnings: list[ValidationWarning]) -> None:
    if not warnings:
        return
    print(f"⚠  Предупреждения ({len(warnings)}):")
    for w in warnings:
        loc = f"[line {w.line}] " if w.line is not None else ""
        print(f"   {loc}{w.message}")
    print("✓  Конвертация продолжается...")


def _prose(lines: list[str]):
    """(line number, line) outside the YAML header, code blocks and display math."""
    fence = None
    math = False
    in_yaml = bool(lines and lines[0].strip() == '---')
    for number, line in enumerate(lines, 1):
        if in_yaml:
            if number > 1 and line.strip() in ('---', '...'):
                in_yaml = False
            continue
        match = re.match(r'^\s*(`{3,}|~{3,})', line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
            continue
        if fence:
            continue
        if line.strip().startswith('$$'):
            # A one-line formula opens and closes on the same line.
            math = not math if line.strip().count('$$') == 1 else math
            continue
        if math:
            continue
        yield number, line


def _check_rules(lines: list[str]) -> list[ValidationWarning]:
    """Content constraints are warnings; never rewrite the author's prose."""
    warnings = []
    for number, line in _prose(lines):
        if re.search(r'\[\^[^\]]+\]|\^\[', line):
            warnings.append(ValidationWarning(number, 'Сноски внизу страницы запрещены пунктом 1.8 правил оформления'))
        heading = re.match(r'^#{1,6}\s+(.+?)(?:\s+\{.*\})?$', line)
        if heading and heading.group(1).rstrip().endswith(('.', ':', ';')):
            warnings.append(ValidationWarning(number, 'В конце заголовка не ставится знак препинания (п. 2.2.5)'))
        if heading and heading.group(1)[:1].islower():
            warnings.append(ValidationWarning(number, 'Заголовок начинается с прописной буквы (п. 2.2.4)'))
        appendix = re.match(r'^#\s+Приложение\s+([А-ЯЁ])(?:\.|\s|$)', line, re.I)
        if appendix and appendix.group(1).upper() in 'ЁЗЙОЧЬЫЪ':
            warnings.append(ValidationWarning(number, 'Эта буква исключена из обозначений приложений (п. 10.3)'))
        caption = re.match(r'^:\s+(.+?)\s*(?:\{.*\})?$', line) or re.match(r'^!\[(.+?)\]\(', line)
        if caption and caption.group(1).rstrip().endswith('.'):
            warnings.append(ValidationWarning(number, 'В конце названия таблицы или рисунка точка не ставится (п. 6.2, 7.2)'))
    return warnings


def _summary(numbers: list[int], message: str) -> list[ValidationWarning]:
    """One warning for a rule broken in many places."""
    if not numbers:
        return []
    shown = ', '.join(map(str, numbers[:8])) + (' …' if len(numbers) > 8 else '')
    return [ValidationWarning(numbers[0], f'{message}; строки {shown} (всего {len(numbers)})')]


def _check_formula_punctuation(lines: list[str]) -> list[ValidationWarning]:
    """Rules 5.4: a formula followed by «где» continues the sentence with a comma."""
    missing = []
    text = '\n'.join(lines)
    for match in re.finditer(r'\$\$(.+?)\$\$(?:[ \t]*\{#eq:[^}]*\})?[ \t]*\n\s*\n(\S+)', text, re.S):
        formula, following = match.group(1).strip(), match.group(2)
        if following.lower().rstrip(':,') == 'где' and not formula.endswith(','):
            missing.append(text.count('\n', 0, match.start()) + 1)
    return _summary(missing, 'Перед пояснением «где» формула заканчивается запятой (п. 5.4)')


def _check_typography(lines: list[str]) -> list[ValidationWarning]:
    """Rules 1.11: the dash «—» stands between spaces; «–» is a minus, «-» a hyphen."""
    dashes = []
    for number, line in _prose(lines):
        # Inline code and math may contain any signs.
        plain = re.sub(r'`[^`]*`|\$[^$]*\$', '', line)
        # A lone «–» in a table cell marks an empty value, not a dash.
        if plain.lstrip().startswith('|'):
            continue
        if re.search(r'\s[–-]\s', plain) and not re.match(r'^\s*[-*+]\s', plain):
            dashes.append(number)
    return _summary(dashes, 'Тире между словами набирается знаком «—», «–» — это минус (п. 1.11)')


def _check_lists(lines: list[str]) -> list[ValidationWarning]:
    """Rules 4.3 and 4.4: punctuation and case of list items."""
    warnings = []
    sources = _sources(lines)
    items = [(n, m.group(1), m.group(2)) for n, line in _prose(lines)
             if (m := re.match(r'^(?:\s{0,3})([-*+]|\d+[.)])\s+(.+)$', line))]
    for number, marker, item in items:
        # Entries of the list of sources follow bibliographic rules instead.
        if any(start < number < end for start, end in sources):
            continue
        first = re.sub(r'^[*_`\[«"]+', '', item)[:1]
        if marker[0].isdigit():
            if first.islower() or not item.rstrip().endswith('.'):
                warnings.append(ValidationWarning(
                    number, 'Пункт нумерованного списка начинается с прописной буквы и заканчивается точкой (п. 4.4)'))
        elif first.isupper() or not item.rstrip().endswith((';', '.')):
            warnings.append(ValidationWarning(
                number, 'Пункт маркированного списка начинается со строчной буквы, '
                        'заканчивается точкой с запятой, последний — точкой (п. 4.3)'))
    return warnings


def _sources(lines: list[str]) -> list[tuple[int, int]]:
    """Line ranges of the list of sources: from its H1 to the next H1."""
    headings = [(n, line[2:].strip()) for n, line in _prose(lines) if line.startswith('# ')]
    return [(number, headings[i + 1][0] if i + 1 < len(headings) else len(lines) + 1)
            for i, (number, title) in enumerate(headings)
            if re.match(r'(?i)список\s+(использ|источник)', title)]


def _check_sources_and_appendices(lines: list[str]) -> list[ValidationWarning]:
    warnings = []
    headings = [(n, line[2:].strip()) for n, line in _prose(lines) if line.startswith('# ')]
    for start, end in _sources(lines):
        count = sum(1 for n, line in _prose(lines) if start < n < end and re.match(r'^\d+[.)]\s', line))
        if count < 7:
            warnings.append(ValidationWarning(start, f'В списке источников {count}; нужно не менее 7 (п. 9.2)'))
    first_appendix = next((n for n, t in headings if re.match(r'(?i)приложение\s', t)), None)
    if first_appendix is not None:
        body = '\n'.join(line for n, line in _prose(lines) if n < first_appendix)
        for number, title in headings:
            letter = re.match(r'(?i)приложение\s+([А-ЯЁA-Z])', title)
            if letter and not re.search(r'Приложени\w*\s+' + letter.group(1).upper() + r'(?![А-ЯЁа-яё])', body):
                warnings.append(ValidationWarning(number, f'На Приложение {letter.group(1).upper()} нет ссылки в тексте (п. 10.6)'))
    return warnings
