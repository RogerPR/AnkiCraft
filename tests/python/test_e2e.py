"""Full loop: Anki export -> real addon Lua code reviews cards -> WoW-style
SavedVariables -> bridge import into Anki -> re-export with ack -> addon
prunes acknowledged ops."""

import os
import shutil
import subprocess
import time

import pytest

from ankicraft_bridge.bridge import Bridge
from conftest import ROOT, add_basic

LUAJIT = shutil.which("luajit")
RUN = os.path.join(ROOT, "tests", "lua", "run.lua")


@pytest.mark.skipif(not LUAJIT, reason="luajit not installed")
def test_full_sync_loop(col, wow):
    for word in ("猫", "犬", "鳥"):
        add_basic(col, "日本語", f"<ruby>{word}<rt>x</rt></ruby>", "meaning")
    bridge = Bridge({"wow_path": str(wow), "flavor": "_forever_", "media": False}, log=lambda *_: None)
    exp = bridge.export(col)
    cards_lua = os.path.join(exp.data_dir, "Cards.lua")
    sv = wow / "_forever_" / "WTF" / "Account" / "TESTACCOUNT" / "SavedVariables" / "AnkiCraft.lua"

    # play a WoW session: Again on the first card, Good on the rest, add a note
    out = subprocess.run([LUAJIT, RUN, "e2e", cards_lua, "", str(sv)], capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0, out.stderr + out.stdout
    assert "pending=5" in out.stdout  # 4 answers (one card twice) + 1 add
    old = time.time() - 5
    os.utime(sv, (old, old))

    results, exp2 = bridge.full_sync(col)
    assert len(results) == 1
    r = results[0]
    assert (r.answered, r.added, r.conflicts, r.errors) == (4, 1, 0, [])
    reps = sorted(col.db.list("select reps from cards where nid in (select id from notes where tags not like '%AnkiCraft%')"))
    assert reps == [1, 1, 2]
    assert len(col.find_notes('"tag:AnkiCraft" "tag:wow"')) == 1

    # next WoW reload sees the ack and drops everything it had pending
    out = subprocess.run([LUAJIT, RUN, "e2e", cards_lua, str(sv), str(sv)], capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0, out.stderr + out.stdout
    # learning cards due now may be exported again and answered; the add op is new
    pending_line = out.stdout.strip().splitlines()[-1]
    pending = int(pending_line.split("pending=")[1])
    sv_text = sv.read_text(encoding="utf-8")
    assert '"seq"] = 1,' not in sv_text and '["seq"] = 5,' not in sv_text
    assert pending >= 1
    # and the bridge applies only the new ops
    os.utime(sv, (old + 1, old + 1))
    results2, _ = bridge.full_sync(col)
    assert results2 and results2[0].added == 1 and results2[0].errors == []
