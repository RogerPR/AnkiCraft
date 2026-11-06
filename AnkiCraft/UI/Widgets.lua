-- Small widget helpers shared by the UI files.
local _, ns = ...

local W = {}
ns.W = W

W.BACKDROP = {
  bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background-Dark",
  edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
  tile = true, tileSize = 16, edgeSize = 16,
  insets = { left = 4, right = 4, top = 4, bottom = 4 },
}

W.FLAGS = {
  { name = "Red", color = { 1.0, 0.31, 0.31 } },
  { name = "Orange", color = { 1.0, 0.63, 0.25 } },
  { name = "Green", color = { 0.25, 0.75, 0.25 } },
  { name = "Blue", color = { 0.31, 0.64, 1.0 } },
  { name = "Pink", color = { 1.0, 0.5, 0.75 } },
  { name = "Turquoise", color = { 0.25, 0.88, 0.82 } },
  { name = "Purple", color = { 0.69, 0.5, 1.0 } },
}

-- Font objects using the bundled Japanese-capable font. Falls back to the
-- game font if the file can't be loaded.
local function setFont(fontObject, size, flags)
  local ok = fontObject:SetFont(ns.FONT, size, flags or "")
  if ok == false then
    fontObject:SetFont(STANDARD_TEXT_FONT, size, flags or "")
  end
end

function W.UpdateFonts()
  local size = ns.db and ns.db.settings.fontSize or 18
  W.cardFont = W.cardFont or CreateFont("AnkiCraftCardFont")
  setFont(W.cardFont, size)
  W.cardFont:SetTextColor(1, 1, 1)
  W.smallFont = W.smallFont or CreateFont("AnkiCraftSmallFont")
  setFont(W.smallFont, 13)
  W.smallFont:SetTextColor(1, 1, 1)
  W.inputFont = W.inputFont or CreateFont("AnkiCraftInputFont")
  setFont(W.inputFont, 14)
  W.inputFont:SetTextColor(1, 1, 1)
end

function W.Button(parent, text, width, height, onClick)
  local b = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
  b:SetSize(width or 80, height or 22)
  b:SetText(text)
  if onClick then b:SetScript("OnClick", onClick) end
  return b
end

function W.Text(parent, fontObject, justify, layer)
  local fs = parent:CreateFontString(nil, layer or "OVERLAY")
  if type(fontObject) == "string" then
    fs:SetFontObject(fontObject)
  else
    fs:SetFontObject(fontObject or GameFontHighlight)
  end
  fs:SetJustifyH(justify or "LEFT")
  return fs
end

function W.Tooltip(frame, title, body)
  frame:HookScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    GameTooltip:SetText(title, 1, 1, 1)
    if body then GameTooltip:AddLine(body, nil, nil, nil, true) end
    GameTooltip:Show()
  end)
  frame:HookScript("OnLeave", function() GameTooltip:Hide() end)
end

-- Checkbox with a label; get() returns current value, set(v) stores it.
function W.Check(parent, label, get, set, tooltip)
  local cb = CreateFrame("CheckButton", nil, parent, "UICheckButtonTemplate")
  cb:SetSize(24, 24)
  local text = W.Text(cb, GameFontHighlight)
  text:SetPoint("LEFT", cb, "RIGHT", 2, 0)
  text:SetText(label)
  cb.label = text
  cb:SetScript("OnClick", function(self) set(self:GetChecked() and true or false) end)
  cb.Refresh = function(self) self:SetChecked(get() and true or false) end
  if tooltip then W.Tooltip(cb, label, tooltip) end
  cb:Refresh()
  return cb
end

-- "- value +" control.
function W.Stepper(parent, label, get, set, minV, maxV, step, fmt)
  local f = CreateFrame("Frame", nil, parent)
  f:SetSize(400, 24)
  local minus = W.Button(f, "-", 24, 22)
  minus:SetPoint("LEFT", 200, 0)
  local text = W.Text(f, GameFontHighlight)
  text:SetPoint("LEFT", 4, 0)
  text:SetPoint("RIGHT", minus, "LEFT", -4, 0)
  text:SetWordWrap(false)
  text:SetText(label)
  local value = W.Text(f, GameFontNormal, "CENTER")
  value:SetPoint("LEFT", minus, "RIGHT", 2, 0)
  value:SetWidth(70)
  local plus = W.Button(f, "+", 24, 22)
  plus:SetPoint("LEFT", value, "RIGHT", 2, 0)
  local function refresh()
    value:SetText(string.format(fmt or "%d", get()))
  end
  local function change(delta)
    local v = get() + delta
    v = math.max(minV, math.min(maxV, v))
    v = math.floor(v / step + 0.5) * step
    set(v)
    refresh()
  end
  minus:SetScript("OnClick", function() change(-step) end)
  plus:SetScript("OnClick", function() change(step) end)
  f.Refresh = refresh
  refresh()
  return f
end

function W.Input(parent, width)
  local eb = CreateFrame("EditBox", nil, parent, "InputBoxTemplate")
  eb:SetSize(width or 200, 24)
  eb:SetAutoFocus(false)
  eb:SetMaxLetters(4000)
  eb:SetFontObject(W.inputFont or ChatFontNormal)
  eb:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
  return eb
end

-- "< label >" selector cycling through a list.
function W.Selector(parent, width, onChange)
  local f = CreateFrame("Frame", nil, parent)
  f:SetSize(width, 24)
  local prev = W.Button(f, "<", 24, 22)
  prev:SetPoint("LEFT")
  local nextB = W.Button(f, ">", 24, 22)
  nextB:SetPoint("RIGHT")
  local text = W.Text(f, W.smallFont or GameFontHighlight, "CENTER")
  text:SetPoint("LEFT", prev, "RIGHT", 4, 0)
  text:SetPoint("RIGHT", nextB, "LEFT", -4, 0)
  text:SetWordWrap(false)
  f.items, f.index = {}, 1
  function f:SetItems(items, index)
    self.items = items or {}
    self.index = math.max(1, math.min(index or 1, #self.items))
    self:Update()
  end
  function f:Update()
    local item = self.items[self.index]
    text:SetText(item and item.label or "-")
  end
  function f:Selected() return self.items[self.index] end
  local function step(d)
    if #f.items == 0 then return end
    f.index = (f.index - 1 + d) % #f.items + 1
    f:Update()
    if onChange then onChange(f:Selected()) end
  end
  prev:SetScript("OnClick", function() step(-1) end)
  nextB:SetScript("OnClick", function() step(1) end)
  return f
end

-- A scroll frame with a content child that follows its width.
function W.Scroll(parent)
  local scroll = CreateFrame("ScrollFrame", nil, parent, "UIPanelScrollFrameTemplate")
  local child = CreateFrame("Frame", nil, scroll)
  child:SetSize(100, 100)
  scroll:SetScrollChild(child)
  scroll:SetScript("OnSizeChanged", function(self, w)
    child:SetWidth(math.max(1, w))
  end)
  scroll.child = child
  return scroll
end
