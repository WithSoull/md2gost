"""Measured layout: decisions come from bookmark positions, never from text guesses."""
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from md2gost.converter import ConvertOptions, convert
from md2gost.formatting import NS, tag
from md2gost.pagination import (GAP, LINE, MARK, PAGE_BOTTOM, PAGE_TOP, Document, Layout,
                                add_marks, update_toc, visible)

STYLES = {'table caption': 'TableCaption', 'listing caption': 'GOSTListingCaption',
          'image caption': 'ImageCaption', 'normal': 'Normal', 'body text': 'BodyText',
          'first paragraph': 'FirstParagraph', 'compact': 'Compact', 'heading 1': 'Heading1'}
WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'


def para(body, text='', style=None, keep=False):
    p = ET.SubElement(body, tag('p'))
    ppr = ET.SubElement(p, tag('pPr'))
    if style:
        ET.SubElement(ppr, tag('pStyle'), {tag('val'): style})
    if keep:
        ET.SubElement(ppr, tag('keepNext'), {tag('val'): '1'})
    ET.SubElement(ET.SubElement(p, tag('r')), tag('t')).text = text
    return p


def table(body, cells, header=True):
    t = ET.SubElement(body, tag('tbl'))
    for index, text in enumerate(cells):
        row = ET.SubElement(t, tag('tr'))
        if header and index == 0:
            ET.SubElement(ET.SubElement(row, tag('trPr')), tag('tblHeader'))
        para(ET.SubElement(row, tag('tc')), text)
    return t


def figure(body, cy):
    p = para(body, '', 'CaptionedFigure', keep=True)
    inline = ET.SubElement(ET.SubElement(ET.SubElement(p, tag('r')), tag('drawing')), f'{{{WP}}}inline')
    ET.SubElement(inline, f'{{{WP}}}extent', cx='5000000', cy=str(cy))
    ET.SubElement(ET.SubElement(inline, f'{{{A}}}xfrm'), f'{{{A}}}ext', cx='5000000', cy=str(cy))
    return p


def document():
    root = ET.Element(tag('document'))
    return root, ET.SubElement(root, tag('body'))


def flow(*blocks):
    """Positions for (page, top) of each body block; tables give one per row."""
    positions = {}
    for index, place in enumerate(blocks):
        if isinstance(place, list):
            for row, row_place in enumerate(place):
                positions[f'{MARK}{index}R{row}'] = row_place
        else:
            positions[f'{MARK}{index}'] = place
    return positions


def test_table_is_cut_at_the_measured_row_and_continued():
    root, body = document()
    para(body, 'Таблица 1.1 — Данные', 'TableCaption', keep=True)
    t = table(body, ['Шапка', 'Первая', 'Вторая', 'Третья'])
    para(body, 'Текст после таблицы.')
    layout = Layout(flow((0, 300), [(0, 280), (0, 260), (0, 80), (1, 785)], (1, 760)), [80, 700])
    page, fix = Document(root, layout, STYLES, {}).first_issue()
    assert page == 0
    fix()
    tables = body.findall('w:tbl', NS)
    assert [visible(x) for x in tables] == ['ШапкаПерваяВторая', 'ШапкаТретья']
    continuation = [p for p in body.findall('w:p', NS) if visible(p) == 'Продолжение Таблицы 1.1']
    assert continuation[0].find('w:pPr/w:pageBreakBefore', NS).get(tag('val')) == '1'
    # Rules 6.3: the first part has no closing bottom line.
    cells = tables[0].findall('w:tr', NS)[-1].findall('w:tc', NS)
    assert all(c.find('w:tcPr/w:tcBorders/w:bottom', NS).get(tag('val')) == 'nil' for c in cells)
    assert t not in list(body)


def test_listing_continues_under_its_own_word():
    root, body = document()
    para(body, 'Листинг А.1 — Модуль', 'GOSTListingCaption', keep=True)
    table(body, ['a = 1', 'b = 2', 'c = 3'], header=False)
    layout = Layout(flow((0, 200), [(0, 180), (0, 168), (1, 785)]), [168, 785])
    Document(root, layout, STYLES, {}).first_issue()[1]()
    assert 'Продолжение Листинга А.1' in [visible(p) for p in body.findall('w:p', NS)]
    assert [len(t.findall('w:tr', NS)) for t in body.findall('w:tbl', NS)] == [2, 1]


def test_caption_left_alone_takes_the_table_to_the_next_page():
    root, body = document()
    caption = para(body, 'Таблица 1.1 — Данные', 'TableCaption', keep=True)
    table(body, ['Шапка', 'Первая'])
    layout = Layout(flow((0, 70), [(0, 60), (1, 785)]), [60, 785])
    Document(root, layout, STYLES, {}).first_issue()[1]()
    assert caption.find('w:pPr/w:pageBreakBefore', NS).get(tag('val')) == '1'


def gap_document(figure_cy):
    root, body = document()
    para(body, 'Предыдущий текст.')
    intro = para(body, 'Схема показана на Рисунке 1.1.', keep=True)
    fig = figure(body, figure_cy)
    para(body, 'Рисунок 1.1 — Схема', 'ImageCaption')
    after = [para(body, 'Первый абзац после рисунка.'), para(body, 'Второй абзац после рисунка.')]
    para(body, '1.2 Подраздел', 'Heading2')
    return root, body, intro, fig, after


def test_text_fills_the_gap_and_the_figure_opens_the_next_page():
    # 12 empty lines at the end of page 0; the figure is too tall to shrink.
    lowest = PAGE_BOTTOM + 12 * LINE + 3.5
    root, body, intro, fig, after = gap_document(figure_cy=9 * 360000 * 2)
    layout = Layout(flow((0, 500), (1, PAGE_TOP), (1, PAGE_TOP - LINE), (1, 200),
                         (1, 180), (1, 180 - 4 * LINE), (1, 180 - 7 * LINE)), [lowest, 100])
    handled = {}
    page, fix = Document(root, layout, STYLES, handled).first_issue()
    assert page == 0
    fix()
    order = [visible(p) for p in body.findall('w:p', NS)]
    assert order.index('Первый абзац после рисунка.') < order.index('')
    assert order.index('Второй абзац после рисунка.') < order.index('')
    assert intro.find('w:pPr/w:keepNext', NS).get(tag('val')) == '0'
    # The same figure is not reconsidered forever.
    assert handled[id(fig)] == 2


def test_slightly_large_figure_shrinks_instead():
    gap = 15 * LINE
    root, body, intro, fig, after = gap_document(figure_cy=int((gap - LINE) / 0.9 * 12700))
    layout = Layout(flow((0, 500), (1, PAGE_TOP), (1, PAGE_TOP - LINE), (1, 200),
                         (1, 180), (1, 100), (1, 76)), [PAGE_BOTTOM + gap + 3.5, 100])
    Document(root, layout, STYLES, {}).first_issue()[1]()
    extent = fig.find(f'.//{{{WP}}}extent')
    assert int(extent.get('cy')) < int((gap - LINE) / 0.9 * 12700)
    assert extent.attrib == fig.find(f'.//{{{A}}}ext').attrib
    assert [visible(p) for p in body.findall('w:p', NS)][4] == 'Первый абзац после рисунка.'


def test_small_gap_is_not_a_defect():
    root, body, *_ = gap_document(figure_cy=9 * 360000)
    layout = Layout(flow((0, 500), (1, PAGE_TOP), (1, PAGE_TOP - LINE), (1, 200),
                         (1, 180), (1, 100), (1, 76)), [PAGE_BOTTOM + GAP - 10, 100])
    assert Document(root, layout, STYLES, {}).first_issue() is None


def test_list_moves_together_with_its_introduction():
    root, body = document()
    para(body, 'Текст.')
    figure(body, 20 * 360000)
    para(body, 'Рисунок 1.1 — Схема', 'ImageCaption')
    para(body, 'Шаги процесса.')
    for n in range(3):
        item = para(body, f'Шаг {n}.', 'Compact')
        ET.SubElement(ET.SubElement(item.find('w:pPr', NS), tag('numPr')), tag('numId'), {tag('val'): '1'})
    para(body, 'Итог.')
    layout = Layout(flow(*[(0, 700)] + [(1, PAGE_TOP - k * LINE) for k in range(7)]), [100, 100])
    units = Document(root, layout, STYLES, {}).units(3)
    assert units == [(3, 7), (7, 8)]


def test_marks_and_toc_numbers():
    root, body = document()
    sdt = ET.SubElement(ET.SubElement(body, tag('sdt')), tag('sdtContent'))
    entry = ET.SubElement(sdt, tag('p'))
    ET.SubElement(ET.SubElement(ET.SubElement(entry, tag('hyperlink'), {tag('anchor'): 'GOSTHeading1'}),
                                tag('r')), tag('t')).text = 'ВВЕДЕНИЕ'
    cache = ET.SubElement(ET.SubElement(ET.SubElement(entry, tag('fldSimple')), tag('r')), tag('t'))
    cache.text = '—'
    para(body, 'Текст')
    table(body, ['Шапка', 'Строка'])
    marked = ET.fromstring(ET.tostring(root))
    add_marks(marked)
    names = [b.get(tag('name')) for b in marked.iter(tag('bookmarkStart'))]
    assert names == [f'{MARK}0', f'{MARK}1R0', f'{MARK}1R1']
    update_toc(root, Layout({'GOSTHeading1': (3, 700)}, []), 5)
    assert cache.text == '8'


@pytest.mark.skipif(not shutil.which('soffice'), reason='нужен LibreOffice')
def test_paginate_fixture_with_libreoffice(tmp_path):
    pytest.importorskip('pypdf')
    fixture = Path(__file__).parent / 'fixtures' / 'formatting' / 'diploma.md'
    out = tmp_path / 'paginated.docx'
    convert(fixture, out, options=ConvertOptions(title_page=False, paginate=True))
    with zipfile.ZipFile(out) as package:
        root = ET.fromstring(package.read('word/document.xml'))
    texts = [visible(p) for p in root.iter(tag('p'))]
    numbers = [p.find('w:fldSimple/w:r/w:t', NS).text for p in root.findall('.//w:sdtContent/w:p', NS)
               if p.find('w:fldSimple', NS) is not None]
    assert numbers and all(n.isdigit() for n in numbers)
    assert 'Продолжение Таблицы Б.1' in texts
    assert 'Продолжение Листинга А.1' in texts
    assert 'md2gostB' not in ET.tostring(root, encoding='unicode')


def test_keep_order_never_moves_text():
    lowest = PAGE_BOTTOM + 12 * LINE + 3.5
    root, body, intro, fig, after = gap_document(figure_cy=9 * 360000 * 2)
    layout = Layout(flow((0, 500), (1, PAGE_TOP), (1, PAGE_TOP - LINE), (1, 200),
                         (1, 180), (1, 180 - 4 * LINE), (1, 180 - 7 * LINE)), [lowest, 100])
    assert Document(root, layout, STYLES, {}, move_text=False).first_issue() is None
