-- Markdown H1 is structural; H2/H3/H4 become Word section levels 1/2/3.
-- Inside an appendix H2 is a section «Приложение А.1» (rules 10.4), inside the
-- list of sources H2 is a rubric (table 9.1).
local APPENDIX = 'Приложение'

local function upper(inlines)
  return inlines:walk {
    Str = function(s) return pandoc.Str(pandoc.text.upper(s.text)) end
  }
end

local function styled(style, inlines)
  return pandoc.Div({pandoc.Para(inlines)}, pandoc.Attr('', {}, {{'custom-style', style}}))
end

local function trim(s)
  -- Lua character classes are locale-dependent and operate on bytes: %s can
  -- treat the final 0xA0 byte of Cyrillic «Р» as whitespace. Trim ASCII only.
  return (s:gsub('^[ \t\r\n\v\f]+', ''):gsub('[ \t\r\n\v\f]+$', ''))
end

-- «Приложение А», «Приложение А. Название», «Приложение А — Название».
local function appendix_heading(text)
  if pandoc.text.upper(text:sub(1, #APPENDIX)) ~= pandoc.text.upper(APPENDIX) then return end
  local letter, rest = text:sub(#APPENDIX + 1):match('^[ \t\r\n]+([^ \t\r\n]+)(.*)$')
  if not letter then return end
  letter = letter:gsub('%.$', '')
  rest = trim(rest)
  for _, dash in ipairs({'—', '–', '-', '.'}) do
    if rest:sub(1, #dash) == dash then rest = trim(rest:sub(#dash + 1)) end
  end
  return pandoc.text.upper(letter), rest
end

function Pandoc(doc)
  local blocks = pandoc.Blocks({})
  local counters = {0, 0, 0, 0, 0, 0}
  local appendix = nil
  local appendix_counters = {0, 0, 0, 0, 0, 0}
  local bibliography = false
  local appendices = {}
  -- Position of an empty «Приложения» part that should receive the list.
  local list_at, list_open, list_empty = nil, false, false

  for _, el in ipairs(doc.blocks) do
    if el.t ~= 'Header' then
      if list_open then list_empty = false end
      -- A title written as a custom-style block completes the appendix list.
      if appendix and el.t == 'Div' and el.attributes['custom-style'] == 'Appendix Title'
          and appendices[#appendices].title == '' then
        appendices[#appendices].title = pandoc.utils.stringify(el)
      end
      blocks:insert(el)
    elseif el.level == 1 then
      local text = pandoc.utils.stringify(el.content)
      local letter, title = appendix_heading(text)
      for i = 3, 6 do counters[i] = 0 end
      bibliography = false
      list_open = false
      el.classes:insert('unnumbered')
      if letter then
        appendix = letter
        appendix_counters = {0, 0, 0, 0, 0, 0}
        el.content = pandoc.Inlines({pandoc.Str(APPENDIX .. ' ' .. letter)})
        el.attributes['gost-section'] = letter
        blocks:insert(el)
        table.insert(appendices, {letter = letter, title = title})
        if title ~= '' then blocks:insert(styled('Appendix Title', pandoc.Inlines(title))) end
      else
        local name = pandoc.text.upper(text)
        appendix = nil
        el.content = upper(el.content)
        el.attributes['gost-section'] = ''
        -- Annotation has no entry in the sample's TOC; other structural parts do.
        if name == 'АННОТАЦИЯ' then el.classes:insert('unlisted') end
        bibliography = name:match('^СПИСОК ИСПОЛЬЗ') or name:match('^СПИСОК ИСТОЧНИК')
          or name:match('^БИБЛИОГРАФ')
        blocks:insert(el)
        if name == 'ПРИЛОЖЕНИЯ' then list_at, list_open, list_empty = #blocks, true, true end
      end
    elseif bibliography then
      blocks:insert(styled('Bibliography Heading', el.content))
    elseif appendix and el.level == 2 then
      appendix_counters[2] = appendix_counters[2] + 1
      for i = 3, 6 do appendix_counters[i] = 0 end
      blocks:insert(styled('Appendix Section',
        pandoc.Inlines(APPENDIX .. ' ' .. appendix .. '.' .. appendix_counters[2])))
      blocks:insert(styled('Appendix Title', el.content))
    else
      local level = el.level
      local active = appendix and appendix_counters or counters
      active[level] = active[level] + 1
      for i = level + 1, 6 do active[i] = 0 end
      local parts = {appendix or tostring(active[2])}
      for i = appendix and 2 or 3, level do table.insert(parts, tostring(active[i])) end
      -- Appendix subsection counters are independent of the main chapters.
      el.content = pandoc.Inlines({pandoc.Str(table.concat(parts, '.')), pandoc.Space()}) .. el.content
      if level == 2 and not appendix then el.content = upper(el.content) end
      el.attributes['gost-section'] = appendix or tostring(counters[2])
      el.level = level - 1
      el.classes:insert('unnumbered')
      blocks:insert(el)
    end
  end

  -- Rules 10.3: the first sheet of «Приложения» lists every appendix.
  if list_empty and #appendices > 0 then
    local items = pandoc.Blocks({})
    for _, a in ipairs(appendices) do
      local line = APPENDIX .. ' ' .. a.letter
      if a.title ~= '' then line = line .. ' – ' .. a.title end
      items:insert(pandoc.Para(pandoc.Inlines(line)))
    end
    local result = pandoc.Blocks({})
    for i, el in ipairs(blocks) do
      result:insert(el)
      if i == list_at then result:extend(items) end
    end
    blocks = result
  end
  doc.blocks = blocks
  return doc
end
