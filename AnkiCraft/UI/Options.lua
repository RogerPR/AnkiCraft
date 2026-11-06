-- Options view.
local _, ns = ...
local W, UI = ns.W, ns.UI

function UI:CreateOptionsView(parent)
  local v = CreateFrame("Frame", nil, parent)
  local scroll = W.Scroll(v)
  scroll:SetPoint("TOPLEFT", 0, 0)
  scroll:SetPoint("BOTTOMRIGHT", -24, 0)
  local c = scroll.child
  local s = function() return ns.db.settings end
  local controls = {}
  local y = -4

  local function header(text)
    local h = W.Text(c, GameFontNormal)
    h:SetPoint("TOPLEFT", 4, y - 4)
    h:SetText(text)
    y = y - 24
  end

  local function check(key, label, tip, after)
    local cb = W.Check(c, label, function() return s()[key] end, function(val)
      s()[key] = val
      if after then after(val) end
    end, tip)
    cb:SetPoint("TOPLEFT", 8, y)
    controls[#controls + 1] = cb
    y = y - 26
  end

  local function stepper(key, label, minV, maxV, step, fmt, after)
    local st = W.Stepper(c, label, function() return s()[key] end, function(val)
      s()[key] = val
      if after then after(val) end
    end, minV, maxV, step, fmt)
    st:SetPoint("TOPLEFT", 8, y)
    controls[#controls + 1] = st
    y = y - 28
  end

  header("Display")
  stepper("fontSize", "Card text size", 10, 40, 1, "%d", function()
    W.UpdateFonts()
  end)
  stepper("scale", "Window scale", 0.6, 1.6, 0.05, "%.2f", function(val)
    UI.frame:SetScale(val)
  end)
  check("showIntervals", "Show next intervals above answer buttons")
  check("minimap", "Show minimap button", nil, function() UI:UpdateMinimapButton() end)

  header("Studying")
  check("captureKeys", "Keyboard shortcuts while the window is open",
    "Space/Enter: show answer, then Good. 1-4: Again/Hard/Good/Easy.\nWhile the window is open these keys won't jump or cast action bar 1-4.",
    function() UI:UpdateKeyboard() end)
  check("autoplay", "Play card audio automatically")
  stepper("againGap", "\"Again\" cards come back after", 0, 20, 1, "%d cards")

  header("Automatic")
  check("autoTaxi", "Open when taking a flight path")
  check("autoDead", "Open when you die (study during the corpse run)")
  check("autoRest", "Open when entering an inn or city")
  check("autoClose", "Close again automatically when that ends")
  check("hideInCombat", "Hide during combat")
  check("reopenAfterCombat", "Reopen after combat")

  header("Sync")
  local info = W.Text(c, GameFontHighlightSmall)
  info:SetPoint("TOPLEFT", 8, y)
  info:SetPoint("RIGHT", c, "RIGHT", -8, 0)
  info:SetText("WoW can only exchange data with Anki when the UI reloads. Keep Anki open with the AnkiCraft Bridge add-on, "
    .. "study here, then press Sync (or type /reload). Decks, card limits, furigana and media are configured in Anki: "
    .. "Tools > AnkiCraft Bridge.")
  y = y - 70
  local reset = W.Button(c, "Reset window position", 180, 22, function() UI:ResetPosition() end)
  reset:SetPoint("TOPLEFT", 8, y)
  y = y - 30

  c:SetHeight(-y + 10)
  v.Refresh = function()
    for _, ctl in ipairs(controls) do ctl:Refresh() end
  end
  return v
end
