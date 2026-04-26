local counters = {}
for i = 1, 6 do counters[i] = 0 end

local function section_number(level)
  local parts = {}
  for i = 2, level do
    table.insert(parts, tostring(counters[i]))
  end
  return table.concat(parts, ".")
end

local page_break = pandoc.RawBlock("openxml", "<w:p><w:r><w:br w:type=\"page\"/></w:r></w:p>")

function Header(el)
  if el.level == 1 then
    el.content = el.content:walk {
      Str = function(s)
        return pandoc.Str(pandoc.text.upper(s.text))
      end
    }
    el.classes:insert("unnumbered")
    el.classes:insert("unlisted")
    for i = 2, 6 do counters[i] = 0 end
    return {page_break, el}
  else
    counters[el.level] = counters[el.level] + 1
    for i = el.level + 1, 6 do counters[i] = 0 end
    local num = section_number(el.level)
    el.content = pandoc.Inlines({pandoc.Str(num), pandoc.Space()}) .. el.content
  end
  return el
end
