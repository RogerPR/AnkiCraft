-- Add view: create new notes in-game; they are added to Anki on sync.
local _, ns = ...
local W, UI = ns.W, ns.UI
local Q = ns.Queue

local MAX_FIELDS = 6

function UI:CreateAddView(parent)
  local v = CreateFrame("Frame", nil, parent)

  local deckLabel = W.Text(v, GameFontNormal)
  deckLabel:SetPoint("TOPLEFT", 4, -8)
  deckLabel:SetText("Deck")
  v.deckSel = W.Selector(v, 300)
  v.deckSel:SetPoint("TOPLEFT", 80, -4)

  local typeLabel = W.Text(v, GameFontNormal)
  typeLabel:SetPoint("TOPLEFT", 4, -38)
  typeLabel:SetText("Type")
  v.typeSel = W.Selector(v, 300, function() UI:Add_UpdateFields(v) end)
  v.typeSel:SetPoint("TOPLEFT", 80, -34)

  v.fieldLabels, v.fields = {}, {}
  for i = 1, MAX_FIELDS do
    local label = W.Text(v, GameFontNormal)
    label:SetPoint("TOPLEFT", 4, -72 - (i - 1) * 32)
    label:SetWidth(72)
    label:SetWordWrap(false)
    local eb = W.Input(v, 300)
    eb:SetPoint("TOPLEFT", 86, -66 - (i - 1) * 32)
    eb:SetPoint("RIGHT", v, "RIGHT", -10, 0)
    eb:SetScript("OnTabPressed", function()
      local nextBox = v.fields[i + 1]
      if nextBox and nextBox:IsShown() then nextBox:SetFocus() else v.tags:SetFocus() end
    end)
    eb:SetScript("OnEnterPressed", function(self)
      local nextBox = v.fields[i + 1]
      if nextBox and nextBox:IsShown() then nextBox:SetFocus() else self:ClearFocus() end
    end)
    v.fieldLabels[i], v.fields[i] = label, eb
  end

  v.tagsLabel = W.Text(v, GameFontNormal)
  v.tagsLabel:SetText("Tags")
  v.tags = W.Input(v, 300)
  v.tags:SetScript("OnEnterPressed", function(self) self:ClearFocus() end)
  v.tags:SetScript("OnTabPressed", function() v.fields[1]:SetFocus() end)

  v.addBtn = W.Button(v, "Add note", 120, 26, function() UI:Add_Submit(v) end)
  v.addBtn:SetPoint("BOTTOMRIGHT", -14, 4)
  v.status = W.Text(v, GameFontHighlightSmall)
  v.status:SetPoint("BOTTOMLEFT", 4, 10)
  v.status:SetPoint("RIGHT", v.addBtn, "LEFT", -8, 0)

  v.Refresh = function() UI:Add_Refresh(v) end
  return v
end

function UI:Add_Refresh(v)
  if ns.DataState() ~= "ok" then
    v.status:SetText("Connect Anki first (see the Study tab).")
    v.addBtn:Disable()
    return
  end
  v.addBtn:Enable()
  if not v.loaded then
    v.loaded = true
    local decks, deckIndex = {}, 1
    local current = Q:FindDeck(Q.deckId)
    for i, d in ipairs(Q:AddDecks()) do
      decks[#decks + 1] = { label = d.name, id = d.id }
      if current and d.name == current.name then deckIndex = i end
    end
    v.deckSel:SetItems(decks, deckIndex)
    local types, typeIndex = {}, 1
    for i, nt in ipairs(Q:NoteTypes()) do
      types[#types + 1] = { label = nt.name, fields = nt.fields }
      if nt.name == "Basic" then typeIndex = i end
    end
    v.typeSel:SetItems(types, typeIndex)
  end
  self:Add_UpdateFields(v)
end

function UI:Add_UpdateFields(v)
  local nt = v.typeSel:Selected()
  local names = nt and nt.fields or {}
  local shown = math.min(#names, MAX_FIELDS)
  for i = 1, MAX_FIELDS do
    if i <= shown then
      v.fieldLabels[i]:SetText(names[i])
      v.fieldLabels[i]:Show()
      v.fields[i]:Show()
    else
      v.fieldLabels[i]:Hide()
      v.fields[i]:Hide()
    end
  end
  local y = -72 - shown * 32
  v.tagsLabel:ClearAllPoints()
  v.tagsLabel:SetPoint("TOPLEFT", 4, y)
  v.tags:ClearAllPoints()
  v.tags:SetPoint("TOPLEFT", 86, y + 6)
  v.tags:SetPoint("RIGHT", v, "RIGHT", -10, 0)
  if #names > MAX_FIELDS then
    v.status:SetText(string.format("Only the first %d fields can be filled in WoW.", MAX_FIELDS))
  end
end

function UI:Add_Submit(v)
  local deck, nt = v.deckSel:Selected(), v.typeSel:Selected()
  if not deck or not nt then return end
  local fields = {}
  for i = 1, math.min(#nt.fields, MAX_FIELDS) do
    fields[i] = v.fields[i]:GetText() or ""
  end
  if strtrim(fields[1] or "") == "" then
    v.status:SetText("|cffff6060The first field can't be empty.|r")
    return
  end
  Q:AddNote(deck.id, nt.label, fields, strtrim(v.tags:GetText() or ""))
  for i = 1, MAX_FIELDS do v.fields[i]:SetText("") end
  v.fields[1]:SetFocus()
  v.status:SetText(string.format("|cff60d060Added to %s.|r It will appear in Anki after you sync (%d waiting).", deck.label, Q:PendingCount()))
end
