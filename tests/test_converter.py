from pathlib import Path
from unittest.mock import patch

import pytest

from md2gost.converter import ConversionError, ConvertOptions, build_command, convert

FIXTURES = Path(__file__).parent / "fixtures"

MINIMAL_TEMPLATE = Path(__file__).parent / "fixtures" / "minimal_template.docx"


def _ensure_minimal_template():
    """Создать минимальный .docx если не существует (pandoc --print-default-data-file)."""
    if not MINIMAL_TEMPLATE.exists():
        import subprocess
        result = subprocess.run(
            ["pandoc", "--print-default-data-file", "reference.docx"],
            capture_output=True,
        )
        if result.returncode == 0:
            MINIMAL_TEMPLATE.write_bytes(result.stdout)
        else:
            pytest.skip("Не удалось создать минимальный шаблон")


def test_build_command_default():
    opts = ConvertOptions()
    cmd = build_command(
        Path("in.md"), Path("out.docx"), Path("tmpl.docx"), opts
    )
    assert "pandoc" in cmd
    assert "--reference-doc" in cmd
    assert "--toc" in cmd
    assert "--number-sections" not in cmd
    assert "-o" in cmd

    lua_idxs = [i for i, x in enumerate(cmd) if x == "--lua-filter"]
    assert len(lua_idxs) == 3
    lua_paths = [cmd[i + 1] for i in lua_idxs]
    assert any("uppercase-h1" in p for p in lua_paths)
    assert any("gost-tables" in p for p in lua_paths)
    assert any("appendix-listing" in p for p in lua_paths)

    last_lua_idx = lua_idxs[-1]
    xref_idx = cmd.index("pandoc-crossref")
    assert last_lua_idx < xref_idx


def test_build_command_no_toc():
    opts = ConvertOptions(toc=False)
    cmd = build_command(Path("in.md"), Path("out.docx"), Path("tmpl.docx"), opts)
    assert "--toc" not in cmd


def test_build_command_toc_depth():
    opts = ConvertOptions(toc_depth=2)
    cmd = build_command(Path("in.md"), Path("out.docx"), Path("tmpl.docx"), opts)
    idx = cmd.index("--toc-depth")
    assert cmd[idx + 1] == "2"


def test_missing_pandoc():
    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="Не найдены в PATH"):
            convert(FIXTURES / "valid.md")


def test_convert_nonexistent_file(tmp_path):
    _ensure_minimal_template()
    with pytest.raises((ConversionError, FileNotFoundError)):
        convert(tmp_path / "ghost.md", template=MINIMAL_TEMPLATE)


def test_convert_success(tmp_path):
    _ensure_minimal_template()
    out = tmp_path / "out.docx"
    result_path, elapsed = convert(
        FIXTURES / "valid.md",
        output_path=out,
        template=MINIMAL_TEMPLATE,
    )
    assert result_path == out
    assert out.exists()
    assert elapsed > 0


def test_default_output_name(tmp_path):
    _ensure_minimal_template()
    md = tmp_path / "report.md"
    md.write_text(
        "---\ntitle: T\nauthor: A\ndate: 2026-01-01\n---\n\n# Раздел\n",
        encoding="utf-8",
    )
    out, _ = convert(md, template=MINIMAL_TEMPLATE)
    assert out == tmp_path / "report.docx"
    assert out.exists()
