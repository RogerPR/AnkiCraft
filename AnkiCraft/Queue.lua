-- Queue: the study session logic. Pure Lua (no frames) so it can be tested
-- outside the game with tests/lua/run.lua.
--
-- Every change made in WoW becomes an "op" in AnkiCraftDB.pending. The Anki
-- bridge applies ops with seq > its stored ack and writes ack[installId]
-- into AnkiCraft_Data, after which the addon drops them.
local _, ns = ...

local Q = {}
ns.Queue = Q

local HIDING_OPS = { answer = true, suspend = true, bury = true }

local function removeWhere(list, pred)
  for i = #list, 1, -1 do
    if pred(list[i]) then table.remove(list, i) end
  end
end

function Q:Init(data, db)
  self.data = (type(data) == "table" and type(data.cards) == "table") and data or nil
  self.db = db
  self.cards = self.data and self.data.cards or {}
  self.list = {}
  self.deckId = nil
  self.undoStack = {}
  self.answersThisSession = {}
  self:PruneAcked()
  self:RebuildOverrides()
end

function Q:Ack()
  local data = self.data
  local ack = data and type(data.ack) == "table" and data.ack[self.db.installId]
  return tonumber(ack) or 0
end

-- Drop ops the bridge has confirmed.
function Q:PruneAcked()
  local ack = self:Ack()
  if ack <= 0 then return end
  removeWhere(self.db.pending, function(op) return (op.seq or 0) <= ack end)
  if (self.db.nextSeq or 1) <= ack then self.db.nextSeq = ack + 1 end
end

-- Cards with pending answer/suspend/bury ops are hidden (until Anki has
-- re-exported them); pending flag/mark ops override the exported values.
function Q:RebuildOverrides()
  self.hidden, self.flags, self.marks = {}, {}, {}
  for _, op in ipairs(self.db.pending) do
    if HIDING_OPS[op.t] then
      self.hidden[op.cid] = true
    elseif op.t == "flag" then
      self.flags[op.cid] = op.flag
    elseif op.t == "mark" then
      self.marks[op.cid] = op.on and true or false
    end
  end
end

function Q:HasData() return self.data ~= nil end

function Q:Decks()
  return self.data and self.data.decks or {}
end

function Q:FindDeck(id)
  for _, d in ipairs(self:Decks()) do
    if d.id == id then return d end
  end
end

-- Remaining counts for a deck (new, learn, review), excluding hidden cards.
function Q:DeckCounts(deck)
  local n, l, r = 0, 0, 0
  for _, cid in ipairs(deck.cards or {}) do
    local c = self.cards[cid]
    if c and not self.hidden[cid] then
      if c.kind == 0 then n = n + 1 elseif c.kind == 1 then l = l + 1 else r = r + 1 end
    end
  end
  return n, l, r
end

function Q:TotalDue()
  local seen, total = {}, 0
  for _, deck in ipairs(self:Decks()) do
    for _, cid in ipairs(deck.cards or {}) do
      if not seen[cid] and self.cards[cid] and not self.hidden[cid] then
        seen[cid] = true
        total = total + 1
      end
    end
  end
  return total
end

function Q:SelectDeck(id)
  local deck = self:FindDeck(id)
  self.list = {}
  self.deckId = deck and deck.id or nil
  if not deck then return false end
  self.db.lastDeck = deck.id
  for _, cid in ipairs(deck.cards or {}) do
    local c = self.cards[cid]
    if c and not self.hidden[cid] then
      self.list[#self.list + 1] = { cid = cid, card = c }
    end
  end
  return true
end

-- Pick the last used deck, else the first deck with cards.
function Q:SelectDefaultDeck()
  if self.db.lastDeck and self:FindDeck(self.db.lastDeck) then
    local n, l, r = self:DeckCounts(self:FindDeck(self.db.lastDeck))
    if n + l + r > 0 then return self:SelectDeck(self.db.lastDeck) end
  end
  for _, d in ipairs(self:Decks()) do
    local n, l, r = self:DeckCounts(d)
    if n + l + r > 0 then return self:SelectDeck(d.id) end
  end
  local first = self:Decks()[1]
  return first and self:SelectDeck(first.id) or false
end

function Q:Current() return self.list[1] end

function Q:Counts()
  local n, l, r = 0, 0, 0
  for _, e in ipairs(self.list) do
    if e.again or e.card.kind == 1 then l = l + 1
    elseif e.card.kind == 0 then n = n + 1
    else r = r + 1 end
  end
  return n, l, r
end

function Q:PendingCount() return #self.db.pending end

function Q:AddOp(op)
  local seq = math.max(self.db.nextSeq or 1, self:Ack() + 1)
  op.seq = seq
  self.db.nextSeq = seq + 1
  table.insert(self.db.pending, op)
  return op
end

function Q:RemoveOp(op)
  for i = #self.db.pending, 1, -1 do
    if self.db.pending[i] == op then
      table.remove(self.db.pending, i)
      return true
    end
  end
  return false
end

function Q:BumpStats(delta)
  local stats = self.db.stats
  local day = ns.Today and ns.Today() or "today"
  if stats.day ~= day then
    stats.day, stats.reviewed = day, 0
  end
  stats.reviewed = math.max(0, (stats.reviewed or 0) + delta)
end

function Q:ReviewedToday()
  local stats = self.db.stats
  if ns.Today and stats.day ~= ns.Today() then return 0 end
  return stats.reviewed or 0
end

-- Interval labels are only meaningful for the first answer of a card.
function Q:Intervals(entry)
  if not entry or entry.again then return nil end
  return entry.card.ivl
end

function Q:Answer(ease, ms)
  ease = tonumber(ease)
  if not ease or ease < 1 or ease > 4 then return nil end
  local e = table.remove(self.list, 1)
  if not e then return nil end
  local cid = e.cid
  local prior = self.answersThisSession[cid] or 0
  local op = self:AddOp({
    t = "answer", cid = cid, ease = ease,
    at = ns.now(), ms = ms and math.floor(ms) or nil,
    reps = (e.card.reps or 0) + prior,
  })
  self.answersThisSession[cid] = prior + 1
  self.hidden[cid] = true
  local requeued
  if ease == 1 then
    requeued = { cid = cid, card = e.card, again = true }
    local gap = tonumber(self.db.settings and self.db.settings.againGap) or 4
    table.insert(self.list, math.min(#self.list + 1, gap + 1), requeued)
  end
  table.insert(self.undoStack, { kind = "answer", entry = e, op = op, requeued = requeued })
  self:BumpStats(1)
  return op
end

-- Remove the current card from the session (suspend / bury).
function Q:RemoveCurrent(kind)
  local e = self.list[1]
  if not e then return nil end
  local op = self:AddOp({ t = kind, cid = e.cid })
  local removed = {}
  for i = #self.list, 1, -1 do
    if self.list[i].cid == e.cid then
      table.insert(removed, 1, { index = i, entry = table.remove(self.list, i) })
    end
  end
  self.hidden[e.cid] = true
  table.insert(self.undoStack, { kind = kind, op = op, removed = removed })
  return op
end

function Q:Suspend() return self:RemoveCurrent("suspend") end
function Q:Bury() return self:RemoveCurrent("bury") end

function Q:Flag(entry)
  if not entry then return 0 end
  local f = self.flags[entry.cid]
  if f == nil then f = entry.card.flag end
  return tonumber(f) or 0
end

function Q:IsMarked(entry)
  if not entry then return false end
  local m = self.marks[entry.cid]
  if m == nil then m = entry.card.marked end
  return m and true or false
end

function Q:SetFlag(flag)
  local e = self.list[1]
  if not e then return nil end
  flag = tonumber(flag) or 0
  if self:Flag(e) == flag then flag = 0 end -- choosing the same flag clears it
  local previous = self.flags[e.cid]
  local op = self:AddOp({ t = "flag", cid = e.cid, flag = flag })
  self.flags[e.cid] = flag
  table.insert(self.undoStack, { kind = "flag", op = op, cid = e.cid, previous = previous })
  return op
end

function Q:ToggleMark()
  local e = self.list[1]
  if not e then return nil end
  local on = not self:IsMarked(e)
  local previous = self.marks[e.cid]
  local op = self:AddOp({ t = "mark", cid = e.cid, on = on })
  self.marks[e.cid] = on
  table.insert(self.undoStack, { kind = "mark", op = op, cid = e.cid, previous = previous })
  return op
end

function Q:CanUndo() return #self.undoStack > 0 end

-- Returns the undone kind, or nil when there is nothing (left) to undo.
function Q:Undo()
  local u = table.remove(self.undoStack)
  if not u then return nil end
  if not self:RemoveOp(u.op) then
    -- already synced to Anki; can't undo here anymore
    self.undoStack = {}
    return nil
  end
  if u.kind == "answer" then
    local cid = u.entry.cid
    if u.requeued then
      removeWhere(self.list, function(x) return x == u.requeued end)
    end
    self.answersThisSession[cid] = math.max(0, (self.answersThisSession[cid] or 1) - 1)
    table.insert(self.list, 1, u.entry)
    self:BumpStats(-1)
  elseif u.kind == "suspend" or u.kind == "bury" then
    for _, r in ipairs(u.removed) do
      table.insert(self.list, math.min(r.index, #self.list + 1), r.entry)
    end
  elseif u.kind == "flag" then
    self.flags[u.cid] = u.previous
  elseif u.kind == "mark" then
    self.marks[u.cid] = u.previous
  end
  -- recompute hidden state from what is still pending
  self.hidden = {}
  for _, op in ipairs(self.db.pending) do
    if HIDING_OPS[op.t] then self.hidden[op.cid] = true end
  end
  return u.kind
end

-- fields: list of strings in note type field order
function Q:AddNote(deckId, notetype, fields, tags)
  return self:AddOp({ t = "add", deck = deckId, notetype = notetype, fields = fields, tags = tags })
end

function Q:AddDecks() return self.data and self.data.addDecks or {} end
function Q:NoteTypes() return self.data and self.data.noteTypes or {} end
