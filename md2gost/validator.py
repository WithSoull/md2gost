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
    warnings += _check_yaml_header(lines)
    warnings += _check_heading_levels(lines)
    warnings += _check_image_paths(lines, input_path.parent)
    warnings += _check_crossref_syntax(lines)
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
    ref_re = re.compile(r"@(fig|tbl|eq):(\w+)")
    anchor_re = re.compile(r"\{#(fig|tbl|eq):(\w+)\}")

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


def print_warnings(warnings: list[ValidationWarning]) -> None:
    if not warnings:
        return
    print(f"⚠  Предупреждения ({len(warnings)}):")
    for w in warnings:
        loc = f"[line {w.line}] " if w.line is not None else ""
        print(f"   {loc}{w.message}")
    print("✓  Конвертация продолжается...")
