local tbl_labels = {}

function Pandoc(doc)
  local h2_counter = 0
  local tbl_counter = 0

  for _, block in ipairs(doc.blocks) do
    if block.t == "Header" then
      if block.level == 1 then
        h2_counter = 0
        tbl_counter = 0
      elseif block.level == 2 then
        h2_counter = h2_counter + 1
        tbl_counter = 0
      end
    elseif block.t == "Table" then
      local label = block.attr.identifier
      if label ~= "" and label:match("^tbl:") then
        tbl_counter = tbl_counter + 1
        tbl_labels[label] = tostring(h2_counter) .. "." .. tostring(tbl_counter)
      end
    end
  end

  doc = doc:walk {
    Table = function(el)
      local label = el.attr.identifier
      if label == "" or not label:match("^tbl:") then return el end
      local num = tbl_labels[label]
      if not num then return el end

      local orig = pandoc.List({})
      if el.caption and el.caption.long and #el.caption.long > 0 then
        orig = el.caption.long[1].content
      end

      local prefix = pandoc.List({pandoc.Str("Таблица " .. num .. " – ")})
      for _, inline in ipairs(orig) do prefix:insert(inline) end

      el.caption.long = {pandoc.Plain(prefix)}
      el.attr.identifier = ""
      return el
    end,

    Cite = function(el)
      for _, cit in ipairs(el.citations) do
        local cid = cit.id
        if cid and cid:match("^tbl:") and tbl_labels[cid] then
          return pandoc.Str("табл. " .. tbl_labels[cid])
        end
      end
      return el
    end
  }

  return doc
end
