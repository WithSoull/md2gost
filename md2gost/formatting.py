"""OOXML layout rules extracted from the Olenin diploma sample.

Only the bundled template gets this layout; user reference documents keep theirs.
Uses the standard library so installed CLI dependencies remain unchanged.
"""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
NS = {'w': W, 'm': M}

# One free line of body text (14 pt, 1.5 spacing) above and below a formula,
# ГОСТ 7.32-2017, 6.8.1. Spacing, not empty paragraphs.
EQUATION_SPACING = 480
# Cell padding: about 1 mm above and below; Word's default 0.19 cm at the sides.
CELL_MARGIN_Y = 57
CELL_MARGIN_X = 108
# Schema order of w:tblPr children: strict OOXML readers expect it.
TBLPR_ORDER = ['tblStyle', 'tblpPr', 'tblOverlap', 'bidiVisual', 'tblStyleRowBandSize',
               'tblStyleColBandSize', 'tblW', 'jc', 'tblCellSpacing', 'tblInd', 'tblBorders',
               'shd', 'tblLayout', 'tblCellMar', 'tblLook', 'tblCaption', 'tblDescription']


def tag(name: str) -> str:
    return f'{{{W}}}{name}'


def child(parent: ET.Element, name: str, **attrs: str) -> ET.Element:
    existing = parent.find(tag(name))
    if existing is None:
        existing = ET.SubElement(parent, tag(name))
    existing.attrib.update({tag(k): str(v) for k, v in attrs.items()})
    return existing


def properties(parent: ET.Element, name: str) -> ET.Element:
    existing = parent.find(tag(name))
    if existing is None:
        existing = ET.Element(tag(name))
        parent.insert(0, existing)
    return existing


def remove(parent: ET.Element, *names: str) -> None:
    for name in names:
        for item in parent.findall(tag(name)):
            parent.remove(item)


def parse(data: bytes) -> ET.Element:
    for _, (prefix, uri) in ET.iterparse(BytesIO(data), events=['start-ns']):
        if not re.fullmatch(r'ns\d+', prefix):
            ET.register_namespace(prefix, uri)
    return ET.fromstring(data)


def serialize(root: ET.Element, original: bytes) -> bytes:
    result = ET.tostring(root, encoding='unicode')
    # Keep declarations referenced by mc:Ignorable even if no element uses them.
    opening = original.decode('utf-8').split('>', 2)
    source = opening[1] if opening[0].startswith('<?xml') else opening[0]
    for prefix, uri in re.findall(r'xmlns:([\w]+)="([^"]+)"', source):
        if f'xmlns:{prefix}=' not in result:
            result = result.replace('>', f' xmlns:{prefix}="{uri}">', 1)
    return result.encode('utf-8')


def rewrite_package(path: Path, updates: dict[str, bytes]) -> None:
    buffer = BytesIO()
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(buffer, 'w') as target:
        for item in source.infolist():
            target.writestr(item, updates.get(item.filename, source.read(item.filename)))
    path.write_bytes(buffer.getvalue())


def font(rpr: ET.Element, size: int = 28, *, bold: bool = False,
         italic: bool = False, name: str = 'Times New Roman') -> None:
    remove(rpr, 'rFonts', 'b', 'bCs', 'i', 'iCs', 'caps', 'color', 'sz', 'szCs')
    child(rpr, 'rFonts', ascii=name, hAnsi=name, cs=name)
    child(rpr, 'sz', val=size)
    child(rpr, 'szCs', val=size)
    child(rpr, 'color', val='000000')
    child(rpr, 'b', val='1' if bold else '0')
    child(rpr, 'i', val='1' if italic else '0')


def paragraph(ppr: ET.Element, *, line: int = 360, first: int = 709,
              align: str = 'both', before: int = 0, after: int = 0,
              keep: bool = False, page: bool = False) -> None:
    remove(ppr, 'spacing', 'ind', 'jc', 'keepNext', 'keepLines', 'pageBreakBefore',
           'contextualSpacing', 'pBdr', 'shd')
    child(ppr, 'spacing', before=before, after=after, line=line, lineRule='auto')
    child(ppr, 'ind', left=0, right=0, firstLine=first)
    child(ppr, 'jc', val=align)
    child(ppr, 'keepNext', val='1' if keep else '0')
    child(ppr, 'pageBreakBefore', val='1' if page else '0')


def configure_styles(root: ET.Element) -> dict[str, str]:
    styles = {}
    for style in root.findall('w:style', NS):
        name = style.find('w:name', NS)
        if name is not None:
            styles[name.get(tag('val'), '').lower()] = style
    normal = styles['normal'].get(tag('styleId'))
    def configure(name: str, sid: str | None = None, **params) -> ET.Element:
        style = styles.get(name.lower())
        if style is None:
            style = ET.SubElement(root, tag('style'), {tag('type'): 'paragraph', tag('styleId'): sid or name})
            child(style, 'name', val=name)
            child(style, 'basedOn', val=normal)
            styles[name.lower()] = style
        size = params.pop('size', 28)
        bold = params.pop('bold', False)
        italic = params.pop('italic', False)
        fname = params.pop('font_name', 'Times New Roman')
        paragraph(properties(style, 'pPr'), **params)
        font(properties(style, 'rPr'), size, bold=bold, italic=italic, name=fname)
        return style
    for name in ['Normal', 'Body Text', 'First Paragraph', 'Compact', 'List Paragraph', 'Bibliography']:
        style = configure(name)
        child(properties(style, 'pPr'), 'suppressAutoHyphens', val='1')
    for level, size in [(1, 36), (2, 32), (3, 28), (4, 28), (5, 28), (6, 28)]:
        style = configure(f'heading {level}', size=size, bold=True,
                          before=0 if level == 1 else 480, after=240,
                          keep=True, page=level == 1)
        child(properties(style, 'pPr'), 'outlineLvl', val=level - 1)
    for name, sid, size, outline in [
        ('Structural Heading', 'GOSTStructuralHeading', 36, 0),
        ('Annotation Heading', 'GOSTAnnotationHeading', 36, 9),
        ('Appendix Heading', 'GOSTAppendixHeading', 28, 0),
        ('Appendix Title', 'GOSTAppendixTitle', 28, 9),
        ('TOC Heading', None, 36, 9),
    ]:
        style = configure(name, sid, size=size, bold=True, first=0, align='center',
                          after=240, keep=True, page=name != 'Appendix Title')
        child(properties(style, 'pPr'), 'outlineLvl', val=outline)
    configure('Table Caption', size=24, italic=True, line=240, first=0,
              align='left', before=120, after=120, keep=True)
    configure('Image Caption', size=24, bold=True, line=240, first=0,
              align='center', after=120)
    # Lines of the «где» explanation after a formula (gost-tables.lua).
    configure('Where', line=360, first=0, align='both', before=0, after=0)
    configure('Figure', line=240, first=0, align='center', keep=True)
    configure('Captioned Figure', line=240, first=0, align='center', keep=True)
    configure('Listing Caption', 'GOSTListingCaption', size=24, italic=True,
              line=240, first=0, align='left', before=120, keep=True)
    configure('Source Code', size=20, font_name='Courier New', line=240, first=0, align='left')
    for name, style in styles.items():
        if name.startswith('verbatim'):
            font(properties(style, 'rPr'), 20, name='Courier New')
    for level in range(1, 4):
        style = configure(f'toc {level}', f'GOSTTOC{level}', size=24,
                          line=240, first=0, align='left')
        ppr = properties(style, 'pPr')
        child(ppr, 'ind', left=(level - 1) * 283, firstLine=0)
        tabs = child(ppr, 'tabs')
        remove(tabs, 'tab')
        child(tabs, 'tab', val='right', leader='dot', pos=9638)
    configure('footer', size=24, line=240, first=0, align='center')
    # Prevent template or theme defaults from overriding the body baseline.
    defaults = child(root, 'docDefaults')
    font(child(child(defaults, 'rPrDefault'), 'rPr'))
    paragraph(child(child(defaults, 'pPrDefault'), 'pPr'))
    return {name: s.get(tag('styleId')) for name, s in styles.items()}


def page_setup(section: ET.Element, landscape: bool = False, start: int | None = None) -> None:
    remove(section, 'pgSz', 'pgMar', 'pgNumType', 'titlePg', 'headerReference')
    child(section, 'pgSz', w=16838 if landscape else 11906,
          h=11906 if landscape else 16838, orient='landscape' if landscape else 'portrait')
    child(section, 'pgMar', top=1701 if landscape else 1134, bottom=567 if landscape else 1134,
          left=1134 if landscape else 1701, right=1134 if landscape else 567,
          header=709, footer=709, gutter=0)
    if start is not None:
        child(section, 'pgNumType', start=start)


def section_widths(root: ET.Element) -> dict[ET.Element, int]:
    body = root.find('w:body', NS)
    widths = {}
    pending = []
    for block in body:
        pending.extend(block.iter(tag('p')))
        section = block if block.tag == tag('sectPr') else block.find('w:pPr/w:sectPr', NS)
        if section is not None:
            size, margin = section.find('w:pgSz', NS), section.find('w:pgMar', NS)
            width = int(size.get(tag('w'))) - int(margin.get(tag('left'))) - int(margin.get(tag('right'))) if size is not None and margin is not None else 9638
            for p in pending:
                widths[p] = width
            pending = []
    return widths


def fix_equations(root: ET.Element) -> None:
    widths = section_widths(root)
    for p in root.iter(tag('p')):
        wrap = p.find('m:oMathPara', NS)
        if wrap is None:
            continue
        math = wrap.find('m:oMath', NS)
        if math is None:
            continue
        runs = list(math)
        texts = [''.join(r.itertext()) for r in runs]
        if not texts or texts[-1] != ')':
            continue
        try:
            opening = len(texts) - 1 - list(reversed(texts[:-1])).index('(') - 1
        except ValueError:
            continue
        if opening == 0 or not texts[opening - 1].isspace():
            continue
        number_text = ''.join(texts[opening + 1:-1])
        if not re.fullmatch(r'(?:\d+|[A-Za-zА-Яа-яЁё]+)(?:\.\d+)*', number_text):
            continue
        for run in runs[opening - 1:]:
            math.remove(run)
        index = list(p).index(wrap)
        p.remove(wrap)
        p.insert(index, math)
        ppr = properties(p, 'pPr')
        paragraph(ppr, first=0, align='left', before=EQUATION_SPACING,
                  after=EQUATION_SPACING, keep=True)
        remove(ppr, 'tabs')
        tabs = child(ppr, 'tabs')
        width = widths.get(p, 9638)
        ET.SubElement(tabs, tag('tab'), {tag('val'): 'center', tag('pos'): str(width // 2)})
        ET.SubElement(tabs, tag('tab'), {tag('val'): 'right', tag('pos'): str(width)})
        tabrun = ET.Element(tag('r')); child(tabrun, 'tab')
        p.insert(list(p).index(math), deepcopy(tabrun))
        p.append(deepcopy(tabrun))
        number = ET.SubElement(p, tag('r'))
        font(child(number, 'rPr'))
        child(number, 't').text = f'({number_text})'


# Times New Roman advance widths in em, checked against the font metrics:
# the estimate stays within -7%..+15% of the real width of Russian words.
_WIDE_CHARS = set('жмшщыюфЖМШЩЫЮФmwMW')
_NARROW_CHARS = set('ilrtjfгI.,:;!|\'()[]')


def text_width(text: str, bold: bool = False) -> float:
    """Estimated width of 12 pt table text in twips."""
    em = 0.0
    for ch in text:
        if ch.isspace():
            em += 0.25
        elif ch in _WIDE_CHARS:
            em += 0.95 if ch.isupper() else 0.72
        elif ch in _NARROW_CHARS:
            em += 0.3
        elif ch.isupper():
            em += 0.7
        elif ch.isalnum():
            em += 0.5
        else:
            em += 0.4
    return em * 240 * (1.08 if bold else 1.0)


def cell_lines(cell: ET.Element) -> list[str]:
    """Visible text of a cell, one string per line, including math (m:t)."""
    lines = []
    for p in cell.iter(tag('p')):
        parts = []
        for item in p:
            if item.tag == tag('pPr'):
                continue
            for el in item.iter():
                if el.tag in (tag('t'), f'{{{M}}}t'):
                    parts.append(el.text or '')
                elif el.tag == tag('tab'):
                    parts.append(' ')
                elif el.tag in (tag('br'), tag('cr')):
                    parts.append('\n')
        lines.extend(''.join(parts).split('\n'))
    return lines


def fit_columns(table: ET.Element, width: int) -> None:
    """Size columns by content when Markdown left them equal.

    A column gets at least its longest word (bold in the header row) and at
    most its longest line; the columns together take the full text width.
    """
    grid = table.find('w:tblGrid', NS)
    cols = grid.findall('w:gridCol', NS) if grid is not None else []
    if not cols or len({c.get(tag('w')) for c in cols}) != 1:
        return
    n = len(cols)
    low, high = [0.0] * n, [0.0] * n
    rows = table.findall('w:tr', NS)
    for r, row in enumerate(rows):
        index = 0
        for cell in row.findall('w:tc', NS):
            span = cell.find('w:tcPr/w:gridSpan', NS)
            span = int(span.get(tag('val'), '1')) if span is not None else 1
            # Spanning cells do not decide the width of a single column.
            if span == 1 and index < n:
                for line in cell_lines(cell):
                    # A 10% margin absorbs the error of the width estimate.
                    word = max((text_width(w, r == 0) for w in line.split()), default=0.0)
                    low[index] = max(low[index], word * 1.1)
                    high[index] = max(high[index], text_width(line.strip(), r == 0))
            index += span
    pad = 2 * CELL_MARGIN_X
    low = [x + pad for x in low]
    high = [max(h + pad, l) for h, l in zip(high, low)]
    if sum(high) <= width:
        sizes = [h * width / sum(high) for h in high]
    elif sum(low) >= width:
        sizes = [l * width / sum(low) for l in low]
    else:
        # Auto table layout: interpolate between the narrowest and widest fit.
        share = (width - sum(low)) / (sum(high) - sum(low))
        sizes = [l + (h - l) * share for l, h in zip(low, high)]
    sizes = [int(s) for s in sizes]
    sizes[sizes.index(max(sizes))] += width - sum(sizes)
    for col, size in zip(cols, sizes):
        col.set(tag('w'), str(size))
    for row in rows:
        index = 0
        for cell in row.findall('w:tc', NS):
            tcpr = properties(cell, 'tcPr')
            span = tcpr.find('w:gridSpan', NS)
            span = int(span.get(tag('val'), '1')) if span is not None else 1
            remove(tcpr, 'tcW')
            tcw = ET.Element(tag('tcW'), {tag('w'): str(sum(sizes[index:index + span])),
                                          tag('type'): 'dxa'})
            # tcW follows only cnfStyle in the schema order of w:tcPr.
            tcpr.insert(1 if tcpr.find('w:cnfStyle', NS) is not None else 0, tcw)
            index += span
    tpr = properties(table, 'tblPr')
    child(tpr, 'tblW', w=width, type='dxa')
    child(tpr, 'tblLayout', type='autofit')


def populate_toc(body: ET.Element, toc: ET.Element, styles: dict[str, str]) -> None:
    """Cache heading labels, retaining a live TOC and PAGEREF fields for Word."""
    content = toc.find('w:sdtContent', NS)
    if content is None:
        return
    heading_ids = {styles[f'heading {level}']: level for level in range(1, 4)}
    heading_ids.update({styles['structural heading']: 1, styles['appendix heading']: 1})
    entries = []
    max_id = max((int(b.get(tag('id'), '0')) for b in body.iter(tag('bookmarkStart'))), default=0)
    for el in body:
        if el.tag != tag('p'):
            continue
        sid = el.find('w:pPr/w:pStyle', NS)
        level = heading_ids.get(sid.get(tag('val'))) if sid is not None else None
        if level is not None:
            text = ''.join(t.text or '' for t in el.iter(tag('t')))
            max_id += 1
            anchor = f'GOSTHeading{max_id}'
            start = ET.Element(tag('bookmarkStart'), {tag('id'): str(max_id), tag('name'): anchor})
            el.insert(1 if el.find('w:pPr', NS) is not None else 0, start)
            ET.SubElement(el, tag('bookmarkEnd'), {tag('id'): str(max_id)})
            entries.append((text, anchor, level))
    # Read the requested depth from the original field rather than assuming 3.
    instruction = next((t.text for t in content.iter(tag('instrText')) if 'TOC ' in (t.text or '')), None)
    depth_match = re.search(r'"1-(\d+)"', instruction or '')
    depth = int(depth_match.group(1)) if depth_match else 3
    heading = content.find('w:p', NS)
    for el in list(content):
        if el is not heading:
            content.remove(el)
    begin = ET.SubElement(content, tag('p'))
    child(properties(begin, 'pPr'), 'spacing', before=0, after=0, line=1, lineRule='exact')
    run = ET.SubElement(begin, tag('r'))
    ET.SubElement(run, tag('fldChar'), {tag('fldCharType'): 'begin', tag('dirty'): 'true'})
    child(run, 'instrText').text = instruction or 'TOC \\o "1-3" \\h \\z \\u'
    ET.SubElement(run, tag('fldChar'), {tag('fldCharType'): 'separate'})
    for text, anchor, level in entries:
        if level > depth:
            continue
        p = ET.SubElement(content, tag('p'))
        child(properties(p, 'pPr'), 'pStyle', val=styles[f'toc {level}'])
        link = child(p, 'hyperlink', anchor=anchor)
        child(child(link, 'r'), 't').text = text
        child(child(p, 'r'), 'tab')
        field = child(p, 'fldSimple', instr=f'PAGEREF "{anchor}" \\h', dirty='true')
        # Page numbers require the target editor's pagination; never guess them.
        child(child(field, 'r'), 't').text = '—'
    end = ET.SubElement(content, tag('p'))
    child(properties(end, 'pPr'), 'spacing', before=0, after=0, line=1, lineRule='exact')
    child(child(end, 'r'), 'fldChar', fldCharType='end')


def format_document(root: ET.Element, styles: dict[str, str], page_start: int) -> None:
    body = root.find('w:body', NS)
    section = body.find('w:sectPr', NS)
    # Empty metadata emitted by Pandoc must not turn into a blank title page.
    for el in list(body):
        if el.tag != tag('p'):
            if el.tag == tag('bookmarkStart'):
                continue
            break
        if ''.join(t.text or '' for t in el.iter(tag('t'))) or el.find('.//w:drawing', NS) is not None:
            break
        body.remove(el)
    heading_ids = {styles[f'heading {level}'] for level in range(1, 7)}
    toc = next((el for el in body.findall('w:sdt', NS)
                if any('TOC ' in (t.text or '') for t in el.iter(tag('instrText')))), None)
    if toc is not None:
        original_index = list(body).index(toc)
        body.remove(toc)
        destination = original_index
        annotation_found = False
        for i, el in enumerate(body):
            sid = el.find('w:pPr/w:pStyle', NS)
            text = ''.join(t.text or '' for t in el.iter(tag('t')))
            if sid is not None and sid.get(tag('val')) in heading_ids:
                if text == 'АННОТАЦИЯ':
                    annotation_found = True
                    continue
                if annotation_found:
                    destination = i
                    while destination > 0 and body[destination - 1].tag == tag('bookmarkStart'):
                        destination -= 1
                    break
        else:
            if annotation_found:
                destination = len(body) - 1
        body.insert(destination, toc)
    in_bibliography = False
    first_heading = True
    for el in list(body):
        ppr = el.find('w:pPr', NS)
        sid = ppr.find('w:pStyle', NS) if ppr is not None else None
        style_id = sid.get(tag('val')) if sid is not None else ''
        text = ''.join(t.text or '' for t in el.iter(tag('t')))
        if style_id in heading_ids:
            in_bibliography = text.startswith(('СПИСОК ИСПОЛЬЗ', 'СПИСОК ИСТОЧНИКОВ'))
            if style_id == styles['heading 1'] and not re.match(r'^\d+(?:\.\d+)*\s', text):
                name = ('appendix heading' if text.startswith('Приложение ') else
                        'annotation heading' if text == 'АННОТАЦИЯ' else 'structural heading')
                sid.set(tag('val'), styles[name])
            # A break before the very first content block can create a blank page.
            previous_content = any(x.tag in (tag('p'), tag('tbl'), tag('sdt')) for x in list(body)[:list(body).index(el)])
            if first_heading and not previous_content:
                child(ppr, 'pageBreakBefore', val='0')
            first_heading = False
        if ppr is not None and ppr.find('w:numPr', NS) is not None:
            level = ppr.find('w:numPr/w:ilvl', NS)
            depth = int(level.get(tag('val'), '0')) if level is not None else 0
            remove(ppr, 'ind')
            if in_bibliography:
                child(ppr, 'ind', left=0, firstLine=567)
            else:
                child(ppr, 'ind', left=1276 + depth * 567, hanging=567)
            child(ppr, 'spacing', before=0, after=0, line=360, lineRule='auto')
        if style_id in ('GOSTLandscapeStart', 'GOSTLandscapeEnd'):
            section_copy = deepcopy(section)
            page_setup(section_copy, landscape=style_id == 'GOSTLandscapeEnd')
            child(section_copy, 'type', val='nextPage')
            remove(ppr, 'pStyle')
            ppr.append(section_copy)
            child(ppr, 'spacing', before=0, after=0, line=1, lineRule='exact')
    if toc is not None:
        populate_toc(body, toc, styles)
    page_setup(section, start=page_start)
    fix_equations(root)
    # Start numbering on the first section, continue across landscape inserts.
    all_sections = list(body.iter(tag('sectPr')))
    for i, sect in enumerate(all_sections):
        remove(sect, 'pgNumType')
        if i == 0:
            child(sect, 'pgNumType', start=page_start)
    parents = {el: parent for parent in body.iter() for el in parent}
    text_widths = section_widths(root)
    for table in list(body.iter(tag('tbl'))):
        if any(p.find('w:pPr/w:pStyle', NS) is not None and
               p.find('w:pPr/w:pStyle', NS).get(tag('val')) == 'SourceCode'
               for p in table.iter(tag('p'))):
            continue
        # Raw listing tables carry explicit Courier New runs.
        if any(r.get(tag('ascii')) == 'Courier New' for r in table.iter(tag('rFonts'))):
            continue
        header = table.find('w:tr', NS)
        if header is not None:
            child(properties(header, 'trPr'), 'tblHeader')
        tpr = properties(table, 'tblPr')
        borders = child(tpr, 'tblBorders')
        for edge in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
            child(borders, edge, val='single', sz=4, color='000000')
        for p in table.iter(tag('p')):
            ppr = properties(p, 'pPr')
            child(ppr, 'spacing', before=0, after=0, line=240, lineRule='auto')
            child(ppr, 'ind', firstLine=0, left=0, right=0)
            # Justified text in narrow content-fitted columns stretches spaces.
            child(ppr, 'jc', val='left')
            child(ppr, 'keepNext', val='0')
            child(ppr, 'pageBreakBefore', val='0')
            for run in p.iter(tag('r')):
                rpr = properties(run, 'rPr')
                child(rpr, 'sz', val=24); child(rpr, 'szCs', val=24)
        if header is not None:
            for p in header.iter(tag('p')):
                child(properties(p, 'pPr'), 'jc', val='center')
            for run in header.iter(tag('r')):
                child(properties(run, 'rPr'), 'b', val='1')
        margins = child(tpr, 'tblCellMar')
        for edge, size in [('top', CELL_MARGIN_Y), ('left', CELL_MARGIN_X),
                           ('bottom', CELL_MARGIN_Y), ('right', CELL_MARGIN_X)]:
            child(margins, edge, w=size, type='dxa')
        if parents[table].tag != tag('tc'):
            first = table.find('.//w:p', NS)
            fit_columns(table, text_widths.get(first, 9638))
        names = [el.tag.split('}')[1] for el in tpr]
        rank = {n: TBLPR_ORDER.index(n) if n in TBLPR_ORDER else len(TBLPR_ORDER) for n in names}
        tpr[:] = sorted(tpr, key=lambda el: rank[el.tag.split('}')[1]])
        # Word has no table-level paragraph spacing. Put the gap on the next
        # paragraph, retaining a heading's larger spacing. Adjacent tables and
        # a table at the end need their own six-point spacer instead.
        parent = parents[table]
        index = list(parent).index(table) + 1
        following = next((el for el in list(parent)[index:]
                          if el.tag not in (tag('bookmarkStart'), tag('bookmarkEnd'))), None)
        if following is not None and following.tag == tag('p'):
            ppr = properties(following, 'pPr')
            sid = ppr.find('w:pStyle', NS)
            style_id = sid.get(tag('val')) if sid is not None else ''
            inherited = 480 if style_id in {styles[f'heading {n}'] for n in range(2, 7)} else 0
            spacing = child(ppr, 'spacing')
            before = int(spacing.get(tag('before'), inherited))
            child(ppr, 'spacing', before=max(before, 120))
        else:
            spacer = ET.Element(tag('p'))
            ppr = properties(spacer, 'pPr')
            paragraph(ppr, first=0, line=120)
            child(ppr, 'spacing', lineRule='exact')
            parent.insert(index, spacer)
    # Keep introductory text, images, captions and table captions together.
    blocks = [x for x in body if x.tag in (tag('p'), tag('tbl'))]
    for i, el in enumerate(blocks[:-1]):
        nxt = blocks[i + 1]
        sid = nxt.find('w:pPr/w:pStyle', NS)
        nxt_style = sid.get(tag('val')) if sid is not None else ''
        image = nxt.find('.//w:drawing', NS) is not None
        if el.tag == tag('p') and (image or nxt_style in
                (styles['table caption'], styles['image caption'], 'GOSTListingCaption')):
            child(properties(el, 'pPr'), 'keepNext', val='1')


def apply_sample_layout(path: Path, *, page_start: int = 1, template_only: bool = False) -> None:
    updates = {}
    with zipfile.ZipFile(path) as package:
        original = package.read('word/styles.xml')
        styles_root = parse(original)
        styles = configure_styles(styles_root)
        updates['word/styles.xml'] = serialize(styles_root, original)
        original = package.read('word/document.xml')
        root = parse(original)
        if template_only:
            for sect in root.iter(tag('sectPr')):
                page_setup(sect)
        else:
            format_document(root, styles, page_start)
        updates['word/document.xml'] = serialize(root, original)
        for name in package.namelist():
            if name.startswith('word/footer') and name.endswith('.xml'):
                original = package.read(name)
                footer = parse(original)
                for p in footer.iter(tag('p')):
                    paragraph(properties(p, 'pPr'), first=0, line=240, align='center')
                    for run in p.iter(tag('r')):
                        font(properties(run, 'rPr'), 24)
                updates[name] = serialize(footer, original)
        if 'word/numbering.xml' in package.namelist():
            original = package.read('word/numbering.xml')
            numbering = parse(original)
            for level in numbering.findall('.//w:lvl', NS):
                kind = level.find('w:numFmt', NS)
                if kind is not None and kind.get(tag('val')) == 'bullet':
                    child(level, 'lvlText', val='–')
                    child(properties(level, 'rPr'), 'rFonts', ascii='Times New Roman', hAnsi='Times New Roman')
            updates['word/numbering.xml'] = serialize(numbering, original)
        if 'word/settings.xml' in package.namelist():
            original = package.read('word/settings.xml')
            settings = parse(original)
            child(settings, 'updateFields', val='true')
            remove(settings, 'evenAndOddHeaders')
            updates['word/settings.xml'] = serialize(settings, original)
    rewrite_package(path, updates)
