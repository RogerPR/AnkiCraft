# AnkiCraft: Anki flashcards inside World of Warcraft

Study your real Anki decks while you fly, wait for a group or run back from the graveyard.
Your reviews go back into Anki and are scheduled by Anki's own scheduler (FSRS or SM-2),
timestamped with the moment you answered in-game.

Built for **WoW Forever** (interface 16001).

## What it does

- Review due and new cards from the decks you choose: **Show Answer**, then **Again / Hard / Good / Easy**, with Anki's next-interval labels.
- **Japanese text** works out of the box (bundled Noto Sans JP font). Furigana is shown as `漢字[かんじ]`, or with readings hidden, or as kana only.
- **Images and audio** from your cards (mp3/ogg), with an auto-play option.
- **Undo**, **suspend**, **bury**, **flag** and **mark** cards.
- **Add new notes** in-game. They're created in Anki on the next sync.
- Optionally **opens automatically** on flight paths, when you die, or when you enter an inn. It hides during combat.
- Keyboard: **Space/Enter** shows the answer, then answers Good. **1–4** answer. You can also set key bindings under *Key Bindings → AddOns → AnkiCraft*.
- Minimap button, `/anki` slash command, and a movable, resizable, scalable window.

## How it works (why there are two parts)

WoW addons can't access the internet or your files. They can only save data when the UI reloads.
So AnkiCraft has two parts:

| Part | Where | Job |
|---|---|---|
| **AnkiCraft** | WoW addon (CurseForge) | Shows cards and records what you do |
| **AnkiCraft Bridge** | Anki add-on (AnkiWeb) | While Anki is open, sends due cards to WoW and applies your in-game reviews to Anki |

```
Anki + Bridge ──writes──► Interface/AddOns/AnkiCraft_Data   (your cards, images, audio)
WoW  /reload  ──writes──► WTF/.../SavedVariables/AnkiCraft.lua  (your reviews)
Bridge notices within ~3 s ─► applies reviews in Anki ─► sends fresh cards back
```

## Setup (one time)

1. **Install the WoW addon**: install *AnkiCraft* with the CurseForge app, or unzip it into
   `World of Warcraft/_forever_/Interface/AddOns/`.
2. **Install the Anki add-on**: in Anki desktop, go to *Tools → Add-ons → Get Add-ons…* and paste the
   AnkiCraft Bridge code from AnkiWeb. Restart Anki.
3. Open *Tools → AnkiCraft Bridge (World of Warcraft)…* in Anki.
   - Check that it says **Connected to …/_forever_**. If not, click *Browse…* and pick your
     `World of Warcraft` folder.
   - Optionally tick the decks you want in WoW. If you tick none, every top-level deck is sent.
   - Click **Save & Sync now**. The first time, Anki tells you to restart WoW.
4. **Fully restart WoW** (exit the game and start it again). This is only needed once, because WoW only
   sees new files when it starts.

## Daily use

1. Open Anki and leave it running (it can be minimized).
2. In WoW, type `/anki` or click the book icon on the minimap.
3. Study: press Space to show the answer, then 1–4 (or click the buttons).
4. When you're done, or whenever you want, press **Sync** (or type `/reload`). This saves your reviews
   and Anki applies them within a few seconds. Press Sync once more if you want the freshly scheduled cards
   right away.
5. Your reviews sync to AnkiWeb and your phone the next time Anki syncs, as usual.

If you play without Anki open, your reviews are kept safely in WoW. They're sent to Anki the next time
both are running and you `/reload` or log out.

## Commands

| Command | |
|---|---|
| `/anki` | open/close the window |
| `/anki sync` | save and reload to sync with Anki |
| `/anki decks` | choose a deck |
| `/anki add` | add a note |
| `/anki options` | settings |
| `/anki status` | sync status |
| `/anki reset` | reset window position |

## Good to know

- **Scheduling**: each review is applied by Anki exactly as if you had answered on the desktop at
  that moment. In-game, a card you press *Again* on comes back after a few cards (you can change this in Options).
  Learning steps continue properly after the next sync.
- **Reviewed elsewhere**: if you review the same card on your phone before syncing, the in-game review
  of that card is skipped (shown in *Decks* as "skipped") instead of being applied twice.
- **Undo in Anki**: each batch from WoW is one undo step (*Edit → Undo AnkiCraft: reviews from WoW*).
- **HTML**: cards are converted to plain text with colors for bold, italics and cloze. Custom CSS layouts and
  JavaScript don't carry over.
- **Fonts**: the bundled font covers Latin, Greek, Cyrillic, kana and about 6,800 kanji (all Jōyō/Jinmeiyō).
  Chinese-only or Korean characters may not display.
- **Images and audio**: WoW can only load files that existed when the game started. The Bridge therefore
  keeps a fixed pool of image and audio files (200 each by default) and reuses them. If you change the pool
  size, restart WoW. Supported audio: mp3 and ogg.

## Troubleshooting

- **"No cards yet" in WoW**: Anki isn't open, the Bridge isn't installed, or you haven't restarted WoW since
  the first sync. Check *Tools → AnkiCraft Bridge* in Anki.
- **Reviews don't show up in Anki**: WoW writes them only on `/reload`, logout or exit. Look at the Activity
  log in the Bridge settings.
- **Images show as blank**: restart WoW once (see above).

## Development

```
AnkiCraft/                 the WoW addon
anki-addon/ankicraft_bridge/   the Anki add-on
tests/lua/run.lua          luajit tests with WoW API stubs
tests/python/              pytest against a real Anki collection (pip package `anki`)
tools/build_font.py        rebuilds the Japanese font subset
tools/package.sh           builds dist/ release files
```

```bash
python3 -m venv .venv && .venv/bin/pip install anki==26.9.2 pytest PyQt6 fonttools
luajit tests/lua/run.lua
.venv/bin/python -m pytest tests/python
tools/package.sh
```

## Support

Bugs and ideas: https://github.com/RogerPR/AnkiCraft/issues
When reporting a sync problem, include the Activity log from *Tools → AnkiCraft Bridge* in Anki.

License: MIT. Bundled font: Noto Sans JP, SIL Open Font License 1.1.
