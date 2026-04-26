from __future__ import annotations

import re
import shutil
import subprocess
import time
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path


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
        "--reference-doc", str(template),
        "--lua-filter", str(UPPERCASE_H1_FILTER),
        "--lua-filter", str(GOST_TABLES_FILTER),
        "--lua-filter", str(APPENDIX_LISTING_FILTER),
        "--filter", "pandoc-crossref",
        "-M", "figureTitle=Рисунок",
        "-M", "figPrefix=рис.",
        "-M", "titleDelim= – ",
        "-o", str(output_path),
    ]
    if options.toc:
        cmd += ["--toc", "--toc-depth", str(options.toc_depth), "-M", "toc-title=Содержание"]
    return cmd


_QQUAD_TAIL_RE = re.compile(
    r'<m:r><m:t>\s{2}</m:t></m:r>'
    r'<m:r><m:rPr><m:sty m:val="p"\s*/></m:rPr><m:t>\(</m:t></m:r>'
    r'<m:r><m:t>(\d+)</m:t></m:r>'
    r'<m:r><m:rPr><m:sty m:val="p"\s*/></m:rPr><m:t>\)</m:t></m:r>'
    r'</m:oMath>'
)

_OMATH_PARA_WRAP_RE = re.compile(
    r'<m:oMathPara><m:oMathParaPr><m:jc m:val="center"\s*/></m:oMathParaPr>'
    r'(.*?)'
    r'</m:oMathPara>'
)

_EQ_PARA_RE = re.compile(r'(<w:p\b[^>]*>)(.*?)(</w:p>)', re.DOTALL)

_TAB_STOPS = (
    '<w:tabs>'
    '<w:tab w:val="center" w:pos="4820"/>'
    '<w:tab w:val="right" w:pos="9639"/>'
    '</w:tabs>'
)
_TAB_RUN = '<w:r><w:tab/></w:r>'


def _fix_equations(docx_path: Path) -> None:
    with zipfile.ZipFile(docx_path, "r") as zin:
        doc_xml = zin.read("word/document.xml").decode("utf-8")

    if "<m:oMathPara>" not in doc_xml:
        return

    def _rewrite_para(m: re.Match) -> str:
        p_open, body, p_close = m.group(1), m.group(2), m.group(3)
        tail_match = _QQUAD_TAIL_RE.search(body)
        if not tail_match:
            return m.group(0)

        eq_num = tail_match.group(1)
        body = body[:tail_match.start()] + "</m:oMath>" + body[tail_match.end():]

        wrap_match = _OMATH_PARA_WRAP_RE.search(body)
        if wrap_match:
            omath = wrap_match.group(1)
            body = body[:wrap_match.start()] + omath + body[wrap_match.end():]

        ppr_close = "</w:pPr>"
        idx = body.find(ppr_close)
        if idx != -1:
            body = body[:idx] + _TAB_STOPS + ppr_close + _TAB_RUN + body[idx + len(ppr_close):]
        else:
            body = "<w:pPr>" + _TAB_STOPS + "</w:pPr>" + _TAB_RUN + body

        eq_num_run = (
            '<w:r><w:rPr>'
            '<w:sz w:val="28"/><w:szCs w:val="28"/>'
            '</w:rPr>'
            f'<w:t>({eq_num})</w:t></w:r>'
        )
        body = body + _TAB_RUN + eq_num_run

        return p_open + body + p_close

    new_xml = _EQ_PARA_RE.sub(
        lambda m: _rewrite_para(m) if "m:oMathPara" in m.group(2) else m.group(0),
        doc_xml,
    )

    if new_xml == doc_xml:
        return

    buf = BytesIO()
    with zipfile.ZipFile(docx_path, "r") as zin, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == "word/document.xml":
                zout.writestr(item, new_xml.encode("utf-8"))
            else:
                zout.writestr(item, zin.read(item.filename))

    docx_path.write_bytes(buf.getvalue())


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

    check_dependencies()

    cmd = build_command(input_path, output_path, template, options)

    t0 = time.monotonic()
    result = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.monotonic() - t0

    if result.returncode != 0:
        raise ConversionError(result.stderr.strip() or f"pandoc завершился с кодом {result.returncode}")

    _fix_equations(output_path)
    _fix_keep_with_media(output_path)

    return output_path, elapsed
