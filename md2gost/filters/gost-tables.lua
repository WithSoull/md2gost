-- Number all captioned media in document order, including nested blocks.
-- Resolve references in a second pass so forward references also work.
local function caption_with_prefix(caption, prefix)
  if #caption.long == 0 then return end
  local content = pandoc.Inlines({pandoc.Str(prefix), pandoc.Space()})
  for _, inline in ipairs(caption.long[1].content) do content:insert(inline) end
  caption.long[1] = pandoc.Plain(content)
end

function Pandoc(doc)
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
      -- Pandoc parses $$...$$ {#eq:id} as Math + Space + Str, not a Span.
      if #el.content == 3 and el.content[1].t == 'Math'
          and el.content[1].mathtype == 'DisplayMath' and el.content[3].t == 'Str' then
        local id = el.content[3].text:match('^{#(eq:[^}]+)}$')
        if id then
          local number = next_number('eq', id)
          local math = el.content[1]
          math.text = math.text .. '\\qquad{(' .. number .. ')}'
          el.content = pandoc.Inlines({math})
        end
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
        local prefix = ({fig = 'рис. ', tbl = 'табл. ', eq = ''})[kind]
        content:insert(pandoc.Str(prefix .. (kind == 'eq' and ('(' .. labels[cit.id] .. ')') or labels[cit.id])))
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
