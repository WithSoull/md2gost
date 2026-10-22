-- Quotation marks (rules 1.10): «…» in Russian text, „…“ inside them;
-- English quotations keep “…” and ‘…’. Only quotes typed as " or ' change:
-- marks written by the author stay as they are.
local function russian(inlines)
  -- Lead bytes of Cyrillic letters in UTF-8.
  return pandoc.utils.stringify(inlines):find('[\208\209]') ~= nil
end

return {
  {
    traverse = 'topdown',
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
