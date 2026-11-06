-- Main window: frame, navigation between views, combat/auto-open behaviour
-- and keyboard shortcuts.
local _, ns = ...
local W = ns.W

local UI = {}
ns.UI = UI

local NAV = {
  { key = "review", label = "Study" },
  { key = "decks", label = "Decks" },
  { key = "add", label = "Add" },
  { key = "options", label = "Options" },
}

function UI:Init()
  if self.frame then return end
  W.UpdateFonts()
  local db = ns.db

  local f = CreateFrame("Frame", "AnkiCraftFrame", UIParent, "BackdropTemplate")
  self.frame = f
  f:SetSize(db.size and db.size.w or 500, db.size and db.size.h or 460)
  f:SetBackdrop(W.BACKDROP)
  f:SetBackdropColor(0.05, 0.05, 0.08, 0.95)
  f:SetFrameStrata("HIGH")
  f:SetToplevel(true)
  f:SetClampedToScreen(true)
  f:SetMovable(true)
  f:SetResizable(true)
  if f.SetResizeBounds then
    f:SetResizeBounds(380, 340, 1200, 1000)
  elseif f.SetMinResize then
    f:SetMinResize(380, 340)
  end
  f:EnableMouse(true)
  f:RegisterForDrag("LeftButton")
  f:SetScript("OnDragStart", f.StartMoving)
  f:SetScript("OnDragStop", function(self)
    self:StopMovingOrSizing()
    UI:SavePosition()
  end)
  f:SetScale(db.settings.scale or 1)
  f:Hide()
  tinsert(UISpecialFrames, "AnkiCraftFrame")

  local title = W.Text(f, GameFontNormalLarge)
  title:SetPoint("TOPLEFT", 14, -12)
  title:SetText("|cff4fa3ffAnki|rCraft")

  local close = CreateFrame("Button", nil, f, "UIPanelCloseButton")
  close:SetPoint("TOPRIGHT", -2, -2)

  -- navigation
  self.nav = {}
  local prev
  for i = #NAV, 1, -1 do
    local item = NAV[i]
    local b = W.Button(f, item.label, 68, 22, function() UI:ShowView(item.key) end)
    if prev then
      b:SetPoint("RIGHT", prev, "LEFT", -2, 0)
    else
      b:SetPoint("TOPRIGHT", -34, -10)
    end
    self.nav[item.key] = b
    prev = b
  end

  -- resize grip
  local grip = CreateFrame("Button", nil, f)
  grip:SetSize(16, 16)
  grip:SetPoint("BOTTOMRIGHT", -4, 4)
  grip:SetNormalTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Up")
  grip:SetHighlightTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Highlight")
  grip:SetPushedTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Down")
  grip:SetScript("OnMouseDown", function() f:StartSizing("BOTTOMRIGHT") end)
  grip:SetScript("OnMouseUp", function()
    f:StopMovingOrSizing()
    db.size = { w = math.floor(f:GetWidth()), h = math.floor(f:GetHeight()) }
    UI:SavePosition()
  end)

  -- content area
  local content = CreateFrame("Frame", nil, f)
  content:SetPoint("TOPLEFT", 10, -40)
  content:SetPoint("BOTTOMRIGHT", -10, 10)
  self.content = content

  self.views = {
    review = self:CreateReviewView(content),
    decks = self:CreateDecksView(content),
    add = self:CreateAddView(content),
    options = self:CreateOptionsView(content),
  }
  for _, v in pairs(self.views) do
    v:SetAllPoints(content)
    v:Hide()
  end

  f:SetScript("OnShow", function() UI:UpdateKeyboard() end)
  f:SetScript("OnHide", function()
    ns.Media:Stop()
    UI:UpdateKeyboard()
    if UI.cardMenu then UI.cardMenu:Hide() end
  end)
  f:SetScript("OnSizeChanged", function()
    if UI.current and UI.views[UI.current].Refresh then
      UI.views[UI.current]:Refresh()
    end
  end)
  f:SetScript("OnKeyDown", function(self, key) UI:OnKeyDown(self, key) end)
  if f.SetPropagateKeyboardInput then f:SetPropagateKeyboardInput(true) end

  self:RestorePosition()
  self:RegisterSettingsPanel()
  self:CreateMinimapButton()
end

function UI:SavePosition()
  local point, _, relPoint, x, y = self.frame:GetPoint(1)
  ns.db.pos = { point = point, relPoint = relPoint, x = x, y = y }
end

function UI:RestorePosition()
  local f, pos = self.frame, ns.db.pos
  f:ClearAllPoints()
  if pos and pos.point then
    f:SetPoint(pos.point, UIParent, pos.relPoint or pos.point, pos.x or 0, pos.y or 0)
  else
    f:SetPoint("CENTER", UIParent, "CENTER", 260, 60)
  end
end

function UI:ResetPosition()
  self:Init()
  ns.db.pos, ns.db.size = nil, nil
  self.frame:SetSize(500, 460)
  self:RestorePosition()
  ns.Print("Window position reset.")
end

function UI:ShowView(key)
  self:Init()
  self.current = key
  for k, v in pairs(self.views) do
    if k == key then v:Show() else v:Hide() end
  end
  for k, b in pairs(self.nav) do
    if k == key then b:Disable() else b:Enable() end
  end
  if self.views[key].Refresh then self.views[key]:Refresh() end
  self:UpdateKeyboard()
end

function UI:Open(view)
  self:Init()
  self.autoReason = nil
  self.frame:Show()
  self:ShowView(view or self.current or "review")
end

function UI:Toggle()
  self:Init()
  if self.frame:IsShown() then
    self.frame:Hide()
  else
    self:Open(self.current == "review" and "review" or nil)
  end
end

function UI:IsOpen() return self.frame and self.frame:IsShown() end

------------------------------------------------------------ auto open/close
function UI:AutoOpen(reason)
  self:Init()
  if self.frame:IsShown() or InCombatLockdown() then return end
  if ns.Queue:TotalDue() == 0 then return end
  self.frame:Show()
  self:ShowView("review")
  self.autoReason = reason
end

function UI:AutoClose(reason)
  if self.autoReason ~= reason then return end
  self.autoReason = nil
  if ns.db.settings.autoClose and self.frame and self.frame:IsShown() then
    self.frame:Hide()
  end
end

function UI:OnCombat(inCombat)
  if not self.frame then return end
  local s = ns.db.settings
  if inCombat then
    if self.frame:IsShown() and s.hideInCombat then
      self.hiddenForCombat = true
      self.frame:Hide()
    end
    pcall(self.frame.EnableKeyboard, self.frame, false)
  else
    if self.hiddenForCombat and s.reopenAfterCombat then
      self.frame:Show()
      self:ShowView(self.current or "review")
    end
    self.hiddenForCombat = false
    self:UpdateKeyboard()
  end
end

------------------------------------------------------------ keyboard
function UI:UpdateKeyboard()
  local f = self.frame
  if not f or InCombatLockdown() then return end
  local want = f:IsShown() and self.current == "review" and ns.db.settings.captureKeys
  f:EnableKeyboard(want and true or false)
end

local KEY_EASE = {
  ["1"] = 1, ["2"] = 2, ["3"] = 3, ["4"] = 4,
  NUMPAD1 = 1, NUMPAD2 = 2, NUMPAD3 = 3, NUMPAD4 = 4,
}

function UI:OnKeyDown(frame, key)
  if InCombatLockdown() then return end
  local handled = false
  if self.current == "review" and not IsModifierKeyDown() then
    if key == "SPACE" or key == "ENTER" then
      handled = self:Review_SpaceOrEnter()
    elseif KEY_EASE[key] then
      handled = self:Review_Answer(KEY_EASE[key])
    end
  end
  if frame.SetPropagateKeyboardInput then
    frame:SetPropagateKeyboardInput(not handled)
    if handled then
      C_Timer.After(0, function()
        if not InCombatLockdown() then frame:SetPropagateKeyboardInput(true) end
      end)
    end
  end
end

------------------------------------------------------------ settings panel
function UI:RegisterSettingsPanel()
  local panel = CreateFrame("Frame")
  panel.name = "AnkiCraft"
  local title = W.Text(panel, GameFontNormalLarge)
  title:SetPoint("TOPLEFT", 16, -16)
  title:SetText("AnkiCraft " .. ns.version)
  local text = W.Text(panel, GameFontHighlight)
  text:SetPoint("TOPLEFT", title, "BOTTOMLEFT", 0, -8)
  text:SetWidth(520)
  text:SetText("Review your Anki flashcards in WoW. All settings live in the AnkiCraft window.\nType /anki or click the minimap button.")
  local b = W.Button(panel, "Open AnkiCraft options", 200, 24, function()
    if SettingsPanel and SettingsPanel:IsShown() then HideUIPanel(SettingsPanel) end
    if InterfaceOptionsFrame and InterfaceOptionsFrame:IsShown() then HideUIPanel(InterfaceOptionsFrame) end
    UI:Open("options")
  end)
  b:SetPoint("TOPLEFT", text, "BOTTOMLEFT", 0, -12)
  if Settings and Settings.RegisterCanvasLayoutCategory then
    local category = Settings.RegisterCanvasLayoutCategory(panel, "AnkiCraft")
    Settings.RegisterAddOnCategory(category)
  elseif InterfaceOptions_AddCategory then
    InterfaceOptions_AddCategory(panel)
  end
end
