-- Media: card images (TGA textures) and audio (mp3/ogg) written by the
-- bridge into Interface\AddOns\AnkiCraft_Data\media\ slot files.
local _, ns = ...

local M = {}
ns.Media = M

local DEFAULT_PATH = "Interface\\AddOns\\AnkiCraft_Data\\media\\"

function M:Path(file)
  local base = (ns.data and ns.data.mediaPath) or DEFAULT_PATH
  return base .. file
end

-- Size an image to fit inside maxW x maxH (never upscaled past 2x).
function M:FitSize(img, maxW, maxH)
  local w, h = img.w or 64, img.h or 64
  local scale = math.min(maxW / w, maxH / h, 2)
  return math.max(1, math.floor(w * scale)), math.max(1, math.floor(h * scale))
end

-- Apply an exported image to a texture. Images are padded to power-of-two
-- sizes by the bridge, so only the top-left w x h part is shown.
function M:ApplyTexture(tex, img)
  tex:SetTexture(self:Path(img.f))
  local tw, th = img.tw or img.w or 1, img.th or img.h or 1
  tex:SetTexCoord(0, (img.w or tw) / tw, 0, (img.h or th) / th)
end

function M:Stop()
  if self.handle then
    StopSound(self.handle)
    self.handle = nil
  end
end

-- Plays a list of audio files one after another.
function M:Play(files)
  self:Stop()
  self.playToken = (self.playToken or 0) + 1
  if type(files) ~= "table" or #files == 0 then return false end
  local token = self.playToken
  local index = 0
  local function playNext()
    if token ~= self.playToken then return end
    index = index + 1
    local file = files[index]
    if not file then return end
    local willPlay, handle = PlaySoundFile(self:Path(file), "Master")
    self.handle = willPlay and handle or nil
    if index < #files then
      -- PlaySoundFile gives no duration; leave a generous gap for word audio.
      C_Timer.After(2.5, playNext)
    end
  end
  playNext()
  return true
end
