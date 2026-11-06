-- AnkiCraft: review Anki flashcards inside World of Warcraft.
-- Core: saved variables, events, slash commands.
local ADDON, ns = ...

ns.ADDON = ADDON
ns.DATA_FORMAT = 1
ns.FONT = "Interface\\AddOns\\AnkiCraft\\Fonts\\NotoSansJP-Regular.ttf"
ns.BRIDGE_NAME = "AnkiCraft Bridge"

local GetMeta = (C_AddOns and C_AddOns.GetAddOnMetadata) or GetAddOnMetadata
ns.version = (GetMeta and GetMeta(ADDON, "Version")) or "dev"

-- Indirections so the pure logic can be unit tested outside the game.
ns.now = time
ns.clock = GetTime

ns.defaults = {
  settings = {
    fontSize = 18,
    scale = 1.0,
    captureKeys = true,
    autoplay = true,
    autoTaxi = true,
    autoDead = false,
    autoRest = false,
    autoClose = true,
    hideInCombat = true,
    reopenAfterCombat = true,
    minimap = true,
    minimapAngle = 215,
    againGap = 4,
    showIntervals = true,
  },
  pending = {},
  nextSeq = 1,
  stats = {},
}

function ns.Print(msg)
  DEFAULT_CHAT_FRAME:AddMessage("|cff4fa3ffAnkiCraft|r: " .. tostring(msg))
end

local function applyDefaults(dst, src)
  for k, v in pairs(src) do
    if type(v) == "table" then
      if type(dst[k]) ~= "table" then dst[k] = {} end
      applyDefaults(dst[k], v)
    elseif dst[k] == nil then
      dst[k] = v
    end
  end
end
ns.applyDefaults = applyDefaults

function ns.NewInstallId()
  return string.format("%x-%x-%x", ns.now(), math.random(0, 0x7fffffff), math.floor((ns.clock() or 0) * 1000) % 0x7fffffff)
end

function ns.InitDB()
  if type(AnkiCraftDB) ~= "table" then AnkiCraftDB = {} end
  local db = AnkiCraftDB
  applyDefaults(db, ns.defaults)
  if type(db.installId) ~= "string" or db.installId == "" then
    db.installId = ns.NewInstallId()
  end
  ns.db = db
  return db
end

-- Returns: "ok", "missing" (data addon not loaded) or "format" (version mismatch)
function ns.DataState()
  local data = ns.data
  if type(data) ~= "table" or type(data.cards) ~= "table" then return "missing" end
  if data.format ~= ns.DATA_FORMAT then return "format" end
  return "ok"
end

function ns.Today()
  return date("%Y-%m-%d")
end

function ns.FormatAgo(ts)
  if not ts then return "never" end
  local d = ns.now() - ts
  if d < 90 then return "just now" end
  if d < 3600 then return string.format("%d min ago", math.floor(d / 60)) end
  if d < 86400 * 2 then return string.format("%d h ago", math.floor(d / 3600)) end
  return string.format("%d days ago", math.floor(d / 86400))
end

-- Save SavedVariables and pick up the latest export from Anki.
function ns.Sync()
  if InCombatLockdown and InCombatLockdown() then
    ns.Print("Can't sync during combat.")
    return
  end
  ReloadUI()
end

------------------------------------------------------------------ events
local events = CreateFrame("Frame")
ns.events = events
local handlers = {}

function handlers.ADDON_LOADED(name)
  if name ~= ADDON then return end
  ns.InitDB()
  ns.data = rawget(_G, "AnkiCraft_Data")
  ns.Queue:Init(ns.data, ns.db)
end

function handlers.PLAYER_LOGIN()
  ns.UI:Init()
  local state = ns.DataState()
  if state == "missing" then
    ns.Print("No cards yet. Install the free \"" .. ns.BRIDGE_NAME .. "\" add-on in Anki, open Anki, then restart WoW. Type /anki for help.")
  elseif state == "format" then
    ns.Print("Your AnkiCraft Bridge and this addon are different versions. Please update both.")
  else
    local due = ns.Queue:TotalDue()
    if due > 0 then
      ns.Print(string.format("%d cards to review. Type |cffffd100/anki|r to study.", due))
    end
    local pending = ns.Queue:PendingCount()
    if pending > 0 then
      ns.Print(string.format("%d changes are waiting for Anki. Keep Anki open, then /reload to sync.", pending))
    end
  end
end

function handlers.PLAYER_REGEN_DISABLED() ns.UI:OnCombat(true) end
function handlers.PLAYER_REGEN_ENABLED() ns.UI:OnCombat(false) end

function handlers.PLAYER_CONTROL_LOST()
  C_Timer.After(1, function()
    if UnitOnTaxi("player") and ns.db.settings.autoTaxi then
      ns.UI:AutoOpen("taxi")
    end
  end)
end

function handlers.PLAYER_CONTROL_GAINED()
  C_Timer.After(0.5, function()
    if not UnitOnTaxi("player") then ns.UI:AutoClose("taxi") end
  end)
end

function handlers.PLAYER_DEAD()
  if ns.db.settings.autoDead then ns.UI:AutoOpen("dead") end
end

function handlers.PLAYER_UNGHOST() ns.UI:AutoClose("dead") end
function handlers.PLAYER_ALIVE()
  if not UnitIsDeadOrGhost("player") then ns.UI:AutoClose("dead") end
end

function handlers.PLAYER_UPDATE_RESTING()
  if ns.db.settings.autoRest and IsResting() then
    ns.UI:AutoOpen("rest")
  end
end

events:SetScript("OnEvent", function(_, event, ...)
  local h = handlers[event]
  if h then h(...) end
end)
for event in pairs(handlers) do events:RegisterEvent(event) end

------------------------------------------------------------------ slash
local HELP = {
  "|cffffd100/anki|r - open or close the review window",
  "|cffffd100/anki sync|r - save and reload to sync with Anki (Anki must be open)",
  "|cffffd100/anki decks|r - choose a deck",
  "|cffffd100/anki add|r - add a new note",
  "|cffffd100/anki options|r - settings",
  "|cffffd100/anki reset|r - reset the window position",
  "|cffffd100/anki status|r - show sync status",
}

SLASH_ANKICRAFT1 = "/anki"
SLASH_ANKICRAFT2 = "/ankicraft"
SlashCmdList.ANKICRAFT = function(msg)
  local cmd = strlower(strtrim(msg or ""))
  if cmd == "" then
    ns.UI:Toggle()
  elseif cmd == "sync" or cmd == "reload" then
    ns.Sync()
  elseif cmd == "decks" or cmd == "deck" then
    ns.UI:Open("decks")
  elseif cmd == "add" then
    ns.UI:Open("add")
  elseif cmd == "options" or cmd == "config" or cmd == "settings" then
    ns.UI:Open("options")
  elseif cmd == "reset" then
    ns.UI:ResetPosition()
  elseif cmd == "status" then
    local data = ns.data
    ns.Print(string.format("version %s, data: %s, exported %s, %d cards due, %d changes waiting for Anki.",
      ns.version, ns.DataState(), ns.FormatAgo(data and data.exportedAt), ns.Queue:TotalDue(), ns.Queue:PendingCount()))
  else
    for _, line in ipairs(HELP) do ns.Print(line) end
  end
end

-- Key binding entry points (see Bindings.xml)
BINDING_HEADER_ANKICRAFT = "AnkiCraft"
BINDING_NAME_ANKICRAFT_TOGGLE = "Open/close review window"
BINDING_NAME_ANKICRAFT_SHOW = "Show answer"
BINDING_NAME_ANKICRAFT_AGAIN = "Answer: Again"
BINDING_NAME_ANKICRAFT_HARD = "Answer: Hard"
BINDING_NAME_ANKICRAFT_GOOD = "Answer: Good"
BINDING_NAME_ANKICRAFT_EASY = "Answer: Easy"
BINDING_NAME_ANKICRAFT_UNDO = "Undo last answer"

function AnkiCraft_Toggle() ns.UI:Toggle() end
function AnkiCraft_ShowAnswer() ns.UI:Review_ShowAnswer() end
function AnkiCraft_Answer(ease) ns.UI:Review_Answer(ease) end
function AnkiCraft_Undo() ns.UI:Review_Undo() end
