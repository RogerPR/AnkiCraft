-- AnkiCraft addon tests. Run from the repo root:
--   luajit tests/lua/run.lua
-- End-to-end mode (used by tests/python/test_e2e.py):
--   luajit tests/lua/run.lua e2e <Cards.lua> <SavedVariables-in-or-""> <SavedVariables-out>
local here = arg[0]:gsub("[^/]+$", "")
package.path = here .. "?.lua;" .. package.path
local ADDON_DIR = here .. "../../AnkiCraft"

local passed, failed = 0, 0
local function test(name, fn)
  local stub = dofile(here .. "wowstub.lua")
  _G.AnkiCraftDB, _G.AnkiCraft_Data = nil, nil
  local ok, err = xpcall(function() fn(stub) end, debug.traceback)
  if ok then
    passed = passed + 1
    io.write("  ok   ", name, "\n")
  else
    failed = failed + 1
    io.write("  FAIL ", name, "\n", err, "\n")
  end
end

local function eq(a, b, msg)
  if a ~= b then error((msg or "values differ") .. ": expected " .. tostring(b) .. ", got " .. tostring(a), 2) end
end
local function truthy(v, msg) if not v then error(msg or "expected truthy", 2) end end

local function card(kind, reps, extra)
  local c = { nid = "n", kind = kind, reps = reps or 0, q = "Q", a = "A", ivl = { "<1m", "<6m", "<10m", "4d" } }
  for k, v in pairs(extra or {}) do c[k] = v end
  return c
end

local function sampleData(ack)
  return {
    format = 1, exportId = 1, exportedAt = 1800000000 - 120,
    ack = ack or {},
    mediaPath = "Interface\\AddOns\\AnkiCraft_Data\\media\\",
    decks = {
      { id = "10", name = "日本語", new = 2, learn = 1, review = 2, cards = { "1", "2", "3", "4", "5" } },
      { id = "20", name = "Other", new = 1, learn = 0, review = 0, cards = { "6" } },
    },
    addDecks = { { id = "10", name = "日本語" }, { id = "20", name = "Other" } },
    noteTypes = { { name = "Basic", fields = { "Front", "Back" } }, { name = "Cloze", fields = { "Text", "Back Extra" } } },
    cards = {
      ["1"] = card(2, 5, { qSnd = { "m001.mp3" }, qImg = { { f = "i001.tga", w = 300, h = 200, tw = 512, th = 256 } } }),
      ["2"] = card(2, 3),
      ["3"] = card(1, 1),
      ["4"] = card(0, 0, { aFull = true, aSnd = { "m002.mp3", "o001.ogg" }, missingImg = 1 }),
      ["5"] = card(0, 0, { flag = 2, marked = true }),
      ["6"] = card(0, 0),
    },
  }
end

local function boot(stub, data, db)
  _G.AnkiCraft_Data = data
  _G.AnkiCraftDB = db
  local ns = stub.loadAddon(ADDON_DIR, "AnkiCraft")
  stub.fire(ns, "ADDON_LOADED", "AnkiCraft")
  stub.fire(ns, "PLAYER_LOGIN")
  return ns
end

------------------------------------------------------------------ e2e mode
if arg[1] == "e2e" then
  local stub = dofile(here .. "wowstub.lua")
  stub.now = os.time()
  dofile(arg[2]) -- defines AnkiCraft_Data
  if arg[3] and arg[3] ~= "" then dofile(arg[3]) end
  local ns = boot(stub, _G.AnkiCraft_Data, _G.AnkiCraftDB)
  local Q = ns.Queue
  Q:SelectDefaultDeck()
  -- answer every card in the first deck: Again for the first, Good otherwise
  local first = true
  local guard = 0
  while Q:Current() and guard < 100 do
    guard = guard + 1
    local e = Q:Current()
    Q:Answer((first or e.again) and (e.again and 3 or 1) or 3, 1500)
    first = false
  end
  Q:AddNote(Q:AddDecks()[1].id, "Basic", { "追加", "added in WoW" }, "wow")
  local f = assert(io.open(arg[4], "w"))
  f:write(stub.savedVariables("AnkiCraftDB", _G.AnkiCraftDB))
  f:close()
  io.write(string.format("answered=%d pending=%d\n", guard, Q:PendingCount()))
  os.exit(0)
end

------------------------------------------------------------------ tests
print("AnkiCraft Lua tests")

test("loads without data and shows setup instructions", function(stub)
  local ns = boot(stub, nil, nil)
  eq(ns.DataState(), "missing")
  truthy(AnkiCraftDB.installId and #AnkiCraftDB.installId > 5, "installId generated")
  truthy(stub.messages[1]:find("AnkiCraft Bridge"), "login hint printed")
  ns.UI:Open()
  local v = ns.UI.views.review
  truthy(v.message:GetText():find("Welcome"), "setup message")
  truthy(not v.showBtn:IsShown(), "no show answer button")
  ns.UI:ShowView("decks")
  ns.UI:ShowView("add")
  ns.UI:ShowView("options")
end)

test("format mismatch is reported", function(stub)
  local data = sampleData()
  data.format = 99
  local ns = boot(stub, data, nil)
  eq(ns.DataState(), "format")
end)

test("deck selection and counts", function(stub)
  local ns = boot(stub, sampleData(), nil)
  local Q = ns.Queue
  eq(Q:TotalDue(), 6)
  truthy(Q:SelectDefaultDeck())
  eq(Q.deckId, "10")
  local n, l, r = Q:Counts()
  eq(n, 2); eq(l, 1); eq(r, 2)
  eq(Q:Current().cid, "1")
  eq(Q:Flag({ cid = "5", card = Q.cards["5"] }), 2)
  truthy(Q:IsMarked({ cid = "5", card = Q.cards["5"] }))
end)

test("answer, again requeue, undo", function(stub)
  local ns = boot(stub, sampleData(), nil)
  local Q = ns.Queue
  ns.db.settings.againGap = 2
  Q:SelectDeck("10")
  local op = Q:Answer(1, 1234)
  eq(op.t, "answer"); eq(op.cid, "1"); eq(op.ease, 1); eq(op.reps, 5); eq(op.ms, 1234); eq(op.seq, 1)
  eq(op.at, stub.now)
  -- card 1 comes back after 2 others
  eq(Q.list[1].cid, "2"); eq(Q.list[2].cid, "3"); eq(Q.list[3].cid, "1")
  truthy(Q.list[3].again)
  eq(Q:Intervals(Q.list[3]), nil)
  Q:Answer(3); Q:Answer(3)
  local again = Q:Current()
  eq(again.cid, "1")
  local op2 = Q:Answer(3)
  eq(op2.reps, 6, "second answer expects reps+1")
  eq(Q:PendingCount(), 4)
  eq(Q:ReviewedToday(), 4)
  -- undo the last answer: the again-card is back in front
  eq(Q:Undo(), "answer")
  eq(Q:Current().cid, "1")
  truthy(Q:Current().again)
  eq(Q:PendingCount(), 3)
  eq(Q:ReviewedToday(), 3)
  -- undo everything
  Q:Undo(); Q:Undo(); Q:Undo()
  eq(Q:PendingCount(), 0)
  eq(Q:Current().cid, "1")
  truthy(not Q:Current().again)
  eq(#Q.list, 5)
  eq(Q:Undo(), nil)
  eq(Q.hidden["1"], nil)
end)

test("suspend, bury, flag, mark and their undo", function(stub)
  local ns = boot(stub, sampleData(), nil)
  local Q = ns.Queue
  Q:SelectDeck("10")
  Q:Suspend()
  eq(Q:Current().cid, "2")
  Q:Bury()
  eq(Q:Current().cid, "3")
  Q:SetFlag(3)
  eq(Q:Flag(Q:Current()), 3)
  Q:SetFlag(3) -- same flag again clears it
  eq(Q:Flag(Q:Current()), 0)
  Q:ToggleMark()
  truthy(Q:IsMarked(Q:Current()))
  eq(Q:PendingCount(), 5)
  local kinds = {}
  for _ = 1, 5 do kinds[#kinds + 1] = Q:Undo() end
  eq(table.concat(kinds, ","), "mark,flag,flag,bury,suspend")
  eq(Q:Current().cid, "1")
  eq(#Q.list, 5)
  eq(Q:PendingCount(), 0)
end)

test("reload hides pending cards; ack prunes ops", function(stub)
  local ns = boot(stub, sampleData(), nil)
  local Q = ns.Queue
  Q:SelectDeck("10")
  Q:Answer(3); Q:Answer(4)
  Q:SetFlag(1)
  Q:AddNote("10", "Basic", { "a", "b" }, "")
  local db = AnkiCraftDB
  eq(#db.pending, 4)
  -- /reload before the bridge has processed: same data, same db
  local stub2 = dofile(here .. "wowstub.lua")
  local ns2 = boot(stub2, sampleData(), db)
  local Q2 = ns2.Queue
  eq(Q2:TotalDue(), 4)
  Q2:SelectDeck("10")
  eq(Q2:Current().cid, "3")
  eq(Q2:Flag(Q2:Current()), 1)
  truthy(stub2.messages[#stub2.messages]:find("4 changes"), "pending reminder printed")
  -- bridge processed seq 1..3 and re-exported (cards 1,2 no longer due)
  local data = sampleData({ [db.installId] = 3 })
  data.decks[1].cards = { "3", "4", "5" }
  local stub3 = dofile(here .. "wowstub.lua")
  local ns3 = boot(stub3, data, db)
  eq(#db.pending, 1)
  eq(db.pending[1].t, "add")
  -- new ops continue after the ack
  ns3.Queue:SelectDeck("10")
  eq(ns3.Queue:Answer(3).seq, 5)
end)

test("nextSeq never goes backwards below ack", function(stub)
  local db = { installId = "x", nextSeq = 1, pending = {} }
  local ns = boot(stub, sampleData({ x = 41 }), db)
  ns.Queue:SelectDeck("10")
  eq(ns.Queue:Answer(3).seq, 42)
end)

test("review UI: reveal, keys, media, answer, undo, card menu", function(stub)
  local ns = boot(stub, sampleData(), nil)
  local UI = ns.UI
  UI:Open("review")
  local v = UI.views.review
  local f = UI.frame
  truthy(f:IsShown())
  eq(v.entry.cid, "1")
  truthy(v.qText:GetText() == "Q")
  eq(v.qImages[1].texture, "Interface\\AddOns\\AnkiCraft_Data\\media\\i001.tga")
  eq(v.qImages[1].texcoord[2], 300 / 512)
  eq(stub.sounds[1], "Interface\\AddOns\\AnkiCraft_Data\\media\\m001.mp3", "autoplay question audio")
  truthy(v.showBtn:IsShown() and not v.easeButtons[1]:IsShown())
  truthy(f.keyboard, "keyboard captured in review")
  -- number keys before reveal only reveal
  f:Fire("OnKeyDown", "3")
  truthy(v.revealed)
  eq(f.propagate, false, "handled key doesn't propagate")
  stub.runTimers()
  eq(f.propagate, true)
  eq(v.easeButtons[4].ivl:GetText(), "4d")
  -- unhandled key propagates
  f:Fire("OnKeyDown", "W")
  eq(f.propagate, true)
  -- answer Good with the key
  f:Fire("OnKeyDown", "3")
  eq(ns.Queue:PendingCount(), 1)
  eq(v.entry.cid, "2")
  truthy(not v.revealed)
  -- space reveals then answers good
  f:Fire("OnKeyDown", "SPACE"); f:Fire("OnKeyDown", "SPACE")
  eq(v.entry.cid, "3")
  eq(v.syncBtn:GetText(), "Sync (2)")
  v.undoBtn:Click()
  eq(v.entry.cid, "2")
  -- card menu: suspend via first button
  v.cardBtn:Click()
  truthy(UI.cardMenu:IsShown())
  ns.Queue:Suspend(); UI:Review_Refresh()
  eq(v.entry.cid, "3")
  -- answer-only card (aFull) and missing media note
  ns.Queue:Answer(3); UI:Review_Refresh()
  eq(v.entry.cid, "4")
  UI:Review_ShowAnswer()
  truthy(not v.qText:IsShown(), "question hidden for full-answer templates")
  truthy(v.aAudio:IsShown())
  truthy(v.note:GetText():find("1 image"))
  -- finish the deck
  UI:Review_Answer(3)
  UI:Review_ShowAnswer(); UI:Review_Answer(3)
  eq(v.entry, nil)
  truthy(v.message:GetText():find("Congratulations"))
  -- sync button reloads
  v.syncBtn:Click()
  eq(stub.reloads, 1)
end)

test("combat hides and reopens; taxi auto-open/close", function(stub)
  local ns = boot(stub, sampleData(), nil)
  local UI = ns.UI
  UI:Open("review")
  stub.inCombat = true
  stub.fire(ns, "PLAYER_REGEN_DISABLED")
  truthy(not UI.frame:IsShown())
  stub.inCombat = false
  stub.fire(ns, "PLAYER_REGEN_ENABLED")
  truthy(UI.frame:IsShown())
  UI.frame:Hide()
  stub.onTaxi = true
  stub.fire(ns, "PLAYER_CONTROL_LOST")
  stub.runTimers()
  truthy(UI.frame:IsShown(), "opened on taxi")
  stub.onTaxi = false
  stub.fire(ns, "PLAYER_CONTROL_GAINED")
  stub.runTimers()
  truthy(not UI.frame:IsShown(), "closed after landing")
  -- manual open is not auto-closed
  UI:Open()
  stub.fire(ns, "PLAYER_CONTROL_GAINED")
  stub.runTimers()
  truthy(UI.frame:IsShown())
end)

test("decks, add note and options views", function(stub)
  local ns = boot(stub, sampleData(), nil)
  local UI = ns.UI
  UI:Open("decks")
  local dv = UI.views.decks
  eq(dv.rows[1].name:GetText(), "日本語")
  eq(dv.rows[2].name:GetText(), "Other")
  dv.rows[2]:Click()
  eq(UI.current, "review")
  eq(ns.Queue.deckId, "20")

  UI:ShowView("add")
  local av = UI.views.add
  eq(av.typeSel:Selected().label, "Basic")
  eq(av.deckSel:Selected().label, "Other")
  truthy(av.fields[2]:IsShown() and not av.fields[3]:IsShown())
  av.fields[1]:SetText("")
  av.addBtn:Click()
  truthy(av.status:GetText():find("empty"))
  av.fields[1]:SetText("猫")
  av.fields[2]:SetText("cat")
  av.tags:SetText(" animals ")
  av.addBtn:Click()
  local op = AnkiCraftDB.pending[1]
  eq(op.t, "add"); eq(op.deck, "20"); eq(op.notetype, "Basic"); eq(op.fields[1], "猫"); eq(op.tags, "animals")
  eq(av.fields[1]:GetText(), "")

  UI:ShowView("options")
  eq(UI.frame.keyboard, false, "no key capture outside review")
  ns.UI.minimapButton:Fire("OnEnter")
  SlashCmdList.ANKICRAFT("status")
  truthy(stub.messages[#stub.messages]:find("changes waiting"))
  SlashCmdList.ANKICRAFT("help")
  SlashCmdList.ANKICRAFT("")
  truthy(not UI.frame:IsShown())
  SlashCmdList.ANKICRAFT("sync")
  eq(stub.reloads, 1)
end)

test("truncated deck asks to sync for the next batch", function(stub)
  local data = sampleData()
  data.decks[2].truncated = true
  local ns = boot(stub, data, nil)
  ns.UI:Open("decks")
  truthy(ns.UI.views.decks.rows[2].counts:GetText():find("+", 1, true), "deck row marked")
  truthy(ns.UI.views.decks.info:GetText():find("More cards are due"), "explained")
  ns.Queue:SelectDeck("20")
  ns.UI:ShowView("review")
  ns.UI:Review_ShowAnswer(); ns.UI:Review_Answer(3)
  truthy(ns.UI.views.review.message:GetText():find("next batch"), "batch message")
end)

test("SavedVariables serializer output is parseable", function(stub)
  local text = stub.savedVariables("X", { a = "line1\nline2 \"q\"", list = { 1, 2 } })
  local chunk = assert(loadstring(text))
  chunk()
  eq(X.a, "line1\nline2 \"q\"")
  eq(X.list[2], 2)
end)

print(string.format("%d passed, %d failed", passed, failed))
os.exit(failed == 0 and 0 or 1)
