import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "anki-addon"))


@pytest.fixture
def col():
    from anki.collection import Collection

    d = tempfile.mkdtemp()
    c = Collection(os.path.join(d, "collection.anki2"))
    yield c
    c.close()


@pytest.fixture
def wow(tmp_path):
    """A fake WoW install with the AnkiCraft addon in _forever_."""
    root = tmp_path / "World of Warcraft"
    addon = root / "_forever_" / "Interface" / "AddOns" / "AnkiCraft"
    addon.mkdir(parents=True)
    (addon / "AnkiCraft.toc").write_text("## Interface: 16001\n## Title: AnkiCraft\n")
    sv = root / "_forever_" / "WTF" / "Account" / "TESTACCOUNT" / "SavedVariables"
    sv.mkdir(parents=True)
    return root


def add_basic(col, deck, front, back="back"):
    m = col.models.by_name("Basic")
    did = col.decks.id(deck)
    n = col.new_note(m)
    n["Front"] = front
    n["Back"] = back
    col.add_note(n, did)
    return n
