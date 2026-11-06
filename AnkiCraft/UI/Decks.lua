-- Decks view: pick a deck, see sync status.
local _, ns = ...
local W, UI = ns.W, ns.UI
local Q = ns.Queue

local ROW_H = 26

function UI:CreateDecksView(parent)
  local v = CreateFrame("Frame", nil, parent)

  v.info = W.Text(v, GameFontHighlightSmall)
  v.info:SetPoint("TOPLEFT", 4, -2)
  v.info:SetPoint("TOPRIGHT", -4, -2)
  v.info:SetSpacing(2)

  local scroll = W.Scroll(v)
  scroll:SetPoint("TOPLEFT", 0, -66)
  scroll:SetPoint("BOTTOMRIGHT", -24, 30)
  v.scroll = scroll
  v.rows = {}

  v.syncBtn = W.Button(v, "Sync with Anki", 140, 22, function() ns.Sync() end)
  v.syncBtn:SetPoint("BOTTOMRIGHT", -14, 0)
  W.Tooltip(v.syncBtn, "Sync with Anki", "Saves and reloads the UI. Keep Anki open with AnkiCraft Bridge installed.")

  v.empty = W.Text(v, GameFontHighlight, "CENTER")
  v.empty:SetPoint("CENTER")

  v.Refresh = function() UI:Decks_Refresh(v) end
  return v
end

local function getRow(v, i)
  local row = v.rows[i]
  if row then return row end
  row = CreateFrame("Button", nil, v.scroll.child)
  row:SetHeight(ROW_H - 2)
  row:SetHighlightTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight", "ADD")
  row.name = W.Text(row, W.smallFont)
  row.name:SetPoint("LEFT", 6, 0)
  row.name:SetPoint("RIGHT", row, "RIGHT", -110, 0)
  row.name:SetWordWrap(false)
  row.counts = W.Text(row, W.smallFont, "RIGHT")
  row.counts:SetPoint("RIGHT", -6, 0)
  row.bg = row:CreateTexture(nil, "BACKGROUND")
  row.bg:SetAllPoints()
  row:SetScript("OnClick", function(self)
    Q:SelectDeck(self.deckId)
    UI:ShowView("review")
  end)
  v.rows[i] = row
  return row
end

function UI:Decks_Refresh(v)
  local data = ns.data
  local pending = Q:PendingCount()
  v.syncBtn:SetText(pending > 0 and string.format("Sync (%d)", pending) or "Sync with Anki")

  if ns.DataState() ~= "ok" then
    v.info:SetText("")
    v.empty:SetText("No cards from Anki yet.\nOpen the Study tab for setup instructions.")
    v.empty:Show()
    for _, row in ipairs(v.rows) do row:Hide() end
    return
  end

  local lines = {
    string.format("Cards exported from Anki %s.  |cff4fa3ffNew|r  |cffff6060Learn|r  |cff60d060Review|r", ns.FormatAgo(data.exportedAt)),
  }
  local ls = data.lastSync
  if ls and ls.at then
    local s = string.format("Last sync %s: %d reviews, %d new notes", ns.FormatAgo(ls.at), ls.answered or 0, ls.added or 0)
    if (ls.conflicts or 0) > 0 then
      s = s .. string.format(", |cffffb040%d skipped (already reviewed elsewhere)|r", ls.conflicts)
    end
    if (ls.errors or 0) > 0 then
      s = s .. string.format(", |cffff6060%d errors (see Anki)|r", ls.errors)
    end
    lines[#lines + 1] = s .. "."
  end
  if pending > 0 then
    lines[#lines + 1] = string.format("|cffffd100%d changes waiting for Anki.|r", pending)
  end
  v.info:SetText(table.concat(lines, "\n"))

  local decks = Q:Decks()
  v.empty:SetText(#decks == 0 and "No decks were exported. Choose decks in Anki:\nTools > AnkiCraft Bridge." or "")
  if #decks == 0 then v.empty:Show() else v.empty:Hide() end

  local width = math.max(100, v.scroll:GetWidth())
  local anyTruncated = false
  for i, deck in ipairs(decks) do
    local row = getRow(v, i)
    row:SetWidth(width)
    row:ClearAllPoints()
    row:SetPoint("TOPLEFT", 0, -(i - 1) * ROW_H)
    row.deckId = deck.id
    row.name:SetText(deck.name)
    local n, l, r = Q:DeckCounts(deck)
    row.counts:SetText(string.format("|cff4fa3ff%d|r  |cffff6060%d|r  |cff60d060%d|r%s", n, l, r,
      deck.truncated and " |cffffd100+|r" or ""))
    if deck.truncated then anyTruncated = true end
    if deck.id == Q.deckId then
      row.bg:SetColorTexture(0.3, 0.6, 1, 0.15)
    else
      row.bg:SetColorTexture(1, 1, 1, i % 2 == 0 and 0.03 or 0)
    end
    row:Show()
  end
  for i = #decks + 1, #v.rows do v.rows[i]:Hide() end
  if anyTruncated then
    v.info:SetText(v.info:GetText() .. "\n|cffffd100+|r More cards are due in Anki than were sent; Sync after finishing to get the rest.")
  end
  v.scroll.child:SetHeight(math.max(1, #decks * ROW_H))
end
