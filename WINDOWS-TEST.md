# Testing AnkiCraft on Windows (checklist for a test PC)

You need: WoW Forever installed, Anki desktop (25.x or newer) installed and opened at least once.

## Install
1. Copy the `AnkiCraft` folder from `AnkiCraft-<version>.zip` into
   `C:\Program Files (x86)\World of Warcraft\_forever_\Interface\AddOns\`
   (or wherever WoW is installed: Battle.net → WoW Forever → gear icon → *Show in Explorer*).
2. In Anki: *Tools → Add-ons → Install from file…* → pick `ankicraft_bridge-<version>.ankiaddon` → restart Anki.

## Check
| # | Do this | Expected |
|---|---|---|
| 1 | Anki: *Tools → AnkiCraft Bridge (World of Warcraft)…* | Top line says **Connected to …\_forever_** without browsing. If it doesn't, note where WoW is installed, then use *Browse…* |
| 2 | Click **Save & Sync now** | A message asks you to restart WoW. The Activity box says "Exported N cards…" |
| 3 | Click *Open data folder* | Explorer shows `AnkiCraft_Data` with `Cards.lua`, `AnkiCraft_Data.toc`, and `media\` with i001.tga… |
| 4 | Start WoW, log in | Chat says "N cards to review" |
| 5 | `/anki` and review 3–4 cards (Space, then 1–4). Try a card with Japanese text, one with an image, one with audio | Text and images render, audio plays |
| 6 | Press **Sync** in the window | UI reloads. Within ~3 s Anki shows a tooltip "AnkiCraft: 4 reviews…" |
| 7 | Press Sync again | The "Sync (N)" counter is gone (Anki confirmed the changes) |
| 8 | Anki: *Browse* → the cards you studied → *Card Info* | Reviews are listed with the times you answered in WoW |
| 9 | Add tab in WoW → add a note → Sync | Note appears in Anki tagged `AnkiCraft` |
| 10 | Review a few more, then **exit WoW completely** (not reload) | Anki applies them within ~3 s of WoW closing |

## If something fails, send back
- The Activity text from the Bridge settings window, or the file
  `%APPDATA%\Anki2\addons21\<addon folder>\user_files\ankicraft.log`
- Where WoW is installed
- Screenshots of any Lua error in WoW (enable with `/console scriptErrors 1`)
