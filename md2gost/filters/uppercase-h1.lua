-- Markdown H1 is structural; H2/H3/H4 become Word section levels 1/2/3.
local counters = {0, 0, 0, 0, 0, 0}
local appendix = nil
local appendix_counters = {0, 0, 0, 0, 0, 0}

function Header(el)
  local level = el.level
  if level == 1 then
    local text = pandoc.utils.stringify(el.content)
    appendix = pandoc.text.upper(text):match('^ПРИЛОЖЕНИЕ%s+(%S+)$')
    for i = 3, 6 do counters[i] = 0 end
    if appendix then
      appendix_counters = {0, 0, 0, 0, 0, 0}
      el.content = pandoc.Inlines({pandoc.Str('Приложение ' .. appendix)})
      el.attributes['gost-section'] = appendix
    else
      el.content = el.content:walk {
        Str = function(s) return pandoc.Str(pandoc.text.upper(s.text)) end
      }
      el.attributes['gost-section'] = ''
    end
    el.classes:insert('unnumbered')
    -- Annotation has no entry in the sample's TOC; other structural parts do.
    if pandoc.text.upper(text) == 'АННОТАЦИЯ' then el.classes:insert('unlisted') end
  else
    local active = appendix and appendix_counters or counters
    active[level] = active[level] + 1
    for i = level + 1, 6 do active[i] = 0 end
    local parts = {appendix or tostring(active[2])}
    for i = appendix and 2 or 3, level do table.insert(parts, tostring(active[i])) end
    -- Appendix subsection counters are independent of the main chapters.
    el.content = pandoc.Inlines({pandoc.Str(table.concat(parts, '.')), pandoc.Space()}) .. el.content
    if level == 2 and not appendix then
      el.content = el.content:walk {
        Str = function(s) return pandoc.Str(pandoc.text.upper(s.text)) end
      }
    end
    el.attributes['gost-section'] = appendix or tostring(counters[2])
    el.level = level - 1
    el.classes:insert('unnumbered')
  end
  return el
end
