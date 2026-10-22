-- A code block whose first line starts with «Листинг» becomes a caption and a
-- framed one-column table, one row per code line (rules 8.2, 8.4, 8.5). Rows let
-- measured pagination or break-after cut the listing at a page boundary and
-- continue it under «Продолжение Листинга N».

local function escape_xml(s)
  return (s:gsub('&', '&amp;'):gsub('<', '&lt;'):gsub('>', '&gt;'):gsub('"', '&quot;'))
end

local function caption(text)
  return '<w:p><w:pPr><w:pStyle w:val="GOSTListingCaption"/></w:pPr>'
    .. '<w:r><w:t xml:space="preserve">' .. escape_xml(text) .. '</w:t></w:r></w:p>'
end

local function row(line)
  return '<w:tr><w:trPr><w:cantSplit/></w:trPr><w:tc><w:tcPr><w:tcW w:w="5000" w:type="pct"/></w:tcPr>'
    .. '<w:p><w:pPr><w:pStyle w:val="SourceCode"/><w:wordWrap w:val="1"/></w:pPr>'
    .. '<w:r><w:rPr><w:rFonts w:ascii="Courier New" w:hAnsi="Courier New" w:cs="Courier New"/>'
    .. '<w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr>'
    .. '<w:t xml:space="preserve">' .. escape_xml(line) .. '</w:t></w:r></w:p></w:tc></w:tr>'
end

local function frame(rows)
  local border = 'w:val="single" w:sz="4" w:space="0" w:color="000000"'
  return '<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/><w:jc w:val="center"/>'
    .. '<w:tblBorders><w:top ' .. border .. '/><w:left ' .. border .. '/><w:bottom ' .. border .. '/>'
    .. '<w:right ' .. border .. '/><w:insideH w:val="nil"/><w:insideV w:val="nil"/></w:tblBorders>'
    .. '<w:tblLayout w:type="fixed"/>'
    .. '<w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="80" w:type="dxa"/>'
    .. '<w:bottom w:w="0" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar>'
    .. '</w:tblPr><w:tblGrid><w:gridCol w:w="9638"/></w:tblGrid>' .. table.concat(rows) .. '</w:tbl>'
end

function CodeBlock(el)
  local first_line, rest = el.text:match('^(Листинг[^\n]*)\n(.*)')
  if not first_line then return el end
  -- «Листинг 1.7 — Процедура» (8.2): the dash between number and name.
  for _, dash in ipairs({'–', '-'}) do
    first_line = first_line:gsub('^(Листинг%s+%S+)%s+' .. dash .. '%s+', '%1 — ')
  end
  rest = rest:gsub('%s+$', '')

  local lines = {}
  for line in (rest .. '\n'):gmatch('([^\n]*)\n') do table.insert(lines, line) end
  -- Lines referenced in the text are numbered with step 10 (8.3).
  if el.classes:includes('numberLines') or el.classes:includes('number-lines') then
    local width = #tostring(10 * #lines)
    for i, line in ipairs(lines) do
      lines[i] = string.format('%-' .. width .. 's  %s', tostring(10 * i), line)
    end
  end
  local rows = {}
  for _, line in ipairs(lines) do table.insert(rows, row(line)) end

  local blocks = {pandoc.RawBlock('openxml', caption(first_line))}
  local breaks = el.attributes['break-after']
  if breaks then
    if not breaks:match('^%d+[, %d]*$') then error('break-after: ожидаются номера строк') end
    table.insert(blocks, pandoc.RawBlock('openxml',
      '<w:p><w:pPr><w:pStyle w:val="GOSTTableBreaks"/></w:pPr><w:r><w:t>' .. breaks .. '</w:t></w:r></w:p>'))
  end
  table.insert(blocks, pandoc.RawBlock('openxml', frame(rows)))
  return blocks
end
