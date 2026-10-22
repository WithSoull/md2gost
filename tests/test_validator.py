from pathlib import Path

import pytest

from md2gost.validator import ValidationError, validate

FIXTURES = Path(__file__).parent / "fixtures"


def test_valid_file_no_warnings():
    warnings = validate(FIXTURES / "valid.md")
    assert warnings == []


def test_missing_yaml_header():
    warnings = validate(FIXTURES / "invalid.md")
    messages = [w.message for w in warnings]
    assert any("YAML-шапка" in m for m in messages)


def test_missing_yaml_fields(tmp_path):
    md = tmp_path / "test.md"
    md.write_text("---\ntitle: Только заголовок\n---\n\n# Текст\n", encoding="utf-8")
    warnings = validate(md)
    messages = [w.message for w in warnings]
    assert any("author" in m for m in messages)
    assert any("date" in m for m in messages)


def test_missing_image(tmp_path):
    md = tmp_path / "test.md"
    md.write_text(
        "---\ntitle: T\nauthor: A\ndate: 2026-01-01\n---\n\n![рис](missing.png)\n",
        encoding="utf-8",
    )
    warnings = validate(md)
    messages = [w.message for w in warnings]
    assert any("missing.png" in m for m in messages)


def test_image_exists_no_warning(tmp_path):
    img = tmp_path / "real.png"
    img.write_bytes(b"")
    md = tmp_path / "test.md"
    md.write_text(
        "---\ntitle: T\nauthor: A\ndate: 2026-01-01\n---\n\n![рис](real.png)\n",
        encoding="utf-8",
    )
    warnings = validate(md)
    assert not any("real.png" in w.message for w in warnings)


def test_heading_skip():
    warnings = validate(FIXTURES / "invalid.md")
    messages = [w.message for w in warnings]
    assert any("Пропущен уровень" in m for m in messages)


def test_crossref_undefined(tmp_path):
    md = tmp_path / "test.md"
    md.write_text(
        "---\ntitle: T\nauthor: A\ndate: 2026-01-01\n---\n\nСм. @fig:scheme\n",
        encoding="utf-8",
    )
    warnings = validate(md)
    messages = [w.message for w in warnings]
    assert any("@fig:scheme" in m for m in messages)


def test_crossref_defined_no_warning(tmp_path):
    md = tmp_path / "test.md"
    md.write_text(
        "---\ntitle: T\nauthor: A\ndate: 2026-01-01\n---\n\n![рис](r.png){#fig:scheme}\n\nСм. Рисунок @fig:scheme\n",
        encoding="utf-8",
    )
    warnings = validate(md)
    assert not any("@fig:scheme" in w.message for w in warnings)


def test_invalid_encoding(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_bytes(b"\xff\xfe bad encoding")
    with pytest.raises(ValidationError):
        validate(bad)


def test_crossref_attributes_and_complete_identifiers(tmp_path):
    md = tmp_path / 'refs.md'
    md.write_text('![рис](r.png){#fig:scheme-first width=80%}\n\n'
                  'См. Рисунок @fig:scheme-first. И Рисунок @fig:scheme-other.\n', encoding='utf-8')
    messages = [w.message for w in validate(md)]
    assert not any('@fig:scheme-first' in message for message in messages)
    assert any('@fig:scheme-other' in message for message in messages)


def test_reference_without_noun_warns(tmp_path):
    md = tmp_path / 'nouns.md'
    md.write_text('![рис](r.png){#fig:a}\n\n: Данные {#tbl:b}\n\n| X |\n|---|\n| 1 |\n\n'
                  '$$ x $$ {#eq:c}\n\n'
                  'Схема на @fig:a, данные в @tbl:b, расчёт по @eq:c.\n'
                  'Схема на Рисунке @fig:a, данные в Таблице\n@tbl:b.\n'
                  'Рисунки [@fig:a; @fig:a] и Таблицы @tbl:b и @tbl:b.\n'
                  'Рисунок @fig:a и @tbl:b.\n', encoding='utf-8')
    warnings = [w for w in validate(md) if 'нет слова' in w.message]
    assert [(w.line, w.message.split()[1]) for w in warnings] == [
        (11, '@fig:a'), (11, '@tbl:b'), (15, '@tbl:b')]


def test_reference_word_warning_does_not_fail_build(tmp_path):
    from click.testing import CliRunner
    from md2gost.cli import cli
    md = tmp_path / 'bare.md'
    md.write_text('---\ntitle: T\nauthor: A\ndate: 2026-01-01\nlang: ru\n---\n\n## Раздел\n\n'
                  'Данные в @tbl:b.\n\n: Данные {#tbl:b}\n\n| X |\n|---|\n| 1 |\n', encoding='utf-8')
    result = CliRunner().invoke(cli, ['convert', str(md), '--no-toc', '-o', str(tmp_path / 'bare.docx')])
    assert result.exit_code == 0, result.output
    assert 'нет слова «Таблица»' in result.output
    assert (tmp_path / 'bare.docx').exists()


def test_reference_word_is_searched_in_the_same_paragraph(tmp_path):
    md = tmp_path / 'paragraphs.md'
    md.write_text(': Данные {#tbl:b}\n\n| X |\n|---|\n| 1 |\n\nСм. Таблицу\n\n@tbl:b в начале абзаца.\n',
                  encoding='utf-8')
    assert [w.line for w in validate(md) if 'нет слова' in w.message] == [9]


def test_document_rules_warnings():
    from md2gost.validator import _check_rules
    warnings = _check_rules(['## Заголовок.', 'Текст[^note]', '# Приложение Ё',
                             '```markdown', '## Пример.', 'Текст[^skip]', '```'])
    assert [w.line for w in warnings] == [1, 2, 3]


def _validate(tmp_path, body):
    md = tmp_path / "rules.md"
    md.write_text("---\ntitle: T\nauthor: A\ndate: 2026-01-01\nlang: ru\n---\n\n" + body, encoding="utf-8")
    return [w.message for w in validate(md)]


def test_formula_before_where_needs_comma(tmp_path):
    messages = _validate(tmp_path, "## Раздел\n\n$$\nx = y\n$$ {#eq:a}\n\nгде $x$ — икс.\n\n"
                                   "$$\nz = 1,\n$$\n\nгде $z$ — зет.\n")
    assert [m for m in messages if "п. 5.4" in m] == [
        "Перед пояснением «где» формула заканчивается запятой (п. 5.4); строки 10 (всего 1)"]


def test_dash_typed_as_minus(tmp_path):
    messages = _validate(tmp_path, "## Раздел\n\nЭкономика – это деятельность, $a - b$ и `x - y`.\n\n"
                                   "Экономика — это деятельность.\n")
    assert any("п. 1.11" in m and "(всего 1)" in m for m in messages)


def test_list_item_case_and_punctuation(tmp_path):
    messages = _validate(tmp_path, "## Раздел\n\n- Первый пункт;\n- второй пункт.\n\n"
                                   "1. первый шаг.\n2. Второй шаг\n\n"
                                   "# Список использованных источников\n\n1. leaves – Go library\n")
    assert sum("п. 4.3" in m for m in messages) == 1
    assert sum("п. 4.4" in m for m in messages) == 2


def test_sources_count_and_appendix_references(tmp_path):
    messages = _validate(tmp_path, "## Раздел\n\nДанные в Приложении А.\n\n"
                                   "# Список использованных источников\n\n1. Один.\n2. Два.\n\n"
                                   "# Приложение А\n\nТекст.\n\n# Приложение Б\n\nТекст.\n")
    assert any("не менее 7 (п. 9.2)" in m for m in messages)
    assert any("Приложение Б нет ссылки" in m for m in messages)
    assert not any("Приложение А нет ссылки" in m for m in messages)


def test_caption_and_heading_form(tmp_path):
    messages = _validate(tmp_path, "## раздел\n\n: Данные таблицы. {#tbl:a}\n\n| X |\n|---|\n| 1 |\n")
    assert any("п. 2.2.4" in m for m in messages)
    assert any("п. 6.2, 7.2" in m for m in messages)
