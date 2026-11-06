-- Review view: shows the current card, reveals the answer, and records
-- Again / Hard / Good / Easy.
local _, ns = ...
local W, UI = ns.W, ns.UI
local Q = ns.Queue

local EASE = {
  { label = "Again", color = "ff6060" },
  { label = "Hard", color = "ffb040" },
  { label = "Good", color = "60d060" },
  { label = "Easy", color = "60b0ff" },
}
local MAX_IMAGES = 4
local BUTTONS_H = 78 -- space reserved at the bottom for answer + footer rows

local view -- the review frame

local function makeImages(parent)
  local list = {}
  for i = 1, MAX_IMAGES do
    local t = parent:CreateTexture(nil, "ARTWORK")
    t:Hide()
    list[i] = t
  end
  return list
end

function UI:CreateReviewView(parent)
  local v = CreateFrame("Frame", nil, parent)
  view = v
  v.revealed = false

  -- header: deck name, counts, flag/mark
  v.deckText = W.Text(v, W.smallFont)
  v.deckText:SetPoint("TOPLEFT", 4, -2)
  v.deckText:SetPoint("RIGHT", v, "RIGHT", -150, 0)
  v.deckText:SetWordWrap(false)
  v.deckText:SetTextColor(1, 0.82, 0)
  v.counts = W.Text(v, W.smallFont, "RIGHT")
  v.counts:SetPoint("TOPRIGHT", -4, -2)
  v.flagTex = v:CreateTexture(nil, "OVERLAY")
  v.flagTex:SetSize(10, 10)
  v.flagTex:SetPoint("TOPLEFT", 4, -22)
  v.flagTex:Hide()
  v.markText = W.Text(v, GameFontNormalSmall)
  v.markText:SetPoint("TOPRIGHT", -4, -20)

  -- card area
  local scroll = W.Scroll(v)
  scroll:SetPoint("TOPLEFT", 0, -36)
  scroll:SetPoint("BOTTOMRIGHT", -24, BUTTONS_H)
  v.scroll = scroll
  local c = scroll.child
  v.qText = W.Text(c, W.cardFont, "CENTER")
  v.qImages = makeImages(c)
  v.qAudio = W.Button(c, "Play audio", 110, 20, function() ns.Media:Play(v.entry and v.entry.card.qSnd) end)
  v.sep = c:CreateTexture(nil, "ARTWORK")
  v.sep:SetColorTexture(1, 1, 1, 0.25)
  v.sep:SetHeight(1)
  v.aText = W.Text(c, W.cardFont, "CENTER")
  v.aImages = makeImages(c)
  v.aAudio = W.Button(c, "Play audio", 110, 20, function() ns.Media:Play(v.entry and v.entry.card.aSnd) end)
  v.note = W.Text(c, GameFontDisableSmall, "CENTER")

  -- empty / setup message
  v.message = W.Text(v, GameFontHighlight, "CENTER")
  v.message:SetPoint("TOPLEFT", 20, -60)
  v.message:SetPoint("TOPRIGHT", -20, -60)
  v.message:SetSpacing(4)

  -- show answer
  v.showBtn = W.Button(v, "Show Answer", 220, 30, function() UI:Review_ShowAnswer() end)
  v.showBtn:SetPoint("BOTTOM", 0, 32)

  -- ease buttons
  v.easeButtons = {}
  for i, e in ipairs(EASE) do
    local b = W.Button(v, "|cff" .. e.color .. e.label .. "|r", 100, 30, function() UI:Review_Answer(i) end)
    b.ivl = W.Text(b, GameFontHighlightSmall, "CENTER")
    b.ivl:SetPoint("BOTTOM", b, "TOP", 0, 2)
    W.Tooltip(b, e.label, "Key: " .. i)
    v.easeButtons[i] = b
  end

  -- footer
  v.undoBtn = W.Button(v, "Undo", 60, 22, function() UI:Review_Undo() end)
  v.undoBtn:SetPoint("BOTTOMLEFT", 0, 0)
  v.cardBtn = W.Button(v, "Card...", 66, 22, function(self) UI:ToggleCardMenu(self) end)
  v.cardBtn:SetPoint("LEFT", v.undoBtn, "RIGHT", 4, 0)
  v.syncBtn = W.Button(v, "Sync", 70, 22, function() ns.Sync() end)
  v.syncBtn:SetPoint("BOTTOMRIGHT", -14, 0)
  W.Tooltip(v.syncBtn, "Sync with Anki",
    "Saves your reviews and reloads the UI. Anki (with AnkiCraft Bridge) must be open. If new cards don't show up right away, sync again a few seconds later.")
  v.status = W.Text(v, GameFontNormalSmall, "CENTER")
  v.status:SetPoint("LEFT", v.cardBtn, "RIGHT", 6, 0)
  v.status:SetPoint("RIGHT", v.syncBtn, "LEFT", -6, 0)

  v.Refresh = function() UI:Review_Refresh() end
  return v
end

------------------------------------------------------------ layout
local function layoutImages(images, list, y, width, maxH)
  local child = view.scroll.child
  for i = 1, MAX_IMAGES do
    local tex, img = images[i], list and list[i]
    if img then
      ns.Media:ApplyTexture(tex, img)
      local w, h = ns.Media:FitSize(img, width - 16, maxH)
      tex:SetSize(w, h)
      tex:ClearAllPoints()
      tex:SetPoint("TOP", child, "TOP", 0, y)
      tex:Show()
      y = y - h - 6
    else
      tex:Hide()
    end
  end
  return y
end

local function placeText(fs, text, y, width)
  local child = view.scroll.child
  fs:ClearAllPoints()
  fs:SetWidth(width - 16)
  fs:SetText(text or "")
  fs:SetPoint("TOP", child, "TOP", 0, y)
  fs:Show()
  return y - fs:GetStringHeight() - 10
end

local function placeButton(btn, files, y)
  if type(files) == "table" and #files > 0 then
    btn:ClearAllPoints()
    btn:SetPoint("TOP", view.scroll.child, "TOP", 0, y)
    btn:SetText(#files > 1 and string.format("Play audio (%d)", #files) or "Play audio")
    btn:Show()
    return y - 26
  end
  btn:Hide()
  return y
end

function UI:Review_LayoutCard()
  local v, e = view, view.entry
  local card = e.card
  local width = math.max(100, v.scroll:GetWidth())
  local maxImgH = math.max(80, v.scroll:GetHeight() * 0.6)
  local y = -6
  local showQuestion = not (v.revealed and card.aFull)

  if showQuestion then
    y = placeText(v.qText, card.q, y, width)
    y = layoutImages(v.qImages, card.qImg, y, width, maxImgH)
    y = placeButton(v.qAudio, card.qSnd, y)
  else
    v.qText:Hide()
    layoutImages(v.qImages, nil, y, width, maxImgH)
    v.qAudio:Hide()
  end

  if v.revealed then
    if showQuestion then
      v.sep:ClearAllPoints()
      v.sep:SetPoint("TOPLEFT", v.scroll.child, "TOPLEFT", 8, y - 2)
      v.sep:SetPoint("TOPRIGHT", v.scroll.child, "TOPRIGHT", -8, y - 2)
      v.sep:Show()
      y = y - 12
    else
      v.sep:Hide()
    end
    y = placeText(v.aText, card.a, y, width)
    y = layoutImages(v.aImages, card.aImg, y, width, maxImgH)
    y = placeButton(v.aAudio, card.aSnd, y)
  else
    v.sep:Hide()
    v.aText:Hide()
    layoutImages(v.aImages, nil, y, width, maxImgH)
    v.aAudio:Hide()
  end

  local missing = {}
  if card.missingImg then missing[#missing + 1] = card.missingImg .. " image(s)" end
  if card.missingSnd then missing[#missing + 1] = card.missingSnd .. " audio file(s)" end
  if #missing > 0 then
    y = placeText(v.note, "(" .. table.concat(missing, ", ") .. " can't be shown in WoW)", y, width)
  else
    v.note:Hide()
  end
  v.scroll.child:SetHeight(math.max(1, -y + 6))
end

function UI:Review_LayoutButtons()
  local v = view
  local width = v:GetWidth()
  local bw = math.max(60, math.floor((width - 14 - 3 * 6) / 4))
  for i, b in ipairs(v.easeButtons) do
    b:SetWidth(bw)
    b:ClearAllPoints()
    b:SetPoint("BOTTOMLEFT", (i - 1) * (bw + 6), 30)
  end
end

------------------------------------------------------------ state
local function setShown(frame, shown)
  if shown then frame:Show() else frame:Hide() end
end

function UI:Review_Refresh()
  local v = view
  if not v or not v:IsVisible() then return end
  v.qText:SetFontObject(W.cardFont)
  v.aText:SetFontObject(W.cardFont)
  self:Review_LayoutButtons()

  local pending = Q:PendingCount()
  v.syncBtn:SetText(pending > 0 and string.format("Sync (%d)", pending) or "Sync")
  v.undoBtn:SetEnabled(Q:CanUndo())

  local state = ns.DataState()
  if state ~= "ok" then
    self:Review_ShowMessage(state == "format"
      and "Your AnkiCraft Bridge (in Anki) and this addon are different versions.\nPlease update both, then restart WoW."
      or ("|cffffd100Welcome to AnkiCraft!|r\n\nTo get your cards into WoW:\n\n"
        .. "1. In Anki: Tools > Add-ons > Get Add-ons, and install |cff4fa3ffAnkiCraft Bridge|r.\n"
        .. "2. Restart Anki and keep it open.\n"
        .. "3. Exit WoW completely and start it again (a /reload is not enough the first time).\n\n"
        .. "After that, use the Sync button whenever you want to send reviews to Anki."))
    v.deckText:SetText("")
    v.counts:SetText("")
    v.status:SetText("")
    return
  end

  if not Q.deckId then Q:SelectDefaultDeck() end
  local deck = Q:FindDeck(Q.deckId)
  v.deckText:SetText(deck and deck.name or "No decks")
  local n, l, r = Q:Counts()
  v.counts:SetText(string.format("|cff4fa3ff%d|r  |cffff6060%d|r  |cff60d060%d|r", n, l, r))
  local reviewed = Q:ReviewedToday()
  v.status:SetText(reviewed > 0 and string.format("%d reviewed today", reviewed) or "")

  local e = Q:Current()
  if e ~= v.entry then
    v.entry = e
    v.revealed = false
    v.shownAt = GetTime()
    v.scroll:SetVerticalScroll(0)
    ns.Media:Stop()
    if e and ns.db.settings.autoplay and e.card.qSnd then
      ns.Media:Play(e.card.qSnd)
    end
  end

  if not e then
    local lines = { "|cffffd100Congratulations!|r You have finished this deck for now." }
    if deck and deck.truncated then
      lines[1] = "|cffffd100Batch done!|r Anki has more cards due in this deck."
      lines[#lines + 1] = "\nPress |cffffd100Sync|r (Anki must be open) to send your reviews and load the next batch."
    elseif pending > 0 then
      lines[#lines + 1] = string.format("\n%d changes are waiting to be sent to Anki.\nMake sure Anki is open, then press |cffffd100Sync|r.", pending)
    else
      lines[#lines + 1] = "\nPick another deck, or press Sync to fetch newly due cards from Anki."
    end
    local data = ns.data
    lines[#lines + 1] = "\n|cff808080Cards exported from Anki " .. ns.FormatAgo(data.exportedAt) .. ".|r"
    self:Review_ShowMessage(table.concat(lines, "\n"))
    v.cardBtn:Disable()
    return
  end

  v.message:Hide()
  v.scroll:Show()
  v.cardBtn:Enable()

  local flag = Q:Flag(e)
  if flag > 0 and W.FLAGS[flag] then
    v.flagTex:SetColorTexture(unpack(W.FLAGS[flag].color))
    v.flagTex:Show()
  else
    v.flagTex:Hide()
  end
  v.markText:SetText(Q:IsMarked(e) and "|cffffd100Marked|r" or "")

  self:Review_LayoutCard()
  setShown(v.showBtn, not v.revealed)
  local ivl = ns.db.settings.showIntervals and Q:Intervals(e)
  for i, b in ipairs(v.easeButtons) do
    setShown(b, v.revealed)
    b.ivl:SetText(ivl and ivl[i] or "")
  end
end

function UI:Review_ShowMessage(text)
  local v = view
  v.entry = nil
  v.scroll:Hide()
  v.message:SetText(text)
  v.message:Show()
  v.showBtn:Hide()
  for _, b in ipairs(v.easeButtons) do b:Hide() end
  v.flagTex:Hide()
  v.markText:SetText("")
end

------------------------------------------------------------ actions
local function reviewing()
  return view and view:IsVisible() and view.entry ~= nil
end

function UI:Review_ShowAnswer()
  if not reviewing() or view.revealed then return false end
  view.revealed = true
  local card = view.entry.card
  if ns.db.settings.autoplay and card.aSnd then
    ns.Media:Play(card.aSnd)
  end
  self:Review_Refresh()
  return true
end

-- Space/Enter: reveal, then "Good".
function UI:Review_SpaceOrEnter()
  if not reviewing() then return false end
  if not view.revealed then return self:Review_ShowAnswer() end
  return self:Review_Answer(3)
end

function UI:Review_Answer(ease)
  if not reviewing() then return false end
  if not view.revealed then return self:Review_ShowAnswer() end
  local ms = (GetTime() - (view.shownAt or GetTime())) * 1000
  Q:Answer(ease, ms)
  self:Review_Refresh()
  return true
end

function UI:Review_Undo()
  local kind = Q:Undo()
  if not kind then
    ns.Print("Nothing to undo.")
    return
  end
  if kind == "answer" or kind == "suspend" or kind == "bury" then
    view.entry = nil -- the restored card is shown again from its question
  end
  self:Review_Refresh()
end

------------------------------------------------------------ card menu
function UI:ToggleCardMenu(anchor)
  local menu = self.cardMenu
  if not menu then
    menu = CreateFrame("Frame", "AnkiCraftCardMenu", self.frame, "BackdropTemplate")
    self.cardMenu = menu
    menu:SetBackdrop(W.BACKDROP)
    menu:SetBackdropColor(0, 0, 0, 0.95)
    menu:SetFrameStrata("DIALOG")
    menu:EnableMouse(true)
    local items = {
      { "Suspend card", function() Q:Suspend() end },
      { "Bury card (until tomorrow)", function() Q:Bury() end },
      { "Toggle mark", function() Q:ToggleMark() end },
    }
    for i, flag in ipairs(W.FLAGS) do
      local hex = string.format("%02x%02x%02x", flag.color[1] * 255, flag.color[2] * 255, flag.color[3] * 255)
      items[#items + 1] = { "|cff" .. hex .. flag.name .. " flag|r", function() Q:SetFlag(i) end }
    end
    local y = -8
    for _, item in ipairs(items) do
      local b = W.Button(menu, item[1], 200, 20, function()
        item[2]()
        menu:Hide()
        UI:Review_Refresh()
      end)
      b:SetPoint("TOP", 0, y)
      y = y - 22
    end
    menu:SetSize(216, -y + 8)
    menu:Hide() -- new frames start shown
  end
  if menu:IsShown() then
    menu:Hide()
  else
    menu:ClearAllPoints()
    menu:SetPoint("BOTTOMLEFT", anchor, "TOPLEFT", 0, 2)
    menu:Show()
  end
end
