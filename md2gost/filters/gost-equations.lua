local function escape_xml(s)
  s = s:gsub("&", "&amp;")
  s = s:gsub("<", "&lt;")
  s = s:gsub(">", "&gt;")
  s = s:gsub('"', "&quot;")
  return s
end

function Para(el)
  if #el.content ~= 1 then return el end

  local span = el.content[1]
  if span.t ~= "Span" then return el end
  if not span.identifier:match("^eq:") then return el end
  if #span.content ~= 1 then return el end

  local math_el = span.content[1]
  if math_el.t ~= "Math" or math_el.mathtype ~= "DisplayMath" then return el end

  local tex = math_el.text
  local eq_body, eq_num = tex:match("^(.-)%s*\\qquad{(%([^)]+%))}%s*$")
  if not eq_body then return el end

  eq_body = eq_body:gsub("^%s+", ""):gsub("%s+$", "")

  local xml = string.format(
    '<w:p>'
    .. '<w:pPr>'
    ..   '<w:tabs>'
    ..     '<w:tab w:val="center" w:pos="4820"/>'
    ..     '<w:tab w:val="right" w:pos="9639"/>'
    ..   '</w:tabs>'
    ..   '<w:spacing w:before="120" w:after="120"/>'
    ..   '<w:ind w:firstLine="0"/>'
    ..   '<w:jc w:val="left"/>'
    .. '</w:pPr>'
    .. '<w:r><w:tab/></w:r>'
    .. '<w:r><w:rPr>'
    ..   '<w:rFonts w:ascii="Cambria Math" w:hAnsi="Cambria Math"/>'
    ..   '<w:sz w:val="28"/><w:szCs w:val="28"/>'
    .. '</w:rPr>'
    .. '<w:t xml:space="preserve">%s</w:t></w:r>'
    .. '<w:r><w:tab/></w:r>'
    .. '<w:r><w:rPr><w:sz w:val="28"/><w:szCs w:val="28"/></w:rPr>'
    .. '<w:t xml:space="preserve">%s</w:t></w:r>'
    .. '</w:p>',
    escape_xml(eq_body), escape_xml(eq_num)
  )

  return pandoc.RawBlock("openxml", xml)
end
