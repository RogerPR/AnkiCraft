"""Build and write AnkiCraft_Data (the file the WoW addon reads)."""

from __future__ import annotations

import os
import re
import time
from typing import Any

import anki.collection  # noqa: F401  (must load before anki.cards)
from anki.cards import Card

from . import fsutil, luaser
from .media import MediaPool
from .render import render_card

BRIDGE_VERSION = "1.0.0"
DATA_FORMAT = 1
DATA_ADDON = "AnkiCraft_Data"
DEFAULT_INTERFACE = "16001"
WOW_MEDIA_PATH = "Interface\\AddOns\\AnkiCraft_Data\\media\\"
SKIP_NOTETYPES = {"Image Occlusion"}
_BIDI_RE = re.compile("[⁦-⁩‎‏]")
CARDS_PER_CHUNK = 150


def _clean_label(s: str) -> str:
    return _BIDI_RE.sub("", s)


def _find_node(node, did: int):
    if node.deck_id == did:
        return node
    for ch in node.children:
        r = _find_node(ch, did)
        if r is not None:
            return r
    return None


def selected_decks(col, names: list[str]) -> list[tuple[int, str]]:
    """Resolve configured deck names; empty means every top-level deck that
    has cards (skipping an empty 'Default')."""
    out: list[tuple[int, str]] = []
    if names:
        for name in names:
            did = col.decks.id_for_name(name)
            if did:
                out.append((int(did), col.decks.name(did)))
        return out
    tree = col.sched.deck_due_tree()
    for child in tree.children:
        if child.deck_id == 1 and col.decks.card_count(1, include_subdecks=True) == 0:
            continue
        out.append((int(child.deck_id), child.name))
    return out


def build_export(
    col,
    cfg: dict,
    acks: dict[str, int] | None = None,
    pool: MediaPool | None = None,
    last_sync: dict | None = None,
) -> dict[str, Any]:
    furigana = cfg.get("furigana", "brackets")
    max_cards = int(cfg.get("max_cards_per_deck", 1000))
    max_total = int(cfg.get("max_total_cards", 5000))

    decks_out: list[dict] = []
    cards: dict[str, dict] = {}
    media_wanted: list[tuple[str, str]] = []
    tree = col.sched.deck_due_tree()
    original = col.decks.get_current_id()
    try:
        for did, name in selected_decks(col, cfg.get("decks") or []):
            node = _find_node(tree, did)
            col.decks.select(did)
            qc = col.sched.get_queued_cards(fetch_limit=max_cards + 1)
            ids: list[str] = []
            hit_total = False
            for queued in list(qc.cards)[:max_cards]:
                cid = str(queued.card.id)
                ids.append(cid)
                if cid in cards:
                    continue
                if len(cards) >= max_total:
                    ids.pop()
                    hit_total = True
                    break
                card = Card(col, backend_card=queued.card)
                r = render_card(card, furigana)
                note = card.note()
                labels = [_clean_label(x) for x in col.sched.describe_next_states(queued.states)]
                entry = {
                    "nid": str(card.nid),
                    "kind": int(queued.queue),  # 0 new, 1 learning, 2 review
                    "reps": int(card.reps),
                    "q": r["q"],
                    "a": r["a"],
                    "aFull": r["aFull"] or None,
                    "ivl": labels,
                    "flag": card.user_flag() or None,
                    "marked": note.has_tag("marked") or None,
                    "_qi": r["qImages"],
                    "_ai": r["aImages"],
                    "_qs": r["qAudio"],
                    "_as": r["aAudio"],
                }
                cards[cid] = entry
                if cfg.get("media", True):
                    media_wanted += [("img", f) for f in r["qImages"] + r["aImages"]]
                    media_wanted += [("audio", f) for f in r["qAudio"] + r["aAudio"]]
            counts = (
                (int(node.new_count), int(node.learn_count), int(node.review_count))
                if node
                else (qc.new_count, qc.learning_count, qc.review_count)
            )
            decks_out.append(
                {
                    "id": str(did),
                    "name": name,
                    "new": counts[0],
                    "learn": counts[1],
                    "review": counts[2],
                    "cards": ids,
                    # a card limit was reached: Anki has more due than we sent
                    "truncated": (hit_total or len(qc.cards) > max_cards) or None,
                }
            )
    finally:
        col.decks.select(original)

    slots = {}
    if pool is not None and media_wanted:
        slots = pool.assign(media_wanted, col.media.dir())

    def _imgs(files: list[str]) -> list[dict] | None:
        out = []
        for f in files:
            ref = slots.get(("img", f))
            if ref:
                out.append({"f": ref.file, "w": ref.w, "h": ref.h, "tw": ref.tw, "th": ref.th})
        return out or None

    def _snds(files: list[str]) -> list[str] | None:
        out = [slots[("audio", f)].file for f in files if ("audio", f) in slots]
        return out or None

    for entry in cards.values():
        qi, ai, qs, as_ = entry.pop("_qi"), entry.pop("_ai"), entry.pop("_qs"), entry.pop("_as")
        entry["qImg"], entry["aImg"] = _imgs(qi), _imgs(ai)
        entry["qSnd"], entry["aSnd"] = _snds(qs), _snds(as_)
        missing = (len(qi) + len(ai)) - len(entry["qImg"] or []) - len(entry["aImg"] or [])
        if missing > 0:
            entry["missingImg"] = missing
        missing_snd = (len(qs) + len(as_)) - len(entry["qSnd"] or []) - len(entry["aSnd"] or [])
        if missing_snd > 0:
            entry["missingSnd"] = missing_snd

    note_types = []
    for nt in col.models.all_names_and_ids():
        if nt.name in SKIP_NOTETYPES:
            continue
        model = col.models.get(nt.id)
        if not model:
            continue
        note_types.append({"name": nt.name, "fields": [f["name"] for f in model["flds"]]})

    add_decks = [
        {"id": str(d.id), "name": d.name}
        for d in col.decks.all_names_and_ids(include_filtered=False)
    ]

    now = time.time()
    return {
        "format": DATA_FORMAT,
        "bridge": BRIDGE_VERSION,
        "exportId": int(now * 1000),
        "exportedAt": int(now),
        "ack": dict(acks or {}),
        "lastSync": last_sync,
        "mediaPath": WOW_MEDIA_PATH,
        "decks": decks_out,
        "addDecks": add_decks,
        "noteTypes": note_types,
        "cards": cards,
    }


def to_lua(data: dict[str, Any]) -> str:
    """Render the export as Lua. Cards are split into separate functions so
    no single function exceeds Lua 5.1's constant limit on huge exports."""
    head = {k: v for k, v in data.items() if k != "cards"}
    parts = [
        "-- Generated by the AnkiCraft Bridge Anki add-on. Do not edit; it is overwritten on every sync.\n",
        "AnkiCraft_Data = ",
        luaser.dumps(head),
        "\nlocal C = {}\nAnkiCraft_Data.cards = C\n",
    ]
    items = list(data.get("cards", {}).items())
    for i in range(0, len(items), CARDS_PER_CHUNK):
        parts.append("do local function f()\n")
        for cid, entry in items[i : i + CARDS_PER_CHUNK]:
            parts.append(f"C[{luaser.quote(cid)}]={luaser.dumps(entry)}\n")
        parts.append("end f() end\n")
    return "".join(parts)


def _atomic_write(path: str, content: str) -> None:
    fsutil.write_atomic(path, content)


def toc_text(interface: str) -> str:
    return (
        f"## Interface: {interface}\n"
        "## Title: AnkiCraft Data\n"
        "## Notes: Your Anki cards, generated by the AnkiCraft Bridge Anki add-on. Do not edit.\n"
        "## Author: AnkiCraft Bridge\n"
        f"## Version: {BRIDGE_VERSION}\n"
        "Cards.lua\n"
    )


def write_data_addon(addons_dir: str, data: dict[str, Any], interface: str) -> tuple[str, bool]:
    """Write AnkiCraft_Data/{AnkiCraft_Data.toc,Cards.lua}. Returns
    (folder, created) where created means a WoW restart is needed."""
    folder = os.path.join(addons_dir, DATA_ADDON)
    toc = os.path.join(folder, DATA_ADDON + ".toc")
    created = not os.path.exists(toc)
    os.makedirs(folder, exist_ok=True)
    want_toc = toc_text(interface)
    try:
        with open(toc, encoding="utf-8") as f:
            current = f.read()
    except OSError:
        current = None
    if current != want_toc:
        _atomic_write(toc, want_toc)
    _atomic_write(os.path.join(folder, "Cards.lua"), to_lua(data))
    return folder, created
