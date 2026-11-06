-- Minimal JSON encoder for tests (Lua 5.1 / LuaJIT).
local json = {}

local function esc(s)
  return (s:gsub('[%c"\\]', function(c)
    if c == "\n" then return "\\n" end
    if c == '"' then return '\\"' end
    if c == "\\" then return "\\\\" end
    return string.format("\\u%04x", c:byte())
  end))
end

local function is_array(t)
  local n = 0
  for k in pairs(t) do
    if type(k) ~= "number" then return false end
    n = n + 1
  end
  for i = 1, n do if t[i] == nil then return false end end
  return true
end

function json.encode(v)
  local t = type(v)
  if t == "nil" then return "null" end
  if t == "boolean" then return tostring(v) end
  if t == "number" then
    if v == math.floor(v) and math.abs(v) < 2^53 then return string.format("%d", v) end
    return string.format("%.17g", v)
  end
  if t == "string" then return '"' .. esc(v) .. '"' end
  if t == "table" then
    local parts = {}
    if next(v) ~= nil and is_array(v) then
      for i = 1, #v do parts[#parts + 1] = json.encode(v[i]) end
      return "[" .. table.concat(parts, ",") .. "]"
    end
    local keys = {}
    for k in pairs(v) do keys[#keys + 1] = k end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    for _, k in ipairs(keys) do
      parts[#parts + 1] = '"' .. esc(tostring(k)) .. '":' .. json.encode(v[k])
    end
    return "{" .. table.concat(parts, ",") .. "}"
  end
  error("cannot encode " .. t)
end

return json
