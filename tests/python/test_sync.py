import json
import os
import shutil
import subprocess
import time

import pytest

from anki.scheduler_pb2 import CardAnswer

from ankicraft_bridge import exporter, importer, luaser
from ankicraft_bridge.bridge import Bridge
from conftest import ROOT, add_basic

LUAJIT = shutil.which("luajit")


def load_lua_data(path):
    if not LUAJIT:
        pytest.skip("luajit not installed")
    out = subprocess.run(
        [LUAJIT, os.path.join(ROOT, "tests", "lua", "dump_data.lua"), path],
        capture_output=True, check=True,
    )
    return json.loads(out.stdout)


def write_sv(path, db):
    path.write_text("\nAnkiCraftDB = " + luaser.dumps(db) + "\n", encoding="utf-8")


def make_bridge(wow):
    return Bridge({"wow_path": str(wow), "flavor": "_forever_", "image_slots": 4, "audio_slots": 4}, log=lambda *_: None)


def test_export_is_valid_lua(col, wow):
    add_basic(col, "日本語", "<b>猫</b> <ruby>猫<rt>ねこ</rt></ruby>", "cat | 'quote' \"dq\"")
    add_basic(col, "日本語::Sub", "犬", "dog")
    add_basic(col, "Other", "x", "y")
    b = make_bridge(wow)
    res = b.export(col)
    assert res.restart_needed  # first run creates the data addon + media pool
    assert res.cards == 3

    toc = os.path.join(res.data_dir, "AnkiCraft_Data.toc")
    assert "## Interface: 16001" in open(toc).read()
    data = load_lua_data(os.path.join(res.data_dir, "Cards.lua"))

    names = [d["name"] for d in data["decks"]]
    assert names == ["Other", "日本語"]
    jp = data["decks"][1]
    assert jp["new"] == 2 and len(jp["cards"]) == 2
    card = data["cards"][jp["cards"][0]]
    assert card["q"].startswith("|cffffd100猫|r 猫")
    assert card["a"] == "cat || 'quote' \"dq\""
    assert card["kind"] == 0 and card["reps"] == 0
    assert len(card["ivl"]) == 4 and all("⁨" not in s for s in card["ivl"])
    assert {"name": "Basic", "fields": ["Front", "Back"]} in data["noteTypes"]
    assert any(d["name"] == "日本語::Sub" for d in data["addDecks"])

    # second export: no restart needed
    assert not b.export(col).restart_needed


def test_export_chunks_many_cards(col, wow):
    for i in range(exporter.CARDS_PER_CHUNK * 2 + 7):
        add_basic(col, "Big", f"front {i}")
    conf = col.decks.config_dict_for_deck_id(col.decks.id("Big"))
    conf["new"]["perDay"] = 1000
    conf["rev"]["perDay"] = 1000
    col.decks.update_config(conf)
    b = make_bridge(wow)
    b.cfg["max_cards_per_deck"] = 1000
    res = b.export(col)
    data = load_lua_data(os.path.join(res.data_dir, "Cards.lua"))
    assert len(data["cards"]) == exporter.CARDS_PER_CHUNK * 2 + 7


def test_export_media(col, wow, tmp_path):
    from PyQt6.QtGui import QColor, QGuiApplication, QImage

    QGuiApplication.instance() or QGuiApplication([])
    img = QImage(10, 10, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 255, 0))
    src = tmp_path / "g.png"
    img.save(str(src))
    col.media.add_file(str(src))
    snd = tmp_path / "hello.mp3"
    snd.write_bytes(b"ID3")
    col.media.add_file(str(snd))
    add_basic(col, "M", 'pic <img src="g.png">', "say [sound:hello.mp3] [sound:missing.mp3]")
    res = make_bridge(wow).export(col)
    data = load_lua_data(os.path.join(res.data_dir, "Cards.lua"))
    card = next(iter(data["cards"].values()))
    assert card["qImg"] == [{"f": "i001.tga", "w": 10, "h": 10, "tw": 16, "th": 16}]
    assert card["aSnd"] == ["m001.mp3"]
    assert card["missingSnd"] == 1
    assert data["mediaPath"] == "Interface\\AddOns\\AnkiCraft_Data\\media\\"
    assert os.path.getsize(os.path.join(res.data_dir, "media", "m001.mp3")) == 3


def _first_card_id(col, deck):
    return col.find_cards(f'"deck:{deck}"')[0]


def test_import_answers_and_ops(col, wow):
    n1 = add_basic(col, "D", "one")
    n2 = add_basic(col, "D", "two")
    n3 = add_basic(col, "D", "three")
    c1, c2, c3 = (n.cards()[0].id for n in (n1, n2, n3))
    did = col.decks.id("D")
    now = time.time()
    at = int(now) - 3600
    db = {
        "installId": "inst-1",
        "nextSeq": 9,
        "pending": [
            {"seq": 1, "t": "answer", "cid": str(c1), "ease": 1, "at": at, "ms": 2500, "reps": 0},
            {"seq": 2, "t": "answer", "cid": str(c1), "ease": 3, "at": at + 30, "ms": 1500, "reps": 1},
            {"seq": 3, "t": "answer", "cid": str(c2), "ease": 4, "at": at + 40, "ms": 999999, "reps": 0},
            {"seq": 4, "t": "suspend", "cid": str(c3)},
            {"seq": 5, "t": "flag", "cid": str(c2), "flag": 1},
            {"seq": 6, "t": "mark", "cid": str(c2), "on": True},
            {"seq": 7, "t": "add", "deck": str(did), "notetype": "Basic",
             "fields": ["新しい", "atarashii\nnew"], "tags": "jp wow"},
            {"seq": 8, "t": "answer", "cid": "999999", "ease": 3, "at": at, "reps": 0},
        ],
    }
    sv = wow / "_forever_" / "WTF" / "Account" / "TESTACCOUNT" / "SavedVariables" / "AnkiCraft.lua"
    write_sv(sv, db)
    os.utime(sv, (now - 5, now - 5))

    b = make_bridge(wow)
    results, exp = b.full_sync(col)
    assert len(results) == 1
    r = results[0]
    assert (r.answered, r.added, r.changed, r.conflicts, r.errors) == (3, 1, 3, 1, [])

    card1 = col.get_card(c1)
    assert card1.reps == 2
    revlog = col.db.all(f"select id, ease, time from revlog where cid={c1} order by id")
    assert [x[1] for x in revlog] == [1, 3]
    assert abs(revlog[0][0] - at * 1000) < 1000  # timestamp = when answered in WoW
    assert revlog[0][2] == 2500
    card2 = col.get_card(c2)
    assert card2.reps == 1 and card2.type == 2  # easy -> review
    assert col.db.scalar(f"select time from revlog where cid={c2}") == importer.MAX_ANSWER_MS
    assert card2.user_flag() == 1 and card2.note().has_tag("marked")
    assert col.get_card(c3).queue == -1
    added = col.find_notes('"tag:AnkiCraft"')
    assert len(added) == 1
    note = col.get_note(added[0])
    assert note["Front"] == "新しい" and note["Back"] == "atarashii<br>new"
    assert set(note.tags) == {"jp", "wow", "AnkiCraft"}

    # ack exported for the addon
    data = load_lua_data(os.path.join(exp.data_dir, "Cards.lua"))
    assert data["ack"] == {"inst-1": 8}
    assert data["lastSync"]["answered"] == 3
    # suspended card is not exported
    assert str(c3) not in data["cards"]

    # idempotent: re-processing the same file changes nothing
    results2, _ = b.full_sync(col, force=True)
    assert results2 == []
    assert col.get_card(c1).reps == 2


def test_conflict_when_reviewed_elsewhere(col, wow):
    n = add_basic(col, "D", "one")
    cid = n.cards()[0].id
    col.sched.answerCard  # noqa: B018 - ensure attribute exists
    card = col.get_card(cid)
    card.start_timer()
    col.decks.select(col.decks.id("D"))
    qc = col.sched.get_queued_cards()
    ans = col.sched.build_answer(card=card, states=qc.cards[0].states, rating=CardAnswer.EASY)
    col.sched.answer_card(ans)  # reviewed on "the phone"
    res = importer.apply_ops(col, "x", [{"seq": 1, "t": "answer", "cid": str(cid), "ease": 1, "at": time.time(), "reps": 0}])
    assert res.conflicts == 1 and res.answered == 0
    assert importer.get_acks(col) == {"x": 1}


def test_undo_groups_sync(col):
    n = add_basic(col, "D", "one")
    cid = n.cards()[0].id
    pos = col.add_custom_undo_entry("AnkiCraft: sync from WoW")
    importer.apply_ops(col, "u", [
        {"seq": 1, "t": "answer", "cid": str(cid), "ease": 3, "at": time.time(), "reps": 0},
        {"seq": 2, "t": "flag", "cid": str(cid), "flag": 3},
    ])
    col.merge_undo_entries(pos)
    assert col.undo_status().undo == "AnkiCraft: sync from WoW"
    col.undo()
    c = col.get_card(cid)
    assert c.reps == 0 and c.user_flag() == 0


def test_truncated_deck_is_flagged(col, wow):
    for i in range(12):
        add_basic(col, "Big", f"card {i}")
    add_basic(col, "Small", "only one")
    b = make_bridge(wow)
    b.cfg["max_cards_per_deck"] = 5
    data = load_lua_data(os.path.join(b.export(col).data_dir, "Cards.lua"))
    decks = {d["name"]: d for d in data["decks"]}
    assert len(decks["Big"]["cards"]) == 5 and decks["Big"]["truncated"] is True
    assert "truncated" not in decks["Small"]
    # exactly at the limit is not truncated
    b.cfg["max_cards_per_deck"] = 12
    data = load_lua_data(os.path.join(b.export(col).data_dir, "Cards.lua"))
    assert "truncated" not in {d["name"]: d for d in data["decks"]}["Big"]


def test_old_default_limits_are_upgraded():
    from ankicraft_bridge.bridge import merged_config

    old = merged_config({"max_cards_per_deck": 300, "max_total_cards": 2000, "decks": ["X"]})
    assert (old["max_cards_per_deck"], old["max_total_cards"]) == (1000, 5000)
    assert old["decks"] == ["X"]
    custom = merged_config({"max_cards_per_deck": 300, "max_total_cards": 3000})
    assert (custom["max_cards_per_deck"], custom["max_total_cards"]) == (300, 3000)
