local MAX_LINES_PER_TABLE = 42

local page_break = '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'

local function escape_xml(s)
  s = s:gsub("&", "&amp;")
  s = s:gsub("<", "&lt;")
  s = s:gsub(">", "&gt;")
  s = s:gsub('"', "&quot;")
  return s
end

local function make_caption(text)
  return string.format(
    '<w:p>'
    .. '<w:pPr><w:pStyle w:val="GOSTListingCaption"/><w:keepNext/><w:spacing w:before="120" w:after="0"/></w:pPr>'
    .. '<w:r><w:rPr></w:rPr>'
    .. '<w:t xml:space="preserve">%s</w:t></w:r>'
    .. '</w:p>',
    escape_xml(text)
  )
end

local function make_code_paragraph(line)
  return string.format(
    '<w:p>'
    .. '<w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/>'
    .. '<w:ind w:firstLine="0"/><w:jc w:val="left"/><w:wordWrap w:val="1"/></w:pPr>'
    .. '<w:r><w:rPr>'
    .. '<w:rFonts w:ascii="Courier New" w:hAnsi="Courier New" w:cs="Courier New"/>'
    .. '<w:sz w:val="20"/><w:szCs w:val="20"/>'
    .. '</w:rPr>'
    .. '<w:t xml:space="preserve">%s</w:t></w:r>'
    .. '</w:p>',
    escape_xml(line)
  )
end

local function make_table(code_paragraphs)
  return string.format(
    '<w:tbl>'
    .. '<w:tblPr>'
    ..   '<w:tblW w:w="5000" w:type="pct"/>'
    ..   '<w:tblBorders>'
    ..     '<w:top w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
    ..     '<w:left w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
    ..     '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
    ..     '<w:right w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
    ..   '</w:tblBorders>'
    ..   '<w:tblCellMar>'
    ..     '<w:top w:w="40" w:type="dxa"/>'
    ..     '<w:left w:w="80" w:type="dxa"/>'
    ..     '<w:bottom w:w="40" w:type="dxa"/>'
    ..     '<w:right w:w="80" w:type="dxa"/>'
    ..   '</w:tblCellMar>'
    .. '</w:tblPr>'
    .. '<w:tr><w:trPr><w:cantSplit/></w:trPr><w:tc>'
    ..   '<w:tcPr><w:tcW w:w="5000" w:type="pct"/></w:tcPr>'
    ..   '%s'
    .. '</w:tc></w:tr>'
    .. '</w:tbl>',
    table.concat(code_paragraphs, "")
  )
end

local listing_count_in_appendix = 0

function Header(el)
  if el.level == 1 then
    listing_count_in_appendix = 0
  end
end

function CodeBlock(el)
  local first_line, rest = el.text:match("^(Листинг[^\n]*)\n(.*)")
  if not first_line then return el end

  listing_count_in_appendix = listing_count_in_appendix + 1

  rest = rest:gsub("%s+$", "")

  local continuation_caption = 'Продолжение ' .. first_line:gsub('^Листинг', 'листинга')

  local lines = {}
  for line in (rest .. "\n"):gmatch("([^\n]*)\n") do
    table.insert(lines, line)
  end

  local chunks = {}
  local chunk = {}
  local visual_lines = 0
  for _, line in ipairs(lines) do
    -- Courier New 10pt: at most 76 characters across the portrait text area.
    local length = utf8.len(line) or #line
    local needed = math.max(1, math.ceil(length / 76))
    if visual_lines + needed > MAX_LINES_PER_TABLE and #chunk > 0 then
      table.insert(chunks, chunk)
      chunk = {}
      visual_lines = 0
    end
    table.insert(chunk, line)
    visual_lines = visual_lines + needed
  end
  if #chunk > 0 then table.insert(chunks, chunk) end

  local blocks = {}
  for idx, chunk in ipairs(chunks) do
    local caption
    if idx == 1 then
      caption = first_line
    elseif idx == #chunks then
      caption = 'Окончание ' .. first_line:gsub('^Листинг', 'листинга')
    else
      caption = continuation_caption
    end

    if idx > 1 or listing_count_in_appendix > 1 then
      table.insert(blocks, pandoc.RawBlock("openxml", page_break))
    end

    table.insert(blocks, pandoc.RawBlock("openxml", make_caption(caption)))

    local code_paragraphs = {}
    for _, line in ipairs(chunk) do
      table.insert(code_paragraphs, make_code_paragraph(line))
    end
    table.insert(blocks, pandoc.RawBlock("openxml", make_table(code_paragraphs)))
  end

  return blocks
end
