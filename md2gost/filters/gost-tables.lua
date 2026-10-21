-- Number all captioned media in document order, including nested blocks.
-- Resolve references in a second pass so forward references also work.
local function caption_with_prefix(caption, prefix)
  if #caption.long == 0 then return end
  local content = pandoc.Inlines({pandoc.Str(prefix), pandoc.Space()})
  for _, inline in ipairs(caption.long[1].content) do content:insert(inline) end
  caption.long[1] = pandoc.Plain(content)
end

-- Pandoc parses $$...$$ {#eq:id} as Math + Space + Str, not a Span.
local function equation_label(el)
  if el.t == 'Para' and #el.content == 3 and el.content[1].t == 'Math'
      and el.content[1].mathtype == 'DisplayMath' and el.content[3].t == 'Str' then
    return el.content[3].text:match('^{#(eq:[^}]+)}$')
  end
end

-- The paragraph right after a numbered formula that starts with «где» lists one
-- symbol per source line. Each line becomes a paragraph in the Where style.
local function split_where(blocks)
  local result = pandoc.Blocks({})
  local previous = nil
  for _, block in ipairs(blocks) do
    local first = block.t == 'Para' and block.content[1] or nil
    if previous and equation_label(previous) and first and first.t == 'Str'
        and pandoc.text.lower(first.text):match('^где[,:]?$') then
      local lines = {pandoc.Inlines({})}
      for _, inline in ipairs(block.content) do
        if inline.t == 'SoftBreak' then table.insert(lines, pandoc.Inlines({}))
        else lines[#lines]:insert(inline) end
      end
      local paras = pandoc.Blocks({})
      for _, line in ipairs(lines) do
        while #line > 0 and line[1].t == 'Space' do line:remove(1) end
        while #line > 0 and line[#line].t == 'Space' do line:remove(#line) end
        if #line > 0 then paras:insert(pandoc.Para(line)) end
      end
      result:insert(pandoc.Div(paras, pandoc.Attr('', {}, {{'custom-style', 'Where'}})))
    else
      result:insert(block)
    end
    previous = block
  end
  return result
end

function Pandoc(doc)
  doc = doc:walk { Blocks = split_where }
  local section = ''
  local counts = {fig = 0, tbl = 0, eq = 0}
  local labels = {}
  local function next_number(kind, id)
    counts[kind] = counts[kind] + 1
    local number = section ~= '' and (section .. '.' .. counts[kind]) or tostring(counts[kind])
    if id ~= '' then
      if labels[id] then error('Повторное определение ' .. id) end
      labels[id] = number
    end
    return number
  end
  doc = doc:walk {
    Header = function(el)
      local new_section = el.attributes['gost-section']
      if new_section ~= nil and new_section ~= section then
        section = new_section
        counts = {fig = 0, tbl = 0, eq = 0}
      end
      return el
    end,
    Figure = function(el)
      if #el.caption.long == 0 then return el end
      local number = next_number('fig', el.identifier)
      caption_with_prefix(el.caption, 'Рисунок ' .. number .. ' –')
      -- Keep bookmarks but stop pandoc-crossref from adding its own number.
      if el.identifier:match('^fig:') then el.identifier = 'gost-' .. el.identifier end
      return el
    end,
    Table = function(el)
      if #el.caption.long == 0 then return el end
      local number = next_number('tbl', el.identifier)
      caption_with_prefix(el.caption, 'Таблица ' .. number .. ' –')
      if el.identifier:match('^tbl:') then el.identifier = 'gost-' .. el.identifier end
      return el
    end,
    Para = function(el)
      local id = equation_label(el)
      if id then
        local number = next_number('eq', id)
        local math = el.content[1]
        math.text = math.text .. '\\qquad{(' .. number .. ')}'
        el.content = pandoc.Inlines({math})
      end
      return el
    end
  }
  doc = doc:walk {
    Cite = function(el)
      local content = pandoc.Inlines({})
      for i, cit in ipairs(el.citations) do
        local kind = cit.id:match('^(fig):') or cit.id:match('^(tbl):') or cit.id:match('^(eq):')
        -- Leave mixed bibliography/media groups intact for the next filter.
        if not kind or not labels[cit.id] then return el end
        if i > 1 then content:insert(pandoc.Str(';')); content:insert(pandoc.Space()) end
        content:extend(cit.prefix)
        if #cit.prefix > 0 then content:insert(pandoc.Space()) end
        -- Only the number: the author writes «Рисунке», «Таблицы» in the right case.
        content:insert(pandoc.Str(kind == 'eq' and ('(' .. labels[cit.id] .. ')') or labels[cit.id]))
        if #cit.suffix > 0 then content:insert(pandoc.Space()); content:extend(cit.suffix) end
      end
      return content
    end,
    Div = function(el)
      if not el.classes:includes('landscape') then return el end
      local blocks = pandoc.Blocks({pandoc.RawBlock('openxml',
        '<w:p><w:pPr><w:pStyle w:val="GOSTLandscapeStart"/></w:pPr></w:p>')})
      blocks:extend(el.content)
      blocks:insert(pandoc.RawBlock('openxml',
        '<w:p><w:pPr><w:pStyle w:val="GOSTLandscapeEnd"/></w:pPr></w:p>'))
      return blocks
    end
  }
  return doc
end
