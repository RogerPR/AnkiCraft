-- Minimap button (no libraries). Left-click: open/close. Right-click: decks.
-- Drag to move around the minimap.
local _, ns = ...
local UI = ns.UI

local RADIUS = 80

local function updatePosition(button)
  local angle = math.rad(ns.db.settings.minimapAngle or 215)
  button:ClearAllPoints()
  button:SetPoint("CENTER", Minimap, "CENTER", math.cos(angle) * RADIUS, math.sin(angle) * RADIUS)
end

function UI:CreateMinimapButton()
  if self.minimapButton then return end
  local b = CreateFrame("Button", "AnkiCraftMinimapButton", Minimap)
  self.minimapButton = b
  b:SetSize(31, 31)
  b:SetFrameStrata("MEDIUM")
  b:SetFrameLevel(8)
  b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  b:RegisterForDrag("LeftButton")
  b:SetHighlightTexture("Interface\\Minimap\\UI-Minimap-ZoomButton-Highlight")

  local overlay = b:CreateTexture(nil, "OVERLAY")
  overlay:SetSize(53, 53)
  overlay:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
  overlay:SetPoint("TOPLEFT")
  local bg = b:CreateTexture(nil, "BACKGROUND")
  bg:SetSize(20, 20)
  bg:SetTexture("Interface\\Minimap\\UI-Minimap-Background")
  bg:SetPoint("TOPLEFT", 7, -5)
  local icon = b:CreateTexture(nil, "ARTWORK")
  icon:SetSize(17, 17)
  icon:SetTexture("Interface\\Icons\\INV_Misc_Book_09")
  icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
  icon:SetPoint("TOPLEFT", 7, -6)

  b:SetScript("OnClick", function(_, button)
    if button == "RightButton" then
      UI:Open("decks")
    else
      UI:Toggle()
    end
  end)
  b:SetScript("OnDragStart", function(self)
    self:SetScript("OnUpdate", function()
      local mx, my = Minimap:GetCenter()
      local scale = Minimap:GetEffectiveScale()
      local cx, cy = GetCursorPosition()
      cx, cy = cx / scale, cy / scale
      ns.db.settings.minimapAngle = math.deg(math.atan2(cy - my, cx - mx)) % 360
      updatePosition(self)
    end)
  end)
  b:SetScript("OnDragStop", function(self) self:SetScript("OnUpdate", nil) end)
  b:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_LEFT")
    GameTooltip:SetText("|cff4fa3ffAnki|rCraft")
    if ns.DataState() == "ok" then
      GameTooltip:AddLine(string.format("%d cards to review", ns.Queue:TotalDue()), 1, 1, 1)
      local pending = ns.Queue:PendingCount()
      if pending > 0 then
        GameTooltip:AddLine(string.format("%d changes waiting for Anki", pending), 1, 0.82, 0)
      end
    else
      GameTooltip:AddLine("Not connected to Anki yet", 1, 0.4, 0.4)
    end
    GameTooltip:AddLine("Left-click: study   Right-click: decks", 0.6, 0.6, 0.6)
    GameTooltip:Show()
  end)
  b:SetScript("OnLeave", function() GameTooltip:Hide() end)

  updatePosition(b)
  self:UpdateMinimapButton()
end

function UI:UpdateMinimapButton()
  if not self.minimapButton then return end
  if ns.db.settings.minimap then
    self.minimapButton:Show()
  else
    self.minimapButton:Hide()
  end
end
