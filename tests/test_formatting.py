"""Check actual Pandoc output, including numbering and OOXML layout contracts."""
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

import pytest
from click.testing import CliRunner

from md2gost.cli import cli
from md2gost.converter import BUILTIN_TEMPLATE, ConvertOptions, convert
from md2gost.formatting import (CELL_MARGIN_X, CELL_MARGIN_Y, EQUATION_SPACING, NS, tag, parse,
                                serialize, rewrite_package, text_width)

FIXTURE = Path(__file__).parent / 'fixtures' / 'formatting' / 'diploma.md'


def read_part(path, name):
    with zipfile.ZipFile(path) as package:
        return ET.fromstring(package.read(name))


def text(el):
    return ''.join(t.text or '' for t in el.iter(tag('t')))


def tabbed(el):
    """Visible text with tabs, as a reader sees «где» lines."""
    math = '{http://schemas.openxmlformats.org/officeDocument/2006/math}t'
    return ''.join('\t' if x.tag == tag('tab') else x.text or ''
                   for x in el.iter() if x.tag in (tag('t'), tag('tab'), math)
                   and not (x.tag == tag('tab') and x.get(tag('val'))))


@pytest.fixture(scope='module')
def converted(tmp_path_factory):
    output = tmp_path_factory.mktemp('layout') / 'diploma.docx'
    convert(FIXTURE, output, options=ConvertOptions(title_page=False, page_start=5))
    return output


def test_page_geometry_and_continuous_numbering(converted):
    root = read_part(converted, 'word/document.xml')
    sections = root.findall('.//w:sectPr', NS)
    assert [s.find('w:pgSz', NS).get(tag('orient')) for s in sections] == ['portrait', 'landscape', 'portrait']
    assert sections[0].find('w:pgSz', NS).get(tag('w')) == '11906'
    assert sections[0].find('w:pgSz', NS).get(tag('h')) == '16838'
    margins = sections[0].find('w:pgMar', NS)
    assert [margins.get(tag(k)) for k in ['left', 'right', 'top', 'bottom']] == ['1701', '567', '1134', '1134']
    assert sections[0].find('w:pgNumType', NS).get(tag('start')) == '5'
    assert all(s.find('w:pgNumType', NS) is None for s in sections[1:])
    assert not root.findall('.//w:headerReference', NS)


def test_headings_and_no_empty_title_block(converted):
    body = read_part(converted, 'word/document.xml').find('w:body', NS)
    paras = body.findall('w:p', NS)
    assert text(paras[0]) == 'АННОТАЦИЯ'
    assert paras[0].find('w:pPr/w:pageBreakBefore', NS).get(tag('val')) == '0'
    values = {text(p): p.find('w:pPr/w:pStyle', NS).get(tag('val'))
              for p in paras if p.find('w:pPr/w:pStyle', NS) is not None}
    assert values['1 ИССЛЕДОВАТЕЛЬСКИЙ РАЗДЕЛ'] == '1'
    assert values['1.1 Анализ предметной области'] == '21'
    assert values['1.1.1 Дополнительный анализ'] == '30'
    assert values['2 АНАЛИТИЧЕСКИЙ РАЗДЕЛ'] == '1'
    assert values['Приложение А'] == 'GOSTAppendixHeading'
    assert values['Дополнительные материалы'] == 'GOSTAppendixTitle'


def test_caption_numbers_and_forward_references(converted):
    root = read_part(converted, 'word/document.xml')
    values = [text(p) for p in root.findall('.//w:p', NS)]
    for expected in ['Таблица 1.1 – Сравнение решений', 'Таблица 1.2 – Дополнительные показатели',
                     'Таблица 2.1 – Характеристики метода', 'Таблица А.1 – Данные приложения',
                     'Таблица Б.1 – Длинная таблица', 'Рисунок 1.1 – Порядок обработки',
                     'Рисунок 2.1 – Схема обработки', 'Рисунок А.1 – Схема приложения']:
        assert expected in values
    # References render as a bare number; the noun comes from the author.
    assert any('будущий Рисунок 2.1.' in value for value in values)
    assert any('приведено в Таблице 1.1.' in value for value in values)
    assert not any('рис.' in value or 'табл.' in value for value in values)
    assert '@fig:' not in text(root) and '@tbl:' not in text(root) and '@eq:' not in text(root)


def test_equation_numbers_are_outside_math(converted):
    root = read_part(converted, 'word/document.xml')
    numbered = [p for p in root.findall('.//w:p', NS) if text(p) in ['(2.1)']]
    assert len(numbered) == 1
    for p in numbered:
        assert p.find('m:oMath', NS) is not None
        assert p.find('m:oMathPara', NS) is None
        assert len(p.findall('w:r/w:tab', NS)) == 2
        assert [tab.get(tag('pos')) for tab in p.findall('w:pPr/w:tabs/w:tab', NS)] == ['4819', '9638']
        assert '#' not in ''.join(p.itertext())


def test_body_headings_captions_and_code_styles(converted):
    root = read_part(converted, 'word/styles.xml')
    by_name = {s.find('w:name', NS).get(tag('val')).lower(): s for s in root.findall('w:style', NS)}
    for name in ['normal', 'body text', 'first paragraph', 'compact']:
        s = by_name[name]
        assert s.find('w:rPr/w:sz', NS).get(tag('val')) == '28'
        assert s.find('w:rPr/w:rFonts', NS).get(tag('ascii')) == 'Times New Roman'
        assert s.find('w:pPr/w:spacing', NS).get(tag('line')) == '360'
        assert s.find('w:pPr/w:ind', NS).get(tag('firstLine')) == '709'
    for level, size in [(1, '36'), (2, '32'), (3, '28')]:
        assert by_name[f'heading {level}'].find('w:rPr/w:sz', NS).get(tag('val')) == size
    assert by_name['table caption'].find('w:pPr/w:jc', NS).get(tag('val')) == 'both'
    assert by_name['table caption'].find('w:rPr/w:i', NS).get(tag('val')) == '1'
    assert by_name['table caption'].find('w:pPr/w:spacing', NS).get(tag('after')) == '0'
    assert by_name['image caption'].find('w:rPr/w:b', NS).get(tag('val')) == '1'
    assert by_name['source code'].find('w:rPr/w:rFonts', NS).get(tag('ascii')) == 'Courier New'
    assert by_name['source code'].find('w:rPr/w:sz', NS).get(tag('val')) == '20'
    # Pandoc's character style otherwise overrides the paragraph's code font.
    assert by_name['verbatim char'].find('w:rPr/w:rFonts', NS).get(tag('ascii')) == 'Courier New'
    assert by_name['verbatim char'].find('w:rPr/w:sz', NS).get(tag('val')) == '20'


def test_toc_after_annotation_and_includes_structural_parts(converted):
    body = read_part(converted, 'word/document.xml').find('w:body', NS)
    toc = body.find('w:sdt', NS)
    assert text(list(body)[0]) != 'СОДЕРЖАНИЕ'
    contents = text(toc)
    assert 'ВВЕДЕНИЕ' in contents and 'ЗАКЛЮЧЕНИЕ' in contents
    assert '1.1.1 Дополнительный анализ' in contents
    assert 'АННОТАЦИЯ' not in contents
    assert toc.findall('.//w:fldSimple', NS)
    field_kinds = [f.get(tag('fldCharType')) for f in toc.findall('.//w:fldChar', NS)]
    assert field_kinds == ['begin', 'separate', 'end']


def test_listing_is_a_frame_with_one_row_per_line(converted):
    """Rules 8.4–8.5: a framed listing; rows let pagination cut it at a page end."""
    root = read_part(converted, 'word/document.xml')
    listing_tables = [t for t in root.findall('.//w:tbl', NS)
                      if any(f.get(tag('ascii')) == 'Courier New' for f in t.findall('.//w:rFonts', NS))]
    assert len(listing_tables) == 1
    rows = listing_tables[0].findall('w:tr', NS)
    assert len(rows) == 90
    assert all(r.find('w:trPr/w:cantSplit', NS) is not None for r in rows)
    borders = listing_tables[0].find('w:tblPr/w:tblBorders', NS)
    assert borders.find('w:insideH', NS).get(tag('val')) == 'nil'
    assert borders.find('w:top', NS).get(tag('val')) == 'single'
    values = [text(p) for p in root.findall('.//w:p', NS)]
    assert 'Листинг А.1 — Проверочный модуль' in values
    assert not any(v.startswith(('Продолжение листинга', 'Окончание')) for v in values)
    assert len(root.findall('.//w:tblHeader', NS)) == 6
    styles = read_part(converted, 'word/styles.xml')
    caption = styles.find("w:style[@w:styleId='GOSTListingCaption']", NS)
    # Like table captions, by agreement: right after the text, no forced page.
    assert caption.find('w:pPr/w:pageBreakBefore', NS).get(tag('val')) == '0'
    assert caption.find('w:pPr/w:keepNext', NS).get(tag('val')) == '1'


def test_listing_line_numbers_step_ten(tmp_path):
    """Rules 8.3: referenced lines are numbered 10, 20, …"""
    output = build(tmp_path, '## Раздел\n\n```{.numberLines}\nЛистинг 1.1 - Пример\na = 1\nb = 2\n```\n')
    values = [text(p) for p in read_part(output, 'word/document.xml').findall('.//w:p', NS)]
    assert 'Листинг 1.1 — Пример' in values
    assert ['10  a = 1', '20  b = 2'] == [v for v in values if v[:2] in ('10', '20')]


def test_table_header_centered_and_other_cells_left_aligned(converted):
    root = read_part(converted, 'word/document.xml')
    tables = [t for t in root.findall('.//w:tbl', NS)
              if t.find('w:tr/w:trPr/w:tblHeader', NS) is not None]
    assert len(tables) == 6
    for table in tables:
        for index, row in enumerate(table.findall('w:tr', NS)):
            for col, cell in enumerate(row.findall('w:tc', NS)):
                for p in cell.findall('.//w:p', NS):
                    assert p.find('w:pPr/w:jc', NS).get(tag('val')) == ('center' if index == 0 else 'left' if col == 0 else 'both')


def test_table_alignment_overrides_markdown_columns(tmp_path):
    source = tmp_path / 'alignment.md'
    source.write_text('## Раздел\n\n| Слева | Справа | По центру |\n'
                      '|:---|---:|:---:|\n| Один | Два | Три |\n', encoding='utf-8')
    output = tmp_path / 'alignment.docx'
    convert(source, output, options=ConvertOptions(toc=False, title_page=False))
    rows = read_part(output, 'word/document.xml').findall('.//w:tbl/w:tr', NS)
    for row, expected in zip(rows, [['center'] * 3, ['left', 'both', 'both']], strict=True):
        assert [p.find('w:pPr/w:jc', NS).get(tag('val'))
                for p in row.findall('.//w:p', NS)] == expected


def test_custom_reference_layout_is_preserved(tmp_path):
    custom = tmp_path / 'reference.docx'
    custom.write_bytes((Path(__file__).parent / 'fixtures' / 'minimal_template.docx').read_bytes())
    with zipfile.ZipFile(custom) as package:
        original_xml = package.read('word/document.xml')
    reference = parse(original_xml)
    section = reference.find('.//w:sectPr', NS)
    if section is None:
        section = ET.SubElement(reference.find('w:body', NS), tag('sectPr'))
    ET.SubElement(section, tag('pgSz'), {tag('w'): '12240', tag('h'): '15840'})
    rewrite_package(custom, {'word/document.xml': serialize(reference, original_xml)})
    out = tmp_path / 'custom.docx'
    convert(Path(__file__).parent / 'fixtures' / 'valid.md', out, template=custom)
    original = read_part(custom, 'word/document.xml').find('.//w:sectPr/w:pgSz', NS)
    actual = read_part(out, 'word/document.xml').find('.//w:sectPr/w:pgSz', NS)
    assert original.attrib == actual.attrib
    assert read_part(out, 'word/styles.xml').find("w:style[@w:styleId='GOSTStructuralHeading']", NS) is None


def test_cli_page_start_and_negative_value(tmp_path):
    runner = CliRunner()
    out = tmp_path / 'cli.docx'
    result = runner.invoke(cli, ['convert', str(FIXTURE), '--no-title-page', '--no-toc',
                                 '--page-start', '7', '-o', str(out)])
    assert result.exit_code == 0, result.output
    first = read_part(out, 'word/document.xml').find('.//w:sectPr/w:pgNumType', NS)
    assert first.get(tag('start')) == '7'
    result = runner.invoke(cli, ['convert', str(FIXTURE), '--page-start', '0'])
    assert result.exit_code != 0


def test_appendix_subsections_and_grouped_refs(tmp_path):
    """Rules 10.4: appendix sections «Приложение А.1»; deeper items «А.1.1»."""
    source = tmp_path / 'appendix.md'
    source.write_text('## Раздел\n\nСм. Приложение А и Приложение Б.\n\n# Приложения\n\n'
                      '# Приложение А. Исходные данные\n\n## Подраздел\n\n'
                      '### Пункт\n\n: Данные {#tbl:a}\n\n| X |\n|---|\n| 1 |\n\n'
                      '$$ a=b $$ {#eq:a}\n\nСм. [@tbl:a; @eq:a].\n\n'
                      '# Приложение Б — Расчёты\n\n## Подраздел\n', encoding='utf-8')
    out = tmp_path / 'appendix.docx'
    convert(source, out, options=ConvertOptions(toc=False, title_page=False))
    paras = read_part(out, 'word/document.xml').findall('.//w:body/w:p', NS)
    styled = [(text(p), p.find('w:pPr/w:pStyle', NS).get(tag('val')) if p.find('w:pPr/w:pStyle', NS) is not None else '')
              for p in paras]
    values = [value for value, _ in styled]
    # Rules 10.3: the first sheet of «Приложения» lists the appendices.
    start = values.index('ПРИЛОЖЕНИЯ')
    assert values[start + 1:start + 3] == ['Приложение А – Исходные данные', 'Приложение Б – Расчёты']
    assert ('Приложение А', 'GOSTAppendixHeading') in styled
    assert ('Исходные данные', 'GOSTAppendixTitle') in styled
    assert ('Приложение А.1', 'GOSTAppendixSection') in styled
    assert ('Приложение Б.1', 'GOSTAppendixSection') in styled
    assert 'А.1.1 Пункт' in values
    assert 'См. А.1; (А.1).' in values


def test_template_itself_matches_sample():
    root = read_part(BUILTIN_TEMPLATE, 'word/document.xml')
    margin = root.find('.//w:sectPr/w:pgMar', NS)
    assert margin.get(tag('left')) == '1701'
    assert margin.get(tag('right')) == '567'


def test_spacing_after_tables_and_before_heading(tmp_path):
    source = tmp_path / 'spacing.md'
    table = '| X |\n|---|\n| 1 |\n\n'
    source.write_text('## Раздел\n\n' + table + 'Текст после таблицы.\n\n' +
                      table + '### Подраздел\n\n' + table +
                      '\\newpage\n\n' + table, encoding='utf-8')
    output = tmp_path / 'spacing.docx'
    convert(source, output, options=ConvertOptions(toc=False, title_page=False))
    body = read_part(output, 'word/document.xml').find('w:body', NS)
    after_text = next(p for p in body.findall('w:p', NS) if text(p) == 'Текст после таблицы.')
    assert after_text.find('w:pPr/w:spacing', NS).get(tag('before')) == '120'
    heading = next(p for p in body.findall('w:p', NS) if text(p) == '1.1 Подраздел')
    assert heading.find('w:pPr/w:spacing', NS).get(tag('before')) == '480'
    last_table_index = max(i for i, el in enumerate(body) if el.tag == tag('tbl'))
    spacer = body[last_table_index + 1]
    assert spacer.tag == tag('p') and text(spacer) == ''
    assert spacer.find('w:pPr/w:spacing', NS).get(tag('line')) == '120'
    assert spacer.find('w:pPr/w:spacing', NS).get(tag('lineRule')) == 'exact'


def test_adjacent_table_spacing():
    from md2gost.formatting import configure_styles, format_document
    with zipfile.ZipFile(BUILTIN_TEMPLATE) as package:
        styles = configure_styles(parse(package.read('word/styles.xml')))
    root = ET.Element(tag('document'))
    body = ET.SubElement(root, tag('body'))
    ET.SubElement(body, tag('tbl'))
    ET.SubElement(body, tag('tbl'))
    ET.SubElement(body, tag('sectPr'))
    format_document(root, styles, 1)
    assert [el.tag for el in body] == [tag('tbl'), tag('p'), tag('tbl'), tag('p'), tag('sectPr')]
    for p in body.findall('w:p', NS):
        spacing = p.find('w:pPr/w:spacing', NS)
        assert spacing.get(tag('line')) == '120'
        assert spacing.get(tag('before')) == spacing.get(tag('after')) == '0'


def build(tmp_path, markdown, name='sample'):
    source = tmp_path / f'{name}.md'
    source.write_text(markdown, encoding='utf-8')
    output = tmp_path / f'{name}.docx'
    convert(source, output, options=ConvertOptions(toc=False, title_page=False))
    return output


def grid(table):
    return [int(c.get(tag('w'))) for c in table.findall('w:tblGrid/w:gridCol', NS)]


def test_columns_fit_content(tmp_path):
    """B1: equal Markdown columns are resized by content to the text width."""
    long = 'Прогнозируемое число клиентских чтений объекта за горизонт прогноза ' * 2
    output = build(tmp_path, '## Раздел\n\n| Обозначение | Смысл |\n|---|---|\n'
                   f'| $\\hat N_i$ | {long}|\n| $c_{{\\mathrm{{HOT}}}}$ | Постоянная часть |\n')
    table = read_part(output, 'word/document.xml').find('.//w:tbl', NS)
    widths = grid(table)
    assert sum(widths) == 9638
    assert widths[0] * 3 < widths[1]
    # The header word must not break in the middle.
    assert widths[0] >= text_width('Обозначение', bold=True) + 2 * CELL_MARGIN_X
    for row in table.findall('w:tr', NS):
        cells = [c.find('w:tcPr/w:tcW', NS) for c in row.findall('w:tc', NS)]
        assert [int(c.get(tag('w'))) for c in cells] == widths
        assert {c.get(tag('type')) for c in cells} == {'dxa'}
    tpr = table.find('w:tblPr', NS)
    assert tpr.find('w:tblLayout', NS).get(tag('type')) == 'autofit'
    assert tpr.find('w:tblW', NS).get(tag('w')) == '9638'
    assert tpr.find('w:tblW', NS).get(tag('type')) == 'dxa'


def test_column_width_counts_formula_text(tmp_path):
    """B1: visible formula symbols (m:t) widen their column."""
    formula = ' + '.join(f'x_{{{i}}}' for i in range(1, 15))
    output = build(tmp_path, f'## Раздел\n\n| A | Описание |\n|---|---|\n| ${formula}$ | Сумма |\n')
    widths = grid(read_part(output, 'word/document.xml').find('.//w:tbl', NS))
    assert widths[0] > widths[1]


def test_author_column_widths_are_kept(tmp_path):
    """B1: unequal widths from the Markdown separator line stay as written."""
    long = 'длинный текст ячейки, который не помещается в строку исходника ' * 2
    output = build(tmp_path, f'## Раздел\n\n| A | B |\n|---|------|\n| 1 | {long}|\n')
    table = read_part(output, 'word/document.xml').find('.//w:tbl', NS)
    widths = grid(table)
    assert widths[1] == 2 * widths[0]
    assert table.find('w:tblPr/w:tblLayout', NS).get(tag('type')) == 'fixed'


def test_fixture_table_widths_follow_section(converted):
    """6.4: tables fit their content within the section's text width; listings are untouched."""
    root = read_part(converted, 'word/document.xml')
    tables = [t for t in root.findall('.//w:tbl', NS)
              if t.find('w:tr/w:trPr/w:tblHeader', NS) is not None]
    sums = [sum(grid(t)) for t in tables]
    assert len(sums) == 6
    assert all(s <= 9638 for s in sums[:5]) and sums[5] <= 14570
    for table, total in zip(tables, sums):
        assert int(table.find('w:tblPr/w:tblW', NS).get(tag('w'))) == total
        assert table.find('w:tblPr/w:jc', NS).get(tag('val')) == 'center'
    notation = next(t for t in tables if text(t).startswith('Обозначение'))
    assert sum(grid(notation)) == 9638
    assert grid(notation)[0] * 2 < grid(notation)[1]
    listings = [t for t in root.findall('.//w:tbl', NS) if t not in tables]
    assert all(t.find('w:tblPr/w:tblLayout', NS).get(tag('type')) == 'fixed' for t in listings)


def test_short_table_is_not_stretched(tmp_path):
    """6.4: «Автоподбор по содержимому» leaves a short table narrower than the text."""
    output = build(tmp_path, '## Раздел\n\n| Код | Значение |\n|---|---|\n| A | 1 |\n')
    table = read_part(output, 'word/document.xml').find('.//w:tbl', NS)
    assert sum(grid(table)) < 9638 / 2
    assert grid(table)[0] >= text_width('Код', bold=True) + 2 * CELL_MARGIN_X


def test_table_cell_margins(converted):
    """B2: a small gap above and below cell text; listings keep their own margins."""
    root = read_part(converted, 'word/document.xml')
    for table in root.findall('.//w:tbl', NS):
        margins = table.find('w:tblPr/w:tblCellMar', NS)
        values = {edge: int(margins.find(f'w:{edge}', NS).get(tag('w')))
                  for edge in ['top', 'left', 'bottom', 'right']}
        if table.find('w:tr/w:trPr/w:tblHeader', NS) is not None:
            assert values == {'top': CELL_MARGIN_Y, 'bottom': CELL_MARGIN_Y,
                              'left': CELL_MARGIN_X, 'right': CELL_MARGIN_X}
            assert CELL_MARGIN_Y == 57 and CELL_MARGIN_X == 108
        else:
            assert values == {'top': 0, 'bottom': 0, 'left': 80, 'right': 80}


def test_free_line_around_equations(converted):
    """B3: one body line (spacing, not empty paragraphs) above and below a formula."""
    # 14 pt × 1.15 × 1.5: one empty body line in Word and LibreOffice.
    assert EQUATION_SPACING == 483
    body = read_part(converted, 'word/document.xml').find('w:body', NS)
    blocks = [el for el in body if el.tag in (tag('p'), tag('tbl'))]
    numbered = [p for p in blocks if text(p) in ['(2.1)']]
    assert len(numbered) == 1
    for p in numbered:
        spacing = p.find('w:pPr/w:spacing', NS)
        assert spacing.get(tag('before')) == spacing.get(tag('after')) == str(EQUATION_SPACING)
        index = blocks.index(p)
        assert ''.join(blocks[index - 1].itertext()).strip()
        assert ''.join(blocks[index + 1].itertext()).strip()


def test_where_lines_after_equation(tmp_path):
    """B4: «где» after a labelled formula splits into Where paragraphs without indent."""
    output = build(tmp_path, '## Раздел\n\n$$\nx = y\n$$ {#eq:a}\n\n'
                   'где $x$ — первое;\n$y$ — второе.\n\n'
                   'где это обычный абзац.\n\n'
                   '$$\nz = 1\n$$ {#eq:b}\n\nЗдесь $z$ — не расшифровка.\n\n'
                   '$$\nw = 2\n$$\n\nгде $w$ — формула без номера.\n')
    paras = read_part(output, 'word/document.xml').findall('.//w:body/w:p', NS)
    def style(p):
        sid = p.find('w:pPr/w:pStyle', NS)
        return sid.get(tag('val')) if sid is not None else ''
    where = [tabbed(p) for p in paras if style(p) == 'Where']
    # Rules 5.8: «где» without indent, every symbol at the same tab stop.
    assert where == ['где\tx — первое;', '\ty — второе.', 'где\tw — формула без номера.']
    others = [tabbed(p) for p in paras if style(p) != 'Where']
    assert 'где это обычный абзац.' in others
    styles = read_part(output, 'word/styles.xml')
    s = styles.find("w:style[@w:styleId='Where']", NS)
    assert s.find('w:pPr/w:ind', NS).get(tag('firstLine')) == '0'
    assert s.find('w:pPr/w:tabs/w:tab', NS).get(tag('pos')) == '709'
    assert s.find('w:pPr/w:jc', NS).get(tag('val')) == 'both'
    spacing = s.find('w:pPr/w:spacing', NS)
    assert (spacing.get(tag('before')), spacing.get(tag('after')), spacing.get(tag('line'))) == ('0', '0', '360')


def test_fixture_where_paragraph(converted):
    """B4: explanations after (2.1) and (А.1) become Where lines."""
    body = read_part(converted, 'word/document.xml').find('w:body', NS)
    where = [p for p in body.findall('w:p', NS)
             if p.find("w:pPr/w:pStyle[@w:val='Where']", NS) is not None]
    assert [tabbed(p) for p in where] == [
        'где\ta — число успешных операций;', '\tb — общее число операций.',
        'где\tc — итоговое значение.']
    # The formula is kept on the page of its explanation.
    formula = body[list(body).index(where[0]) - 1]
    assert formula.find('w:pPr/w:keepNext', NS).get(tag('val')) == '1'


def test_references_render_number_only(tmp_path):
    """B5: @fig/@tbl give only the number, @eq stays in parentheses."""
    output = build(tmp_path, '## Раздел\n\nНа Рисунке @fig:a показано, в Таблице @tbl:b приведено, '
                   'по формуле @eq:c считается.\n\n![Схема](x.png){#fig:a}\n\n'
                   ': Данные {#tbl:b}\n\n| X |\n|---|\n| 1 |\n\n$$ a = b $$ {#eq:c}\n')
    actual = text(read_part(output, 'word/document.xml'))
    assert 'На Рисунке 1.1 показано, в Таблице 1.1 приведено, по формуле (1.1) считается.' in actual
    assert 'рис.' not in actual and 'табл.' not in actual


def test_explicit_table_continuations(tmp_path):
    output = build(tmp_path, '## Раздел\n\n: Проверка {#tbl:test break-after="2,3"}\n\n'
                   '| Имя | Значение |\n|---|---|\n| A | 1 |\n| B | 2 |\n| C | 3 |\n| D | 4 |\n')
    body = read_part(output, 'word/document.xml').find('w:body', NS)
    tables = body.findall('w:tbl', NS)
    assert [len(t.findall('w:tr', NS)) for t in tables] == [3, 2, 2]
    assert [text(t) for t in tables] == ['ИмяЗначениеA1B2', 'ИмяЗначениеC3', 'ИмяЗначениеD4']
    continuations = [p for p in body.findall('w:p', NS) if text(p) == 'Продолжение Таблицы 1.1']
    assert len(continuations) == 2
    assert all(p.find('w:pPr/w:pageBreakBefore', NS).get(tag('val')) == '1' for p in continuations)
    for table in tables[:-1]:
        cells = table.findall('w:tr', NS)[-1].findall('w:tc', NS)
        assert all(c.find('w:tcPr/w:tcBorders/w:bottom', NS).get(tag('val')) == 'nil' for c in cells)
    assert 'GOSTTableBreaks' not in ET.tostring(body, encoding='unicode')


def test_only_referenced_formulas_numbered(tmp_path):
    output = build(tmp_path, '## Раздел\n\n$$ a=b $$ {#eq:unused}\n\n'
                   '$$ c=d $$ {#eq:used}\n\nПо формуле @eq:used.\n\n$$ e=f $$\n')
    root = read_part(output, 'word/document.xml')
    assert '(1.1)' in text(root) and '(1.2)' not in text(root)
    assert 'eq:unused' not in text(root)
    formulas = [p for p in root.findall('.//w:body/w:p', NS) if p.find('.//m:oMath', NS) is not None]
    assert len(formulas) == 3
    for p in formulas:
        spacing = p.find('w:pPr/w:spacing', NS)
        assert spacing.get(tag('before')) == spacing.get(tag('after')) == str(EQUATION_SPACING)


def test_rules_toc_lists_and_hyphenation(converted):
    styles = read_part(converted, 'word/styles.xml')
    by_name = {s.find('w:name', NS).get(tag('val')).lower(): s for s in styles.findall('w:style', NS)}
    for level in range(1, 4):
        s = by_name[f'toc {level}']
        assert s.find('w:rPr/w:sz', NS).get(tag('val')) == '28'
        assert s.find('w:pPr/w:spacing', NS).get(tag('line')) == '360'
        assert s.find('w:pPr/w:ind', NS).get(tag('firstLine')) == '0'
    for name in ['normal', 'heading 2', 'heading 3']:
        assert by_name[name].find('w:pPr/w:widowControl', NS).get(tag('val')) == '1'
    settings = read_part(converted, 'word/settings.xml')
    assert settings.find('w:autoHyphenation', NS).get(tag('val')) == 'false'
    numbering = read_part(converted, 'word/numbering.xml')
    for level in numbering.findall('.//w:lvl', NS):
        depth = int(level.get(tag('ilvl')))
        ind = level.find('w:pPr/w:ind', NS)
        assert int(ind.get(tag('left'))) == 1276 + depth * 567
        assert ind.get(tag('hanging')) == '567'
    title = by_name['appendix title']
    assert title.find('w:rPr/w:b', NS).get(tag('val')) == '0'
    assert title.find('w:pPr/w:spacing', NS).get(tag('after')) == '0'


def test_images_fit_page_without_distortion():
    from md2gost.formatting import fit_figures
    wp = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
    a = 'http://schemas.openxmlformats.org/drawingml/2006/main'
    root = ET.Element(tag('document'))
    body = ET.SubElement(root, tag('body'))
    p = ET.SubElement(body, tag('p'))
    inline = ET.SubElement(ET.SubElement(ET.SubElement(p, tag('r')), tag('drawing')), '{'+wp+'}inline')
    extent = ET.SubElement(inline, '{'+wp+'}extent', cx='4000000', cy='10000000')
    shape = ET.SubElement(ET.SubElement(inline, '{'+a+'}xfrm'), '{'+a+'}ext', cx='4000000', cy='10000000')
    ET.SubElement(body, tag('sectPr'))
    fit_figures(root)
    assert int(extent.get('cy')) == 19 * 360000
    assert int(extent.get('cx')) / int(extent.get('cy')) == .4
    assert shape.attrib == extent.attrib


def test_hyperlinks_are_black(converted):
    styles = read_part(converted, 'word/styles.xml')
    link = next(s for s in styles.findall('w:style', NS)
                if s.find('w:name', NS).get(tag('val')).lower() == 'hyperlink')
    color = link.find('w:rPr/w:color', NS)
    assert color.attrib == {tag('val'): '000000'}
    assert link.find('w:rPr/w:u', NS).get(tag('val')) == 'none'


def test_properties_follow_schema_order(converted):
    """Word drops properties out of schema sequence; LibreOffice hides the problem."""
    from md2gost.formatting import SCHEMA_ORDER, W, _SAME_RANK
    with zipfile.ZipFile(converted) as package:
        parts = [n for n in package.namelist() if n.startswith('word/') and n.endswith('.xml')]
        for name in parts:
            for el in ET.fromstring(package.read(name)).iter():
                local = el.tag.rpartition('}')[2]
                order = SCHEMA_ORDER.get(local)
                if order is None or not el.tag.startswith(f'{{{W}}}'):
                    continue
                ranks = [order.index(_SAME_RANK.get(c.tag.rpartition('}')[2], c.tag.rpartition('}')[2]))
                         for c in el if c.tag.startswith(f'{{{W}}}')
                         and _SAME_RANK.get(c.tag.rpartition('}')[2], c.tag.rpartition('}')[2]) in order]
                assert ranks == sorted(ranks), (name, local, [c.tag for c in el])


def test_first_level_headings_are_all_caps(converted):
    """Table 2.1: «Видоизменение: все прописные» for chapters and structural parts."""
    styles = read_part(converted, 'word/styles.xml')
    by_name = {s.find('w:name', NS).get(tag('val')).lower(): s for s in styles.findall('w:style', NS)}
    for name in ['heading 1', 'structural heading', 'toc heading']:
        assert by_name[name].find('w:rPr/w:caps', NS).get(tag('val')) == '1'
    for name in ['heading 2', 'appendix heading', 'appendix title']:
        assert by_name[name].find('w:rPr/w:caps', NS) is None


def test_quotes_follow_the_language(tmp_path):
    """Rules 1.10: «…» in Russian, “…” in English."""
    output = build(tmp_path, '## Раздел\n\nСтандарт "Правила \'внутри\' текста" и "plain English".\n')
    assert 'Стандарт «Правила „внутри“ текста» и “plain English”.' in \
        [text(p) for p in read_part(output, 'word/document.xml').findall('.//w:p', NS)]


def test_bibliography_rubrics(tmp_path):
    """Table 9.1: rubrics inside the list of sources are unnumbered and outside the TOC."""
    output = build(tmp_path, '## Раздел\n\nТекст.\n\n# Список использованных источников\n\n'
                   '## Нормативные документы\n\n1. Закон.\n\n## Книги\n\n2. Книга.\n\n## Следующий\n')
    paras = read_part(output, 'word/document.xml').findall('.//w:body/w:p', NS)
    styled = {text(p): p.find('w:pPr/w:pStyle', NS).get(tag('val')) for p in paras
              if p.find('w:pPr/w:pStyle', NS) is not None}
    assert styled['Нормативные документы'] == 'GOSTBibliographyHeading'
    assert styled['Книги'] == 'GOSTBibliographyHeading'
    style = read_part(output, 'word/styles.xml').find("w:style[@w:styleId='GOSTBibliographyHeading']", NS)
    assert style.find('w:rPr/w:b', NS).get(tag('val')) == '0'
    assert style.find('w:rPr/w:caps', NS).get(tag('val')) == '1'
    assert style.find('w:pPr/w:ind', NS).get(tag('left')) == '709'
    assert style.find('w:pPr/w:jc', NS).get(tag('val')) == 'center'
