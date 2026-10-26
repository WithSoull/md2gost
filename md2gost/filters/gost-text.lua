-- Quotation marks (rules 1.10): «…» in Russian text, „…“ inside them;
-- English quotations keep “…” and ‘…’. Only quotes typed as " or ' change:
-- marks written by the author stay as they are.
local function russian(inlines)
  -- Lead bytes of Cyrillic letters in UTF-8.
  return pandoc.utils.stringify(inlines):find('[\208\209]') ~= nil
end

-- A long address cannot break, so a justified line before it stretches. A
-- zero-width space after «/», «.», «-» and similar marks lets the printed
-- address wrap; the link target stays intact.
local ZWSP = '\u{200B}'

return {
  {
    traverse = 'topdown',
    Link = function(el)
      local text = pandoc.utils.stringify(el.content)
      if #el.content == 1 and el.content[1].t == 'Str' and utf8.len(text) > 30 then
        el.content = {pandoc.Str((text:gsub('([/%.%-_?&=#]+)', '%1' .. ZWSP)))}
      end
      return el
    end,
    Quoted = function(el)
      local ru = russian(el.content)
      local inner = el.content:walk {
        Quoted = function(q)
          return pandoc.Inlines({pandoc.Str(ru and '„' or '‘')}) .. q.content
            .. pandoc.Inlines({pandoc.Str(ru and '“' or '’')})
        end
      }
      return pandoc.Inlines({pandoc.Str(ru and '«' or '“')}) .. inner
        .. pandoc.Inlines({pandoc.Str(ru and '»' or '”')}), false
    end,
  }
}
