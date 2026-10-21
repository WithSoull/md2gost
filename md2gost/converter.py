from __future__ import annotations

import re
import shutil
import subprocess
import time
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from .formatting import apply_sample_layout, fix_equations, parse, serialize, rewrite_package


BUILTIN_TEMPLATE = Path(__file__).parent / "templates" / "gost-7.32.docx"
UPPERCASE_H1_FILTER = Path(__file__).parent / "filters" / "uppercase-h1.lua"
GOST_TABLES_FILTER = Path(__file__).parent / "filters" / "gost-tables.lua"
APPENDIX_LISTING_FILTER = Path(__file__).parent / "filters" / "appendix-listing.lua"


class ConversionError(Exception):
    pass


@dataclass
class ConvertOptions:
    toc: bool = True
    toc_depth: int = 3
    title_page: bool = True
    page_start: int = 1


def check_dependencies() -> None:
    missing = [tool for tool in ("pandoc", "pandoc-crossref") if not shutil.which(tool)]
    if missing:
        raise RuntimeError(f"Не найдены в PATH: {', '.join(missing)}")


def build_command(
    input_path: Path,
    output_path: Path,
    template: Path,
    options: ConvertOptions,
) -> list[str]:
    cmd = [
        "pandoc",
        str(input_path),
        "--from", "markdown+lists_without_preceding_blankline",
        "--resource-path", str(input_path.resolve().parent),
        "--syntax-highlighting=none",
        "--reference-doc", str(template),
        "--lua-filter", str(UPPERCASE_H1_FILTER),
        "--lua-filter", str(GOST_TABLES_FILTER),
        "--lua-filter", str(APPENDIX_LISTING_FILTER),
        "--filter", "pandoc-crossref",
        "-M", "figureTitle=Рисунок",
        "-M", "titleDelim= – ",
        "-o", str(output_path),
    ]
    if options.toc:
        cmd += ["--toc", "--toc-depth", str(options.toc_depth), "-M", "toc-title=СОДЕРЖАНИЕ"]
    if not options.title_page:
        cmd += ["-M", "title=", "-M", "author=", "-M", "date="]
    return cmd


def _fix_equations(docx_path: Path) -> None:
    with zipfile.ZipFile(docx_path) as source:
        original = source.read("word/document.xml")
    root = parse(original)
    fix_equations(root)
    rewritten = serialize(root, original)
    if rewritten != original:
        rewrite_package(docx_path, {"word/document.xml": rewritten})


_BLOCK_RE = re.compile(r'<w:p\b[^>]*>.*?</w:p>|<w:tbl>.*?</w:tbl>', re.DOTALL)


def _add_keep_next(para_xml: str) -> str:
    ppr_end = para_xml.find("</w:pPr>")
    if ppr_end != -1:
        return para_xml[:ppr_end] + "<w:keepNext/>" + para_xml[ppr_end:]
    p_open_end = para_xml.find(">") + 1
    return para_xml[:p_open_end] + "<w:pPr><w:keepNext/></w:pPr>" + para_xml[p_open_end:]


def _fix_keep_with_media(docx_path: Path) -> None:
    with zipfile.ZipFile(docx_path, "r") as zin:
        doc_xml = zin.read("word/document.xml").decode("utf-8")

    blocks = [(m.start(), m.end(), m.group(0)) for m in _BLOCK_RE.finditer(doc_xml)]
    if not blocks:
        return

    replacements = []
    for i in range(len(blocks) - 1):
        cur_start, cur_end, cur = blocks[i]
        _, _, nxt = blocks[i + 1]

        if cur.startswith("<w:tbl>"):
            continue

        is_before_figure_table = nxt.startswith("<w:tbl>") and "FigureTable" in nxt
        is_before_figure_para = nxt.startswith("<w:p") and 'w:val="CaptionedFigure"' in nxt
        is_before_table_caption = nxt.startswith("<w:p") and 'w:val="TableCaption"' in nxt

        if (is_before_figure_table or is_before_figure_para or is_before_table_caption) and "<w:keepNext/>" not in cur:
            replacements.append((cur_start, cur_end, _add_keep_next(cur)))

    if not replacements:
        return

    parts = []
    prev = 0
    for start, end, new_block in replacements:
        parts.append(doc_xml[prev:start])
        parts.append(new_block)
        prev = end
    parts.append(doc_xml[prev:])
    new_xml = "".join(parts)

    buf = BytesIO()
    with zipfile.ZipFile(docx_path, "r") as zin, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == "word/document.xml":
                zout.writestr(item, new_xml.encode("utf-8"))
            else:
                zout.writestr(item, zin.read(item.filename))

    docx_path.write_bytes(buf.getvalue())


def convert(
    input_path: str | Path,
    output_path: str | Path | None = None,
    template: str | Path | None = None,
    options: ConvertOptions | None = None,
) -> tuple[Path, float]:
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path.with_suffix(".docx")
    output_path = Path(output_path)

    if template is None:
        template = BUILTIN_TEMPLATE
    template = Path(template)

    if options is None:
        options = ConvertOptions()

    if options.page_start < 1:
        raise ConversionError("Начальный номер страницы должен быть положительным")

    check_dependencies()

    cmd = build_command(input_path, output_path, template, options)

    t0 = time.monotonic()
    result = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.monotonic() - t0

    if result.returncode != 0:
        raise ConversionError(result.stderr.strip() or f"pandoc завершился с кодом {result.returncode}")

    if template.resolve() == BUILTIN_TEMPLATE.resolve():
        apply_sample_layout(output_path, page_start=options.page_start)
    else:
        _fix_equations(output_path)
        _fix_keep_with_media(output_path)

    return output_path, elapsed
