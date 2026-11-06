-- usage: luajit dump_data.lua <path/to/Cards.lua>
-- Loads a generated AnkiCraft_Data file exactly like WoW would (plain Lua 5.1
-- chunk) and prints it as JSON so Python tests can inspect it.
package.path = arg[0]:gsub("[^/]+$", "") .. "?.lua;" .. package.path
local json = require("json")
local chunk, err = loadfile(arg[1])
if not chunk then
  io.stderr:write(err, "\n")
  os.exit(2)
end
chunk()
io.write(json.encode(AnkiCraft_Data))
