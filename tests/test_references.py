"""Reference rendering that does not depend on the full layout fixture."""
import re
import zipfile

from md2gost.converter import ConvertOptions, convert


def paragraphs(path):
    xml = zipfile.ZipFile(path).read('word/document.xml').decode()
    return [''.join(re.findall(r'<w:t[^>]*>([^<]*)</w:t>', p))
            for p in re.findall(r'<w:p[ >].*?</w:p>', xml, re.S)]


def test_consecutive_equation_group_renders_as_range(tmp_path):
    source = tmp_path / 'in.md'
    source.write_text('## Раздел\n\n' + ''.join(f'$$ {c}=1 $$ {{#eq:{c}}}\n\n' for c in 'abcd')
                      + 'Формулы [@eq:a; @eq:b; @eq:c; @eq:d] и [@eq:a; @eq:c; @eq:d], '
                      'пара [@eq:a; @eq:b], формула @eq:b.\n', encoding='utf-8')
    output = tmp_path / 'out.docx'
    convert(source, output, options=ConvertOptions(toc=False, title_page=False))
    assert ('Формулы 1.1 – 1.4 и (1.1); (1.3); (1.4), пара (1.1); (1.2), формула (1.2).'
            in paragraphs(output))
