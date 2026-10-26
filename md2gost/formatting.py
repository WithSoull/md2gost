"""OOXML layout rules from ПРАВИЛА_ОФОРМЛЕНИЯ.docx.

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

# One empty line of body text above and below a formula (rules 5.2): Times New
# Roman 14 pt at 1.5 spacing advances 14 × 1.15 × 1.5 = 24.15 pt in Word and
# LibreOffice. Spacing, not empty paragraphs.
EQUATION_SPACING = 483
# «где» lines: symbols start at the body indent, one under another (rules 5.8).
WHERE_TAB = 709
# Cell padding: about 1 mm above and below; Word's default 0.19 cm at the sides.
CELL_MARGIN_Y = 57
CELL_MARGIN_X = 108
# Schema order of w:tblPr children: strict OOXML readers expect it.
TBLPR_ORDER = ['tblStyle', 'tblpPr', 'tblOverlap', 'bidiVisual', 'tblStyleRowBandSize',
               'tblStyleColBandSize', 'tblW', 'jc', 'tblCellSpacing', 'tblInd', 'tblBorders',
               'shd', 'tblLayout', 'tblCellMar', 'tblLook', 'tblCaption', 'tblDescription']
_MARGINS = ['top', 'start', 'left', 'bottom', 'end', 'right', 'insideH', 'insideV', 'tl2br', 'tr2bl']
# Child order of the ECMA-376 complex types this module edits. LibreOffice reads
# properties in any order, Word ignores or rejects those out of sequence.
SCHEMA_ORDER = {
    'style': ['name', 'aliases', 'basedOn', 'next', 'link', 'autoRedefine', 'hidden',
              'uiPriority', 'semiHidden', 'unhideWhenUsed', 'qFormat', 'locked', 'personal',
              'personalCompose', 'personalReply', 'rsid', 'pPr', 'rPr', 'tblPr', 'trPr',
              'tcPr', 'tblStylePr'],
    'pPr': ['pStyle', 'keepNext', 'keepLines', 'pageBreakBefore', 'framePr', 'widowControl',
            'numPr', 'suppressLineNumbers', 'pBdr', 'shd', 'tabs', 'suppressAutoHyphens',
            'kinsoku', 'wordWrap', 'overflowPunct', 'topLinePunct', 'autoSpaceDE',
            'autoSpaceDN', 'bidi', 'adjustRightInd', 'snapToGrid', 'spacing', 'ind',
            'contextualSpacing', 'mirrorIndents', 'suppressOverlap', 'jc', 'textDirection',
            'textAlignment', 'textboxTightWrap', 'outlineLvl', 'divId', 'cnfStyle', 'rPr',
            'sectPr', 'pPrChange'],
    'rPr': ['ins', 'del', 'moveFrom', 'moveTo', 'rStyle', 'rFonts', 'b', 'bCs', 'i', 'iCs',
            'caps', 'smallCaps', 'strike', 'dstrike', 'outline', 'shadow', 'emboss', 'imprint',
            'noProof', 'snapToGrid', 'vanish', 'webHidden', 'color', 'spacing', 'w', 'kern',
            'position', 'sz', 'szCs', 'highlight', 'u', 'effect', 'bdr', 'shd', 'fitText',
            'vertAlign', 'rtl', 'cs', 'em', 'lang', 'eastAsianLayout', 'specVanish', 'oMath',
            'rPrChange'],
    'tblPr': TBLPR_ORDER,
    'tcPr': ['cnfStyle', 'tcW', 'gridSpan', 'hMerge', 'vMerge', 'tcBorders', 'shd', 'noWrap',
             'tcMar', 'textDirection', 'tcFitText', 'vAlign', 'hideMark', 'headers', 'cellIns',
             'cellDel', 'cellMerge', 'tcPrChange'],
    'sectPr': ['headerReference', 'footerReference', 'footnotePr', 'endnotePr', 'type', 'pgSz',
               'pgMar', 'paperSrc', 'pgBorders', 'lnNumType', 'pgNumType', 'cols', 'formProt',
               'vAlign', 'noEndnote', 'titlePg', 'textDirection', 'bidi', 'rtlGutter',
               'docGrid', 'printerSettings', 'sectPrChange'],
    'tblBorders': _MARGINS, 'tcBorders': _MARGINS, 'tblCellMar': _MARGINS, 'tcMar': _MARGINS,
    'lvl': ['start', 'numFmt', 'lvlRestart', 'pStyle', 'isLgl', 'suff', 'lvlText',
            'lvlPicBulletId', 'legacy', 'lvlJc', 'pPr', 'rPr'],
    'docDefaults': ['rPrDefault', 'pPrDefault'],
    'settings': ['writeProtection', 'view', 'zoom', 'removePersonalInformation',
                 'removeDateAndTime', 'doNotDisplayPageBoundaries', 'displayBackgroundShape',
                 'printPostScriptOverText', 'printFractionalCharacterWidth', 'printFormsData',
                 'embedTrueTypeFonts', 'embedSystemFonts', 'saveSubsetFonts', 'saveFormsData',
                 'mirrorMargins', 'alignBordersAndEdges', 'bordersDoNotSurroundHeader',
                 'bordersDoNotSurroundFooter', 'gutterAtTop', 'hideSpellingErrors',
                 'hideGrammaticalErrors', 'activeWritingStyle', 'proofState', 'formsDesign',
                 'attachedTemplate', 'linkStyles', 'stylePaneFormatFilter',
                 'stylePaneSortMethod', 'documentType', 'mailMerge', 'revisionView',
                 'trackRevisions', 'doNotTrackMoves', 'doNotTrackFormatting',
                 'documentProtection', 'autoFormatOverride', 'styleLockTheme',
                 'styleLockQFSet', 'defaultTabStop', 'autoHyphenation',
                 'consecutiveHyphenLimit', 'hyphenationZone', 'doNotHyphenateCaps',
                 'showEnvelope', 'summaryLength', 'clickAndTypeStyle', 'defaultTableStyle',
                 'evenAndOddHeaders', 'bookFoldRevPrinting', 'bookFoldPrinting',
                 'bookFoldPrintingSheets', 'drawingGridHorizontalSpacing',
                 'drawingGridVerticalSpacing', 'displayHorizontalDrawingGridEvery',
                 'displayVerticalDrawingGridEvery', 'doNotUseMarginsForDrawingGridOrigin',
                 'drawingGridHorizontalOrigin', 'drawingGridVerticalOrigin',
                 'doNotShadeFormData', 'noPunctuationKerning', 'characterSpacingControl',
                 'printTwoOnOne', 'strictFirstAndLastChars', 'noLineBreaksAfter',
                 'noLineBreaksBefore', 'savePreviewPicture', 'doNotValidateAgainstSchema',
                 'saveInvalidXml', 'ignoreMixedContent', 'alwaysShowPlaceholderText',
                 'doNotDemarcateInvalidXml', 'saveXmlDataOnly', 'useXSLTWhenSaving',
                 'saveThroughXslt', 'showXMLTags', 'alwaysMergeEmptyNamespace', 'updateFields',
                 'hdrShapeDefaults', 'footnotePr', 'endnotePr', 'compat', 'docVars', 'rsids',
                 'mathPr', 'attachedSchema', 'themeFontLang', 'clrSchemeMapping',
                 'doNotIncludeSubdocsInStats', 'doNotAutoCompressPictures', 'forceUpgrade',
                 'captions', 'readModeInkLockDown', 'smartTagType', 'schemaLibrary',
                 'shapeDefaults', 'doNotEmbedSmartTags', 'decimalSymbol', 'listSeparator'],
}
# Choice groups: members share a position and keep their relative order.
_SAME_RANK = {'footerReference': 'headerReference', 'left': 'start', 'right': 'end'}


def normalize_order(root: ET.Element) -> None:
    """Sort children of known WordprocessingML types into schema order."""
    for el in root.iter():
        name = el.tag.rpartition('}')[2]
        order = SCHEMA_ORDER.get(name)
        if order is None or not el.tag.startswith(f'{{{W}}}') or len(el) < 2:
            continue
        def rank(item: ET.Element) -> int:
            local = item.tag.rpartition('}')[2]
            local = _SAME_RANK.get(local, local)
            # Foreign extensions go last, where the schema allows them.
            return order.index(local) if item.tag.startswith(f'{{{W}}}') and local in order else len(order)
        el[:] = sorted(el, key=rank)


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


# Word extensions a part may list in mc:Ignorable.
EXTENSIONS = {
    'w14': 'http://schemas.microsoft.com/office/word/2010/wordml',
    'wp14': 'http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing',
    'w15': 'http://schemas.microsoft.com/office/word/2012/wordml',
    'w16se': 'http://schemas.microsoft.com/office/word/2015/wordml/symex',
    'w16cid': 'http://schemas.microsoft.com/office/word/2016/wordml/cid',
    'w16': 'http://schemas.microsoft.com/office/word/2018/wordml',
    'w16cex': 'http://schemas.microsoft.com/office/word/2018/wordml/cex',
    'w16sdtdh': 'http://schemas.microsoft.com/office/word/2020/wordml/sdtdatahash',
    'w16du': 'http://schemas.microsoft.com/office/word/2023/wordml/word16du',
    'w16sdtfl': 'http://schemas.microsoft.com/office/word/2024/wordml/sdtformatlock',
}


def serialize(root: ET.Element, original: bytes) -> bytes:
    normalize_order(root)
    result = ET.tostring(root, encoding='unicode')
    end = result.index('>')
    head, rest = result[:end], result[end:]
    # ElementTree drops declarations no element uses; mc:Ignorable still names them.
    opening = original.decode('utf-8').split('>', 2)
    source = opening[1] if opening[0].startswith('<?xml') else opening[0]
    declared = dict(re.findall(r'xmlns:(\w+)="([^"]+)"', source))
    for prefix, uri in declared.items():
        if f'xmlns:{prefix}=' not in head:
            head += f' xmlns:{prefix}="{uri}"'
    # Word rejects a part whose mc:Ignorable names an undeclared prefix
    # («unreadable content»): declare known extensions, drop the rest.
    ignorable = re.search(r'(\w+):Ignorable="([^"]*)"', head)
    if ignorable:
        kept = []
        for prefix in ignorable.group(2).split():
            if f'xmlns:{prefix}=' not in head and prefix in EXTENSIONS:
                head += f' xmlns:{prefix}="{EXTENSIONS[prefix]}"'
            if f'xmlns:{prefix}=' in head:
                kept.append(prefix)
        head = head.replace(ignorable.group(0), f'{ignorable.group(1)}:Ignorable="{" ".join(kept)}"')
    return (head + rest).encode('utf-8')


def rewrite_package(path: Path, updates: dict[str, bytes]) -> None:
    buffer = BytesIO()
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(buffer, 'w') as target:
        for item in source.infolist():
            target.writestr(item, updates.get(item.filename, source.read(item.filename)))
    path.write_bytes(buffer.getvalue())


def font(rpr: ET.Element, size: int = 28, *, bold: bool = False,
         italic: bool = False, name: str = 'Times New Roman', caps: bool = False) -> None:
    remove(rpr, 'rFonts', 'b', 'bCs', 'i', 'iCs', 'caps', 'color', 'sz', 'szCs')
    child(rpr, 'rFonts', ascii=name, hAnsi=name, cs=name, eastAsia=name)
    child(rpr, 'sz', val=size)
    child(rpr, 'szCs', val=size)
    child(rpr, 'color', val='000000')
    child(rpr, 'b', val='1' if bold else '0')
    child(rpr, 'bCs', val='1' if bold else '0')
    child(rpr, 'i', val='1' if italic else '0')
    child(rpr, 'iCs', val='1' if italic else '0')
    # «Видоизменение: все прописные» is a font effect, not only uppercase text.
    if caps:
        child(rpr, 'caps', val='1')


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
    child(ppr, 'widowControl', val='1')
    child(ppr, 'suppressAutoHyphens', val='1')
    if keep:
        child(ppr, 'keepLines', val='1')


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
        caps = params.pop('caps', False)
        fname = params.pop('font_name', 'Times New Roman')
        paragraph(properties(style, 'pPr'), **params)
        font(properties(style, 'rPr'), size, bold=bold, italic=italic, name=fname, caps=caps)
        return style
    for name in ['Normal', 'Body Text', 'First Paragraph', 'Compact', 'List Paragraph', 'Bibliography']:
        style = configure(name)
        child(properties(style, 'pPr'), 'suppressAutoHyphens', val='1')
    # Table 2.1: chapters 18 pt caps from a new page, sections 16 pt, items 14 pt.
    for level, size in [(1, 36), (2, 32), (3, 28), (4, 28), (5, 28), (6, 28)]:
        style = configure(f'heading {level}', size=size, bold=True, caps=level == 1,
                          before=0 if level == 1 else 480, after=240,
                          keep=True, page=level == 1)
        child(properties(style, 'pPr'), 'outlineLvl', val=level - 1)
    # 2.6.7: unnumbered parts use the first-level heading, centered (no indent).
    # 10.7: «Приложение А» as a third-level heading from a new page, its title
    # in body text; sections «Приложение А.1» (10.4) continue on the same page.
    for name, sid, size, outline in [
        ('Structural Heading', 'GOSTStructuralHeading', 36, 0),
        ('Annotation Heading', 'GOSTAnnotationHeading', 36, 9),
        ('Appendix Heading', 'GOSTAppendixHeading', 28, 0),
        ('Appendix Section', 'GOSTAppendixSection', 28, 9),
        ('Appendix Title', 'GOSTAppendixTitle', 28, 9),
        ('TOC Heading', None, 36, 9),
    ]:
        appendix = name.startswith('Appendix')
        style = configure(name, sid, size=size, bold=name != 'Appendix Title',
                          caps=not appendix, first=0, align='center',
                          after=0 if appendix else 240, keep=True,
                          page=name in ('Structural Heading', 'Annotation Heading',
                                        'Appendix Heading', 'TOC Heading'))
        child(properties(style, 'pPr'), 'outlineLvl', val=outline)
    # Table 9.1: rubrics inside the list of sources.
    configure('Bibliography Heading', 'GOSTBibliographyHeading', caps=True, first=0,
              align='center', before=120, after=120, keep=True)
    child(properties(styles['bibliography heading'], 'pPr'), 'ind', left=709, right=0, firstLine=0)
    configure('Table Caption', size=24, italic=True, line=240, first=0,
              align='both', before=120, after=0, keep=True)
    configure('Image Caption', size=24, bold=True, line=240, first=0,
              align='center', after=120)
    # Lines of the «где» explanation after a formula (gost-tables.lua): «где»,
    # then a tab, so that every symbol starts at WHERE_TAB.
    where = configure('Where', line=360, first=0, align='both', before=0, after=0)
    child(child(properties(where, 'pPr'), 'tabs'), 'tab', val='left', pos=WHERE_TAB)
    configure('Figure', line=240, first=0, align='center', keep=True)
    configure('Captioned Figure', line=240, first=0, align='center', keep=True)
    # Table 8.1 asks for a new page like table captions; the rules' own example
    # (Приложение А.3) and 1.7 keep listings right after the text.
    configure('Listing Caption', 'GOSTListingCaption', size=24, italic=True,
              line=240, first=0, align='left', before=120, keep=True)
    configure('Source Code', size=20, font_name='Courier New', line=240, first=0, align='left')
    for name, style in styles.items():
        if name.startswith('verbatim'):
            font(properties(style, 'rPr'), 20, name='Courier New')
    for name in ['hyperlink', 'followedhyperlink']:
        if name in styles:
            rpr = properties(styles[name], 'rPr')
            remove(rpr, 'color', 'u')
            child(rpr, 'color', val='000000')
            child(rpr, 'u', val='none')
    for level in range(1, 4):
        style = configure(f'toc {level}', f'GOSTTOC{level}', size=28,
                          line=360, first=0, align='center' if level == 1 else 'both')
        ppr = properties(style, 'pPr')
        child(ppr, 'ind', left=0, right=360, firstLine=0)
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
    parents = {el: parent for parent in root.iter() for el in parent}
    for p in list(root.iter(tag('p'))):
        wrap = p.find('m:oMathPara', NS)
        if wrap is None:
            continue
        siblings = list(parents[p])
        following = siblings[siblings.index(p) + 1] if siblings.index(p) + 1 < len(siblings) else None
        # A formula never ends a page apart from its «где» explanation.
        keep = following is not None and following.find("w:pPr/w:pStyle[@w:val='Where']", NS) is not None
        ppr = properties(p, 'pPr')
        paragraph(ppr, first=0, align='center', before=EQUATION_SPACING,
                  after=EQUATION_SPACING, keep=keep)
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
                  after=EQUATION_SPACING, keep=keep)
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
    """Size columns by content when Markdown left them equal (rules 6.4).

    A column gets at least its longest word (bold in the header row) and at
    most its longest line. Like Word's «Автоподбор по содержимому», a table
    whose lines all fit stays narrower than the text; a wider one takes the
    full text width and wraps its longest cells.
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
                    word = max((text_width(w, r == 0) for w in re.split(r'[\s/–—-]+', line)), default=0.0)
                    low[index] = max(low[index], word * 1.1)
                    high[index] = max(high[index], text_width(line.strip(), r == 0))
            index += span
    pad = 2 * CELL_MARGIN_X
    low = [x + pad for x in low]
    high = [max(h + pad, l) for h, l in zip(high, low)]
    if sum(high) <= width:
        # A 5% reserve absorbs underestimated text widths.
        sizes = [min(h * 1.05, h + (width - sum(high)) / n) for h in high]
    elif sum(low) >= width:
        sizes = [l * width / sum(low) for l in low]
    else:
        # Auto table layout: interpolate between the narrowest and widest fit.
        share = (width - sum(low)) / (sum(high) - sum(low))
        sizes = [l + (h - l) * share for l, h in zip(low, high)]
    sizes = [int(s) for s in sizes]
    if sum(high) > width:
        sizes[sizes.index(max(sizes))] += width - sum(sizes)
    width = sum(sizes)
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
    in_appendix = False
    for el in body:
        if el.tag != tag('p'):
            continue
        sid = el.find('w:pPr/w:pStyle', NS)
        style_id = sid.get(tag('val')) if sid is not None else None
        level = heading_ids.get(style_id)
        if style_id in (styles['structural heading'], styles['appendix heading']):
            in_appendix = style_id == styles['appendix heading']
        # Inside appendices only «Приложение А» itself is listed.
        elif in_appendix:
            level = None
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


def add_table_gap(table: ET.Element, parents: dict, styles: dict) -> None:
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


def split_table(table: ET.Element, breaks: list[int], caption: str,
                caption_style: str) -> list[ET.Element]:
    """Explicit page cuts after body rows; never estimate pagination from text length."""
    rows = table.findall('w:tr', NS)
    header_count = 0
    for row in rows:
        if row.find('w:trPr/w:tblHeader', NS) is None:
            break
        header_count += 1
    total = len(rows) - header_count
    if not breaks or breaks != sorted(set(breaks)) or any(n < 1 or n >= total for n in breaks):
        raise ValueError('break-after: номера должны возрастать и быть меньше числа строк данных')
    number = re.match(r'(Таблица|Листинг)\s+(\S+)', caption)
    if number is None:
        raise ValueError('break-after: таблице нужна нумерованная подпись')
    # Rules 6.3: «Продолжение Таблицы 6.1» in the caption style; listings alike.
    word = {'Таблица': 'Таблицы', 'Листинг': 'Листинга'}[number.group(1)]
    continuation = f'Продолжение {word} {number.group(2)}'
    blocks = []
    start = 0
    for part, end in enumerate(breaks + [total]):
        fragment = deepcopy(table)
        for row in fragment.findall('w:tr', NS):
            fragment.remove(row)
        selected = rows[:header_count] + rows[header_count + start:header_count + end]
        for row in selected:
            copy = deepcopy(row)
            if part and row in rows[:header_count]:
                for parent in copy.iter():
                    remove(parent, 'bookmarkStart', 'bookmarkEnd')
            fragment.append(copy)
        if part:
            p = ET.Element(tag('p'))
            ppr = properties(p, 'pPr')
            child(ppr, 'pStyle', val=caption_style)
            child(ppr, 'pageBreakBefore', val='1')
            child(ppr, 'keepNext', val='1')
            child(child(p, 'r'), 't').text = continuation
            blocks.append(p)
        if end < total:
            # A cell border wins over tblBorders, which is normalized later.
            for cell in fragment.findall('w:tr', NS)[-1].findall('w:tc', NS):
                child(child(properties(cell, 'tcPr'), 'tcBorders'), 'bottom', val='nil')
        blocks.append(fragment)
        start = end
    return blocks


def apply_table_breaks(body: ET.Element, styles: dict[str, str]) -> None:
    for parent in list(body.iter()):
        pending = None
        caption, caption_style = '', styles['table caption']
        for block in list(parent):
            sid = block.find('w:pPr/w:pStyle', NS)
            value = sid.get(tag('val')) if sid is not None else ''
            if value == 'GOSTTableBreaks':
                pending = [int(x) for x in re.findall(r'\d+', ''.join(block.itertext()))]
                parent.remove(block)
            elif value in (styles['table caption'], styles['listing caption']):
                caption, caption_style = ''.join(block.itertext()), value
            elif block.tag == tag('tbl') and pending is not None:
                parts = split_table(block, pending, caption, caption_style)
                index = list(parent).index(block)
                parent.remove(block)
                for offset, part in enumerate(parts):
                    parent.insert(index + offset, part)
                pending = None


def fit_figures(root: ET.Element) -> None:
    """Keep drawings inside text width and leave room for introduction/caption.

    19 cm is a layout choice for portrait pages, not a rule in the source.
    Never upscale an image. DrawingML extents use EMU (635 per twip).
    """
    widths = section_widths(root)
    wp = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
    drawing = 'http://schemas.openxmlformats.org/drawingml/2006/main'
    blocks = root.findall('w:body/w:p', NS)
    for p in root.iter(tag('p')):
        width = widths.get(p, 9638) * 635
        # Landscape: its shorter vertical area needs a lower cap.
        height_cm = 14 if widths.get(p, 9638) > 9638 else 19
        if p in blocks:
            index = blocks.index(p)
            preceding = blocks[max(0, index - 2):index]
            if any(re.match(r'^\d+(?:\.\d+)+\s', ''.join(t.text or '' for t in el.iter(tag('t'))))
                   for el in preceding):
                height_cm = min(height_cm, 17.5)
        height = height_cm * 360000
        for inline in p.findall('.//{' + wp + '}inline'):
            extent = inline.find('{' + wp + '}extent')
            if extent is None:
                continue
            cx, cy = int(extent.get('cx', '0')), int(extent.get('cy', '0'))
            if cx <= 0 or cy <= 0:
                continue
            factor = min(1, width / cx, height / cy)
            if factor < 1:
                for size in [extent] + inline.findall('.//{' + drawing + '}xfrm/{' + drawing + '}ext'):
                    size.set('cx', str(round(cx * factor)))
                    size.set('cy', str(round(cy * factor)))


def format_document(root: ET.Element, styles: dict[str, str], page_start: int) -> None:
    body = root.find('w:body', NS)
    apply_table_breaks(body, styles)
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
                child(ppr, 'ind', left=0, firstLine=709)
            else:
                child(ppr, 'ind', left=1276 + depth * 567, hanging=567)
                tabs = child(ppr, 'tabs')
                remove(tabs, 'tab')
                child(tabs, 'tab', val='num', pos=1276 + depth * 567)
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
    fit_figures(root)
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
            add_table_gap(table, parents, styles)
            continue
        # Raw listing tables carry explicit Courier New runs.
        if any(r.get(tag('ascii')) == 'Courier New' for r in table.iter(tag('rFonts'))):
            add_table_gap(table, parents, styles)
            continue
        header = table.find('w:tr', NS)
        if header is not None:
            child(properties(header, 'trPr'), 'tblHeader')
        tpr = properties(table, 'tblPr')
        child(tpr, 'jc', val='center')
        borders = child(tpr, 'tblBorders')
        for edge in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
            child(borders, edge, val='single', sz=4, color='000000')
        for p in table.iter(tag('p')):
            ppr = properties(p, 'pPr')
            child(ppr, 'spacing', before=0, after=0, line=240, lineRule='auto')
            child(ppr, 'ind', firstLine=0, left=0, right=0)
            # Row labels are left aligned; remaining data cells follow Table 6.1.
            child(ppr, 'jc', val='both')
            child(ppr, 'suppressAutoHyphens', val='1')
            child(ppr, 'keepNext', val='0')
            child(ppr, 'pageBreakBefore', val='0')
            for run in p.iter(tag('r')):
                rpr = properties(run, 'rPr')
                child(rpr, 'sz', val=24); child(rpr, 'szCs', val=24)
        for row in table.findall('w:tr', NS):
            child(properties(row, 'trPr'), 'cantSplit')
            first_cell = row.find('w:tc', NS)
            if first_cell is not None:
                for p in first_cell.iter(tag('p')):
                    child(properties(p, 'pPr'), 'jc', val='left')
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
        add_table_gap(table, parents, styles)
    # A figure stays with its caption. The paragraph that mentions it is not
    # kept with the figure: rules 1.14 allow the figure on the next page, and a
    # heading, a long introduction and a tall figure chained together exceed a
    # page, so Word moves the chain and leaves empty space on two pages.
    blocks = [x for x in body if x.tag in (tag('p'), tag('tbl'))]
    for i, el in enumerate(blocks[:-1]):
        nxt = blocks[i + 1]
        sid = nxt.find('w:pPr/w:pStyle', NS)
        nxt_style = sid.get(tag('val')) if sid is not None else ''
        if el.find('.//w:drawing', NS) is not None and nxt_style == styles['image caption']:
            child(properties(el, 'pPr'), 'keepNext', val='1')


def apply_rules_layout(path: Path, *, page_start: int = 1, template_only: bool = False) -> None:
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
                depth = int(level.get(tag('ilvl'), '0'))
                ppr = properties(level, 'pPr')
                remove(ppr, 'ind', 'tabs')
                child(ppr, 'ind', left=1276 + depth * 567, hanging=567)
                child(child(ppr, 'tabs'), 'tab', val='num', pos=1276 + depth * 567)
                child(level, 'suff', val='tab')
                kind = level.find('w:numFmt', NS)
                if kind is not None and kind.get(tag('val')) == 'bullet':
                    child(level, 'lvlText', val='–')
                    child(properties(level, 'rPr'), 'rFonts', ascii='Times New Roman', hAnsi='Times New Roman')
            updates['word/numbering.xml'] = serialize(numbering, original)
        if 'word/settings.xml' in package.namelist():
            original = package.read('word/settings.xml')
            settings = parse(original)
            child(settings, 'updateFields', val='true')
            child(settings, 'autoHyphenation', val='false')
            remove(settings, 'evenAndOddHeaders')
            updates['word/settings.xml'] = serialize(settings, original)
    rewrite_package(path, updates)
