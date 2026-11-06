-- Minimal World of Warcraft API stubs so the addon can be loaded and driven
-- by LuaJIT (Lua 5.1, like WoW). Frames are permissive mocks: unknown
-- methods are no-ops, so tests exercise addon logic, not Blizzard's UI.
local stub = { messages = {}, timers = {}, reloads = 0, sounds = {}, now = 1800000000 }

local Obj = {}
local objMeta = {
  __index = function(t, k)
    local m = Obj[k]
    if m then return m end
    -- unknown methods are no-ops; unknown lowercase fields are nil
    if type(k) == "string" and k:match("^[A-Z]") then return function() end end
    return nil
  end,
}

local function new(kind, parent)
  return setmetatable({
    kind = kind, parent = parent, scripts = {}, shown = true, w = 400, h = 300,
    text = "", checked = false, enabled = true, keyboard = false, propagate = true,
  }, objMeta)
end
stub.new = new

function Obj:CreateFontString() return new("FontString", self) end
function Obj:CreateTexture() return new("Texture", self) end
function Obj:SetScript(name, fn) self.scripts[name] = fn end
function Obj:GetScript(name) return self.scripts[name] end
function Obj:HookScript(name, fn)
  local old = self.scripts[name]
  self.scripts[name] = function(...)
    if old then old(...) end
    fn(...)
  end
end
function Obj:Fire(name, ...)
  local fn = self.scripts[name]
  if fn then return fn(self, ...) end
end
function Obj:Show()
  local was = self:IsVisible()
  self.shown = true
  if not was and self:IsVisible() then self:Fire("OnShow") end
end
function Obj:Hide()
  local was = self:IsVisible()
  self.shown = false
  if was then self:Fire("OnHide") end
end
function Obj:IsShown() return self.shown end
function Obj:IsVisible()
  if not self.shown then return false end
  local parent = rawget(self, "parent")
  if parent then return parent:IsVisible() end
  return true
end
function Obj:SetShown(v) if v then self:Show() else self:Hide() end end
function Obj:GetWidth() return self.w end
function Obj:GetHeight() return self.h end
function Obj:SetWidth(w) self.w = w end
function Obj:SetHeight(h) self.h = h end
function Obj:SetSize(w, h) self.w, self.h = w, h end
function Obj:GetSize() return self.w, self.h end
function Obj:SetText(t) self.text = t or "" end
function Obj:GetText() return self.text end
function Obj:GetStringHeight() return 20 end
function Obj:SetChecked(v) self.checked = v and true or false end
function Obj:GetChecked() return self.checked end
function Obj:Enable() self.enabled = true end
function Obj:Disable() self.enabled = false end
function Obj:SetEnabled(v) self.enabled = v and true or false end
function Obj:IsEnabled() return self.enabled end
function Obj:GetPoint() return "CENTER", nil, "CENTER", 10, 20 end
function Obj:GetCenter() return 0, 0 end
function Obj:GetEffectiveScale() return 1 end
function Obj:SetFont() return true end
function Obj:EnableKeyboard(v) self.keyboard = v end
function Obj:SetPropagateKeyboardInput(v) self.propagate = v end
function Obj:SetTexture(path) self.texture = path end
function Obj:SetTexCoord(...) self.texcoord = { ... } end
function Obj:Click(button)
  if self.enabled then self:Fire("OnClick", button or "LeftButton") end
end
function Obj:SetFocus() stub.focus = self end
function Obj:ClearFocus() if stub.focus == self then stub.focus = nil end end

local G = _G
G.CreateFrame = function(kind, name, parent)
  local f = new(kind, parent)
  if kind == "Frame" and parent == G.UIParent then f.shown = true end
  if name then G[name] = f end
  return f
end
G.CreateFont = function(name)
  local f = new("Font")
  if name then G[name] = f end
  return f
end
G.UIParent = new("Frame")
G.Minimap = new("Frame")
G.GameTooltip = new("GameTooltip")
G.DEFAULT_CHAT_FRAME = { AddMessage = function(_, msg) table.insert(stub.messages, msg) end }
G.UISpecialFrames = {}
G.STANDARD_TEXT_FONT = "Fonts\\FRIZQT__.TTF"
for _, n in ipairs({ "GameFontNormal", "GameFontNormalLarge", "GameFontHighlight", "GameFontHighlightSmall",
  "GameFontNormalSmall", "GameFontDisableSmall", "ChatFontNormal" }) do
  G[n] = new("Font")
end
G.time = function() return stub.now end
G.GetTime = function() return stub.now - 1700000000 + 0.5 end
G.date = os.date
G.C_Timer = { After = function(_, fn) table.insert(stub.timers, fn) end }
G.ReloadUI = function() stub.reloads = stub.reloads + 1 end
G.InCombatLockdown = function() return stub.inCombat or false end
G.UnitOnTaxi = function() return stub.onTaxi or false end
G.UnitIsDeadOrGhost = function() return stub.dead or false end
G.IsResting = function() return stub.resting or false end
G.IsModifierKeyDown = function() return false end
G.PlaySoundFile = function(path) table.insert(stub.sounds, path); return true, #stub.sounds end
G.StopSound = function() end
G.GetCursorPosition = function() return 10, 10 end
G.HideUIPanel = function() end
G.Settings = {
  RegisterCanvasLayoutCategory = function() return {} end,
  RegisterAddOnCategory = function() end,
}
G.SlashCmdList = {}
G.strtrim = function(s) return (s:gsub("^%s+", ""):gsub("%s+$", "")) end
G.strlower = string.lower
G.tinsert = table.insert
G.unpack = G.unpack or table.unpack

function stub.runTimers()
  local t = stub.timers
  stub.timers = {}
  for _, fn in ipairs(t) do fn() end
end

-- Load the addon files listed in the .toc, like the client does.
function stub.loadAddon(dir, name)
  local ns = {}
  local toc = assert(io.open(dir .. "/" .. name .. ".toc"))
  for line in toc:lines() do
    line = line:gsub("\r", "")
    if line ~= "" and not line:match("^#") then
      local path = dir .. "/" .. line:gsub("\\", "/")
      local chunk = assert(loadfile(path))
      chunk(name, ns)
    end
  end
  toc:close()
  return ns
end

function stub.fire(ns, event, ...)
  ns.events:Fire("OnEvent", event, ...)
end

-- Serialize like WoW writes SavedVariables.
local function ser(v, indent, out)
  local t = type(v)
  if t == "string" then
    out[#out + 1] = string.format("%q", v)
  elseif t == "number" or t == "boolean" then
    out[#out + 1] = tostring(v)
  elseif t == "table" then
    out[#out + 1] = "{\n"
    local n = #v
    for i = 1, n do
      ser(v[i], indent, out)
      out[#out + 1] = ", -- [" .. i .. "]\n"
    end
    local keys = {}
    for k in pairs(v) do
      if not (type(k) == "number" and k >= 1 and k <= n and k % 1 == 0) then keys[#keys + 1] = k end
    end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    for _, k in ipairs(keys) do
      if type(k) == "string" then
        out[#out + 1] = string.format("[%q] = ", k)
      else
        out[#out + 1] = "[" .. tostring(k) .. "] = "
      end
      ser(v[k], indent, out)
      out[#out + 1] = ",\n"
    end
    out[#out + 1] = "}"
  else
    out[#out + 1] = "nil"
  end
end

function stub.savedVariables(name, value)
  local out = { "\n", name, " = " }
  ser(value, 0, out)
  out[#out + 1] = "\n"
  return table.concat(out)
end

return stub
