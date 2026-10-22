"""Final layout measured in LibreOffice.

Each pass exports a PDF of a draft in which every body block and every table
row carries a bookmark. LibreOffice turns bookmarks into named destinations
with the page and the vertical position, so nothing is guessed from text. The
earliest page with a defect is fixed, then the document is measured again:

* a table or listing that crosses a page is cut there and continues under
  «Продолжение Таблицы N» with the header repeated (rules 6.3);
* a figure pushed to the next page together with its introduction, leaving a
  large empty area (rules 1.7), is reduced slightly when that is enough;
  otherwise the following text paragraphs move before it and the figure opens
  the next page, as rules 1.14 allow.

TOC page numbers come from the heading bookmarks. No macros are used, and the
DOCX is never re-saved by LibreOffice: Pandoc's styles and formulas stay intact.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from .formatting import M, NS, child, parse, rewrite_package, serialize, split_table, tag

WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
MARK = 'md2gostB'
# Portrait A4 with 20 mm top and bottom margins, in PDF points from the bottom.
PAGE_TOP = 841.89 - 56.7
PAGE_BOTTOM = 56.7
LINE = 24.15
# Below the baseline of the last line: descent of 14 pt Times New Roman.
DESCENT = 3.5
# Four empty body lines at a page end count as a gap (rules 1.7).
GAP = 4 * LINE
# A figure may shrink to this share of its size to stay with its introduction.
MIN_SCALE = 0.8
# A stronger reduction is still better than an empty third of a page.
LOW_SCALE = 0.75
BODY_STYLES = ('normal', 'body text', 'first paragraph', 'compact')
PAGE_STYLES = ('heading 1', 'structural heading', 'annotation heading', 'appendix heading')
EXPORT = 'pdf:writer_pdf_Export:{"ExportBookmarksToPDFDestination":{"type":"boolean","value":"true"}}'


class PaginationError(RuntimeError):
    pass


def visible(element) -> str:
    return ''.join(t.text or '' for t in element.iter(tag('t')))


def style_of(p) -> str | None:
    sid = p.find('w:pPr/w:pStyle', NS)
    return sid.get(tag('val')) if sid is not None else None


@dataclass
class Layout:
    """Measured positions: bookmark → (page index, top in PDF points)."""
    positions: dict[str, tuple[int, float]]
    # Baseline of the lowest body text on each page; None for a page without text.
    lowest: list[float | None]
    landscape: list[bool] = field(default_factory=list)

    def page(self, name: str) -> int:
        return self.positions[name][0]

    def top(self, name: str) -> float:
        return self.positions[name][1]

    def free(self, page: int) -> float:
        """Empty height at the end of a portrait page."""
        if not 0 <= page < len(self.lowest) or (self.landscape and self.landscape[page]):
            return 0.0
        low = self.lowest[page]
        return PAGE_TOP - PAGE_BOTTOM if low is None else max(0.0, low - DESCENT - PAGE_BOTTOM)

    def height(self, here: str, after: str | None) -> float:
        """Height from one mark to the next in the text flow, also across a page break."""
        if after not in self.positions:
            return 2 * LINE
        if self.page(here) == self.page(after):
            return self.top(here) - self.top(after)
        lowest = self.lowest[self.page(here)] or PAGE_BOTTOM
        return self.top(here) - lowest + DESCENT + PAGE_TOP - self.top(after)


def blocks(body) -> list:
    return [el for el in body if el.tag in (tag('p'), tag('tbl'))]


def add_marks(root) -> None:
    """Zero-length bookmarks at each body block and table row (draft only)."""
    number = 900000
    def mark(p, name):
        nonlocal number
        number += 1
        index = 1 if p.find('w:pPr', NS) is not None else 0
        p.insert(index, ET.Element(tag('bookmarkStart'), {tag('id'): str(number), tag('name'): name}))
        p.insert(index + 1, ET.Element(tag('bookmarkEnd'), {tag('id'): str(number)}))
    for i, block in enumerate(blocks(root.find('w:body', NS))):
        if block.tag == tag('p'):
            mark(block, f'{MARK}{i}')
            continue
        for r, row in enumerate(block.findall('w:tr', NS)):
            p = row.find('w:tc/w:p', NS)
            if p is not None:
                mark(p, f'{MARK}{i}R{r}')


def style_ids(package: zipfile.ZipFile) -> dict[str, str]:
    root = parse(package.read('word/styles.xml'))
    return {s.find('w:name', NS).get(tag('val')).lower(): s.get(tag('styleId'))
            for s in root.findall('w:style', NS) if s.find('w:name', NS) is not None}


class Document:
    """The body being laid out, with the measurement of its current state."""

    def __init__(self, root, layout: Layout, styles: dict[str, str], handled: dict,
                 move_text: bool = True):
        self.body = root.find('w:body', NS)
        self.move_text = move_text
        self.items = blocks(self.body)
        self.layout = layout
        self.styles = styles
        self.handled = handled

    def name(self, k: int) -> str | None:
        """Bookmark at the top of block k: the paragraph or its first row."""
        if k >= len(self.items):
            return None
        name = f'{MARK}{k}' if self.items[k].tag == tag('p') else f'{MARK}{k}R0'
        return name if name in self.layout.positions else None

    def page(self, k: int) -> int:
        return self.layout.page(self.name(k))

    def top(self, k: int) -> float:
        return self.layout.top(self.name(k))

    def height(self, k: int) -> float:
        return self.layout.height(self.name(k), self.name(k + 1))

    def movable(self, p) -> bool:
        """Body text or a list item that may change places with a figure."""
        text = {self.styles.get(name) for name in BODY_STYLES} | {None}
        return (p.tag == tag('p') and style_of(p) in text and visible(p).strip() != ''
                and p.find('.//w:drawing', NS) is None and p.find('.//w:sectPr', NS) is None
                and p.find(f'.//{{{M}}}oMathPara', NS) is None)

    def units(self, k: int) -> list[tuple[int, int]]:
        """Movable blocks from k on, grouped so that nothing is torn apart:
        a list with the paragraph that introduces it, a colon with what follows."""
        items, units = self.items, []
        def ok(j):
            return j < len(items) and self.movable(items[j]) and self.name(j) is not None
        def is_item(j):
            return items[j].find('w:pPr/w:numPr', NS) is not None
        while ok(k):
            end = k + 1
            while True:
                if ok(end) and is_item(end):
                    while ok(end) and is_item(end):
                        end += 1
                    continue
                if not visible(items[end - 1]).rstrip().endswith(':'):
                    break
                if not ok(end):
                    return units
                end += 1
            units.append((k, end))
            k = end
        return units

    def first_issue(self):
        found = []
        for i, block in enumerate(self.items):
            issue = self.table_issue(i) if block.tag == tag('tbl') else self.figure_issue(i)
            if issue:
                found.append(issue)
        return min(found, key=lambda issue: issue[0]) if found else None

    def caption(self, i: int):
        if i == 0 or self.items[i - 1].tag != tag('p'):
            return None
        caption = self.items[i - 1]
        kinds = {self.styles.get('table caption'), self.styles.get('listing caption')}
        if style_of(caption) in kinds and re.match(r'(?:Продолжение )?(?:Таблиц|Листинг)', visible(caption)):
            return caption
        return None

    def table_issue(self, i: int):
        """(page, fix) for the first row of a captioned table on a new page."""
        table = self.items[i]
        caption = self.caption(i)
        rows = table.findall('w:tr', NS)
        names = [f'{MARK}{i}R{r}' for r, row in enumerate(rows)
                 if row.find('w:trPr/w:tblHeader', NS) is None]
        if caption is None or not names or any(n not in self.layout.positions for n in names):
            return None
        pages = [self.layout.page(n) for n in names]
        if self.name(i - 1) is None:
            return None
        if self.page(i - 1) < pages[0]:
            # The caption and header stayed behind: the table starts the next page.
            if caption.find('w:pPr/w:pageBreakBefore[@w:val="1"]', NS) is not None:
                return None
            return self.page(i - 1), lambda: child(child(caption, 'pPr'), 'pageBreakBefore', val='1')
        cut = next((k for k in range(1, len(pages)) if pages[k] != pages[k - 1]), None)
        if cut is None:
            return None

        def split():
            title = re.sub(r'^Продолжение (Таблицы|Листинга)',
                           lambda m: {'Таблицы': 'Таблица', 'Листинга': 'Листинг'}[m.group(1)],
                           visible(caption))
            parts = split_table(table, [cut], title, style_of(caption))
            index = list(self.body).index(table)
            self.body.remove(table)
            for offset, part in enumerate(parts):
                self.body.insert(index + offset, part)
        return pages[cut] - 1, split

    def figure_issue(self, i: int):
        """(page, fix) when a figure leaves an empty page end behind it."""
        items, styles = self.items, self.styles
        figure = items[i]
        if figure.find('.//w:drawing', NS) is None or i + 1 >= len(items):
            return None
        if style_of(items[i + 1]) != styles.get('image caption'):
            return None
        if self.name(i) is None or self.name(i + 1) is None:
            return None
        page = self.page(i)
        start = i
        while start > 0 and i - start < 4 and self.name(start - 1) and self.page(start - 1) == page:
            start -= 1
        # The figure opens its page, with at most its introduction and headings.
        if start == 0 or self.name(start - 1) is None or self.page(start - 1) != page - 1:
            return None
        first = items[start]
        if (style_of(first) in {styles[name] for name in PAGE_STYLES if name in styles}
                or first.find('w:pPr/w:pageBreakBefore[@w:val="1"]', NS) is not None):
            return None
        gap = self.layout.free(page - 1)
        attempts = self.handled.get(id(figure), 0)
        if gap < GAP or attempts >= 2:
            return None
        before = self.top(start) - self.top(i)
        after = self.height(i + 1)
        sizes = [el for inline in figure.iter(f'{{{WP}}}inline')
                 for el in [inline.find(f'{{{WP}}}extent'), *inline.iter(f'{{{A}}}ext')] if el is not None]
        height = int(sizes[0].get('cy')) / 12700 if sizes else 0.0
        scale = (gap - before - after - 6) / height if height else 0.0

        def shrink():
            self.handled[id(figure)] = attempts + 1
            for size in sizes:
                for axis in ('cx', 'cy'):
                    size.set(axis, str(round(int(size.get(axis)) * scale * 0.98)))

        # Text after the caption fills the page; the figure opens the next one.
        available = gap - before - 6
        moving, room = [], available
        for first_k, end in self.units(i + 2) if self.move_text else []:
            size = sum(self.height(j) for j in range(first_k, end))
            if size <= room:
                moving.extend(items[first_k:end])
                room -= size
                continue
            # Text of four lines or more may break at the page end, if what
            # remains still leaves room for the figure on the next page.
            rest = max(size - room, 2 * LINE)
            if (size >= 4 * LINE and room >= 2 * LINE
                    and rest + height + after <= PAGE_TOP - PAGE_BOTTOM - LINE):
                moving.extend(items[first_k:end])
                room = 0.0
            break
        # A slight reduction keeps the reading order; text moves when it fills
        # the page; a stronger reduction beats a gap; any visible gain is taken.
        fits = scale < 1 and attempts == 0
        if fits and scale >= MIN_SCALE:
            return page - 1, shrink
        if moving and room < GAP:
            return page - 1, self.float_text(i, start, moving)
        if fits and scale >= LOW_SCALE:
            return page - 1, shrink
        if moving and available - room >= 2 * LINE:
            return page - 1, self.float_text(i, start, moving)
        return None

    def float_text(self, i: int, start: int, moving: list):
        figure = self.items[i]

        def apply():
            self.handled[id(figure)] = 2
            intro = self.items[i - 1]
            # The introduction no longer has to share the page with the figure.
            if i > start and self.movable(intro):
                child(child(intro, 'pPr'), 'keepNext', val='0')
            for p in moving:
                self.body.remove(p)
            index = list(self.body).index(figure)
            for offset, p in enumerate(moving):
                self.body.insert(index + offset, p)
        return apply


def update_toc(root, layout: Layout, page_start: int) -> None:
    for p in root.findall('.//w:sdtContent/w:p', NS):
        link = p.find('w:hyperlink', NS)
        cache = p.find('w:fldSimple/w:r/w:t', NS)
        if link is None or cache is None:
            continue
        anchor = link.get(tag('anchor'))
        if anchor not in layout.positions:
            raise PaginationError('Не найдена закладка заголовка в PDF: ' + visible(link))
        cache.text = str(layout.page(anchor) + page_start)


def measure(draft: Path, out: Path, executable: str, profile: Path) -> Layout:
    from pypdf import PdfReader
    out.mkdir()
    try:
        result = subprocess.run([
            executable, '-env:UserInstallation=' + profile.as_uri(),
            '--headless', '--norestore', '--convert-to', EXPORT,
            '--outdir', str(out), str(draft.resolve()),
        ], capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PaginationError(f'Не удалось выполнить пагинацию LibreOffice: {exc}') from exc
    pdf = out / (draft.stem + '.pdf')
    if result.returncode or not pdf.exists():
        raise PaginationError('LibreOffice не создал PDF: ' + result.stderr[-2000:])
    reader = PdfReader(pdf)
    positions = {}
    for key, destination in reader.named_destinations.items():
        top = destination.get('/Top')
        if top is not None:
            positions[key.lstrip('/')] = (reader.get_destination_page_number(destination), float(top))
    if not any(key.startswith(MARK) for key in positions):
        raise PaginationError('LibreOffice не экспортировал закладки в PDF: нужна версия 7.4 или новее.')
    lowest, landscape = [], []
    for page in reader.pages:
        baselines = []
        def visit(text, cm, tm, font, size):
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            # The page number lies inside the bottom margin.
            if text.strip() and y > PAGE_BOTTOM:
                baselines.append(y)
        page.extract_text(visitor_text=visit)
        lowest.append(min(baselines) if baselines else None)
        landscape.append(float(page.mediabox.width) > float(page.mediabox.height))
    return Layout(positions, lowest, landscape)


def paginate(path: Path, *, executable: str | None = None, page_start: int = 1,
             move_text: bool = True, max_passes: int = 40) -> None:
    try:
        import pypdf  # noqa: F401
    except ImportError as exc:
        raise PaginationError('Для --paginate установите md2gost[pagination] (pypdf).') from exc
    executable = executable or shutil.which('soffice')
    if not executable:
        raise PaginationError('Для --paginate нужен LibreOffice: задайте --libreoffice /путь/к/soffice.')
    with zipfile.ZipFile(path) as package:
        original = package.read('word/document.xml')
        styles = style_ids(package)
    root = parse(original)
    handled: dict = {}
    with tempfile.TemporaryDirectory(prefix='md2gost-pagination-') as directory:
        work = Path(directory)
        draft = work / path.name
        draft.write_bytes(path.read_bytes())
        for iteration in range(max_passes):
            marked = deepcopy(root)
            add_marks(marked)
            rewrite_package(draft, {'word/document.xml': serialize(marked, original)})
            layout = measure(draft, work / str(iteration), executable, work / 'profile')
            update_toc(root, layout, page_start)
            issue = Document(root, layout, styles, handled, move_text).first_issue()
            if issue is None:
                rewrite_package(path, {'word/document.xml': serialize(root, original)})
                return
            issue[1]()
    raise PaginationError(f'Вёрстка не стабилизировалась за {max_passes} проходов; проверьте длинные таблицы.')
