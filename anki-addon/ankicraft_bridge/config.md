Most settings are easier to change in **Tools → AnkiCraft Bridge (World of Warcraft)…**.

- `wow_path`: your World of Warcraft folder. Empty = auto-detect.
- `flavor`: the game version folder inside it, e.g. `_forever_`, `_classic_era_`, `_retail_`.
- `decks`: deck names to send to WoW. Empty = every top-level deck.
- `max_cards_per_deck` / `max_total_cards`: caps on exported cards (Anki's own daily limits still apply).
- `furigana`: `brackets` (漢字[かんじ]), `kanji` (hide readings) or `kana` (reading only).
- `media`: send images and audio to WoW.
- `image_max_size`: longest image side in pixels.
- `image_slots` / `audio_slots`: size of the media file pool. Raising these requires a full WoW restart.
- `auto_sync`: watch WoW's SavedVariables and sync automatically.
- `poll_seconds`: how often to check for changes from WoW.
