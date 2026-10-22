from __future__ import annotations

import sys
from pathlib import Path

import click

from .converter import ConversionError, ConvertOptions, convert
from .validator import ValidationError, print_warnings, validate
from .watcher import watch as _watch


def _make_options(toc_depth: int, no_toc: bool, no_title_page: bool, page_start: int = 1, paginate: bool = False,
                  libreoffice: str | None = None, keep_order: bool = False) -> ConvertOptions:
    return ConvertOptions(
        toc=not no_toc,
        toc_depth=toc_depth,
        title_page=not no_title_page,
        page_start=page_start,
        paginate=paginate,
        libreoffice=libreoffice,
        move_text=not keep_order,
    )


_shared_options = [
    click.argument("input_file", type=click.Path(exists=True, dir_okay=False)),
    click.option("-o", "--output", "output", type=click.Path(), default=None,
                 help="Путь для сохранения .docx (по умолчанию рядом с входным файлом)"),
    click.option("-t", "--template", "template", type=click.Path(exists=True), default=None,
                 help="Свой reference.docx шаблон"),
    click.option("--toc-depth", type=click.IntRange(1, 3), default=3, show_default=True,
                 help="Глубина оглавления"),
    click.option("--no-toc", is_flag=True, default=False,
                 help="Отключить оглавление"),
    click.option("--no-title-page", is_flag=True, default=False,
                 help="Не добавлять титульный блок из title, author и date"),
    click.option("--page-start", type=click.IntRange(min=1), default=1, show_default=True,
                 help="Начальный номер страницы для встроенного шаблона"),
    click.option("--paginate", is_flag=True, help="Финальная вёрстка через LibreOffice: продолжения таблиц и номера оглавления"),
    click.option("--libreoffice", type=click.Path(exists=True, dir_okay=False), default=None,
                 help="Исполняемый файл soffice для --paginate"),
    click.option("--keep-order", is_flag=True, default=False,
                 help="С --paginate не переносить абзацы перед рисунками, только уменьшать рисунки"),
    click.option("--no-validate", is_flag=True, default=False,
                 help="Пропустить валидацию"),
]


def _apply_options(func):
    for option in reversed(_shared_options):
        func = option(func)
    return func


@click.group()
def cli() -> None:
    pass


@cli.command("convert")
@_apply_options
def convert_cmd(
    input_file: str,
    output: str | None,
    template: str | None,
    toc_depth: int,
    no_toc: bool,
    no_title_page: bool,
    page_start: int,
    no_validate: bool,
    paginate: bool,
    libreoffice: str | None,
    keep_order: bool,
) -> None:
    """Конвертировать Markdown в DOCX по ГОСТ 7.32."""
    input_path = Path(input_file)
    output_path = Path(output) if output else None

    if not no_validate:
        try:
            warnings = validate(input_path)
            print_warnings(warnings)
        except ValidationError as exc:
            click.echo(f"✗ Ошибка валидации: {exc}", err=True)
            sys.exit(1)

    try:
        out, elapsed = convert(
            input_path,
            output_path,
            template,
            _make_options(toc_depth, no_toc, no_title_page, page_start, paginate, libreoffice, keep_order),
        )
        click.echo(f"✓ {out} готов ({elapsed:.1f}s)")
    except ConversionError as exc:
        click.echo(f"✗ Ошибка конвертации:\n{exc}", err=True)
        sys.exit(1)
    except RuntimeError as exc:
        click.echo(f"✗ {exc}", err=True)
        sys.exit(1)


@cli.command("watch")
@_apply_options
def watch_cmd(
    input_file: str,
    output: str | None,
    template: str | None,
    toc_depth: int,
    no_toc: bool,
    no_title_page: bool,
    page_start: int,
    no_validate: bool,
    paginate: bool,
    libreoffice: str | None,
    keep_order: bool,
) -> None:
    """Следить за файлом и конвертировать при каждом изменении."""
    _watch(
        input_path=input_file,
        output_path=output,
        template=template,
        options=_make_options(toc_depth, no_toc, no_title_page, page_start, paginate, libreoffice, keep_order),
        no_validate=no_validate,
    )
