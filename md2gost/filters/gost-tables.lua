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

-- The paragraph right after a formula that starts with «где» lists one symbol
-- per source line. Each line becomes a paragraph in the Where style; a tab
-- puts every symbol at the style's tab stop, one under another (rules 5.8).
local TAB = pandoc.RawInline('openxml', '<w:r><w:tab/></w:r>')

local function is_display(el)
  return el and el.t == 'Para' and el.content[1] and el.content[1].t == 'Math'
    and el.content[1].mathtype == 'DisplayMath'
end

local function split_where(blocks)
  local result = pandoc.Blocks({})
  local previous = nil
  for _, block in ipairs(blocks) do
    local first = block.t == 'Para' and block.content[1] or nil
    if is_display(previous) and first and first.t == 'Str'
        and pandoc.text.lower(first.text):match('^где[,:]?$') then
      local lines = {pandoc.Inlines({})}
      for _, inline in ipairs(block.content) do
        if inline.t == 'SoftBreak' then table.insert(lines, pandoc.Inlines({}))
        else lines[#lines]:insert(inline) end
      end
      local paras = pandoc.Blocks({})
      for i, line in ipairs(lines) do
        while #line > 0 and line[1].t == 'Space' do line:remove(1) end
        while #line > 0 and line[#line].t == 'Space' do line:remove(#line) end
        if #line > 0 then
          if i == 1 then
            -- «где» without a colon (5.8), then the tab instead of a space.
            line[1] = pandoc.Str('где')
            if line[2] and line[2].t == 'Space' then line:remove(2) end
            line:insert(2, TAB)
          else
            line:insert(1, TAB)
          end
          paras:insert(pandoc.Para(line))
        end
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
  local referenced = {}
  doc:walk { Cite = function(el)
    for _, cit in ipairs(el.citations) do referenced[cit.id] = true end
  end }
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
      local breaks = el.attributes['break-after']
      if breaks then
        if not breaks:match('^%d+[, %d]*$') then error('break-after: ожидаются номера строк') end
        return {pandoc.RawBlock('openxml', '<w:p><w:pPr><w:pStyle w:val="GOSTTableBreaks"/></w:pPr><w:r><w:t>' .. breaks .. '</w:t></w:r></w:p>'), el}
      end
      return el
    end,
    Para = function(el)
      local id = equation_label(el)
      if id then
        local math = el.content[1]
        if referenced[id] then
          local number = next_number('eq', id)
          math.text = math.text .. '\\qquad{(' .. number .. ')}'
        end
        el.content = pandoc.Inlines({math})
      end
      return el
    end
  }
  -- Three or more consecutive formulas in one group read as a range: «2.5 – 2.9».
  local function equation_range(citations)
    if #citations < 3 then return nil end
    local chapter, previous
    for _, cit in ipairs(citations) do
      local label = cit.id:match('^eq:') and labels[cit.id]
      if not label or #cit.prefix > 0 or #cit.suffix > 0 then return nil end
      local head, n = label:match('^(.-)(%d+)$')
      n = tonumber(n)
      if previous and (head ~= chapter or n ~= previous + 1) then return nil end
      chapter, previous = head, n
    end
    return labels[citations[1].id] .. ' – ' .. labels[citations[#citations].id]
  end
  doc = doc:walk {
    Cite = function(el)
      local range = equation_range(el.citations)
      if range then return pandoc.Str(range) end
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
