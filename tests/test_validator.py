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
        "---\ntitle: T\nauthor: A\ndate: 2026-01-01\n---\n\n![рис](r.png){#fig:scheme}\n\nСм. @fig:scheme\n",
        encoding="utf-8",
    )
    warnings = validate(md)
    assert not any("@fig:scheme" in w.message for w in warnings)


def test_invalid_encoding(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_bytes(b"\xff\xfe bad encoding")
    with pytest.raises(ValidationError):
        validate(bad)
