"""Windows-specific behaviour, simulated so it can run on any OS:
file locking (WinError 32), registry / Battle.net folder detection,
backslash paths and half-written SavedVariables."""

import json
import os
import sys
import time
import types

import pytest

from ankicraft_bridge import fsutil, wowpaths
from ankicraft_bridge.bridge import Bridge
from conftest import add_basic


def sharing_violation():
    e = PermissionError(13, "The process cannot access the file because it is being used by another process")
    e.winerror = 32
    return e


def flaky_replace(monkeypatch, failures):
    real = os.replace
    calls = {"n": 0}

    def fake(src, dst):
        calls["n"] += 1
        if calls["n"] <= failures:
            raise sharing_violation()
        return real(src, dst)

    monkeypatch.setattr(fsutil.os, "replace", fake)
    return calls


def test_replace_retries_while_locked(tmp_path, monkeypatch):
    calls = flaky_replace(monkeypatch, failures=3)
    target = tmp_path / "Cards.lua"
    target.write_text("old")
    fsutil.write_atomic(str(target), "new")
    assert target.read_text() == "new"
    assert calls["n"] == 4
    assert [p.name for p in tmp_path.iterdir()] == ["Cards.lua"]  # temp file cleaned up


def test_replace_gives_up_and_cleans_up(tmp_path, monkeypatch):
    flaky_replace(monkeypatch, failures=10**6)
    target = tmp_path / "Cards.lua"
    target.write_text("old")
    with pytest.raises(PermissionError):
        fsutil.write_atomic(str(target), "new", timeout=0.3)
    assert target.read_text() == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["Cards.lua"]


def test_non_lock_errors_are_not_retried(tmp_path, monkeypatch):
    def fake(src, dst):
        raise FileNotFoundError(2, "gone")

    monkeypatch.setattr(fsutil.os, "replace", fake)
    start = time.monotonic()
    with pytest.raises(FileNotFoundError):
        fsutil.write_atomic(str(tmp_path / "x"), "data", timeout=5)
    assert time.monotonic() - start < 1


def test_read_bytes_retries(tmp_path, monkeypatch):
    f = tmp_path / "AnkiCraft.lua"
    f.write_text("AnkiCraftDB = {}")
    real_open = open
    calls = {"n": 0}

    def fake_open(path, mode="r", *a, **kw):
        if str(path) == str(f):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise sharing_violation()
        return real_open(path, mode, *a, **kw)

    monkeypatch.setattr("builtins.open", fake_open)
    assert fsutil.read_bytes(str(f)) == b"AnkiCraftDB = {}"
    assert calls["n"] == 3


def test_export_survives_locked_cards_file(col, wow, monkeypatch):
    add_basic(col, "D", "x")
    b = Bridge({"wow_path": str(wow), "media": False}, log=lambda *_: None)
    b.export(col)
    flaky_replace(monkeypatch, failures=2)
    res = b.export(col)
    assert res.cards == 1


def test_export_permission_error_is_explained(col, wow, monkeypatch):
    add_basic(col, "D", "x")
    b = Bridge({"wow_path": str(wow), "media": False}, log=lambda *_: None)
    monkeypatch.setattr(fsutil, "replace", lambda s, d, timeout=3.0: (_ for _ in ()).throw(sharing_violation()))
    with pytest.raises(PermissionError, match="Can't write to"):
        b.export(col)


def test_strip_flavor_windows_paths():
    s = wowpaths._strip_flavor
    assert s("C:\\Program Files (x86)\\World of Warcraft\\_retail_\\") == "C:\\Program Files (x86)\\World of Warcraft"
    assert s('"D:\\Games\\World of Warcraft\\_forever_"') == "D:\\Games\\World of Warcraft"
    assert s("D:\\Games\\World of Warcraft") == "D:\\Games\\World of Warcraft"
    assert s("/Applications/World of Warcraft/_classic_era_/") == "/Applications/World of Warcraft"


def test_battlenet_config(tmp_path):
    cfgdir = tmp_path / "Battle.net"
    cfgdir.mkdir()
    (cfgdir / "Battle.net.config").write_text(json.dumps({"Client": {"Install": {"DefaultInstallPath": "E:\\Blizzard"}}}))
    assert wowpaths._battlenet_config_roots(str(tmp_path)) == [os.path.join("E:\\Blizzard", "World of Warcraft")]
    (cfgdir / "Battle.net.config").write_text("{not json")
    assert wowpaths._battlenet_config_roots(str(tmp_path)) == []
    assert wowpaths._battlenet_config_roots(str(tmp_path / "missing")) == []


def test_registry_detection_on_windows(monkeypatch, wow, tmp_path):
    fake = types.ModuleType("winreg")
    fake.HKEY_LOCAL_MACHINE, fake.HKEY_CURRENT_USER = 1, 2
    install = str(wow / "_retail_") + os.sep

    class Key:
        def __init__(self, hive, path):
            if hive != 1 or "WOW6432Node" not in path:
                raise FileNotFoundError(path)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    fake.OpenKey = Key
    fake.QueryValueEx = lambda key, name: (install, 1)
    monkeypatch.setitem(sys.modules, "winreg", fake)
    monkeypatch.setattr(wowpaths.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    roots = wowpaths.candidate_roots()
    assert roots[0] == str(wow)
    assert wowpaths.detect_root() == str(wow)


def test_normalize_root_accepts_subfolders(wow):
    for picked in (
        wow,
        wow / "_forever_",
        wow / "_forever_" / "Interface" / "AddOns",
        wow / "_forever_" / "WTF",
    ):
        assert wowpaths.normalize_root(str(picked)) == str(wow)
    b = Bridge({"wow_path": str(wow / "_forever_" / "Interface")}, log=lambda *_: None)
    assert b.root() == str(wow)
    assert b.addons_dir() == str(wow / "_forever_" / "Interface" / "AddOns")


def test_half_written_savedvariables_are_retried(col, wow):
    n = add_basic(col, "D", "x")
    cid = n.cards()[0].id
    sv = wow / "_forever_" / "WTF" / "Account" / "TESTACCOUNT" / "SavedVariables" / "AnkiCraft.lua"
    sv.write_text('AnkiCraftDB = { ["installId"] = "w", ["pending"] = { { ["seq"] = 1, ')
    old = time.time() - 10
    os.utime(sv, (old, old))
    logs = []
    b = Bridge({"wow_path": str(wow), "media": False}, log=logs.append)
    results, _ = b.full_sync(col)
    assert results == [] and logs == []  # not reported yet, will retry
    assert b.changed_sv_files() == [str(sv)]  # still pending
    # WoW finishes writing
    sv.write_text(
        'AnkiCraftDB = { ["installId"] = "w", ["pending"] = { { ["seq"] = 1, ["t"] = "answer", '
        f'["cid"] = "{cid}", ["ease"] = 3, ["at"] = {int(time.time())}, ["reps"] = 0 }} }} }}\r\n'
    )
    os.utime(sv, (old + 1, old + 1))
    results, _ = b.full_sync(col)
    assert results[0].answered == 1


def test_corrupt_savedvariables_give_up_after_retries(col, wow):
    sv = wow / "_forever_" / "WTF" / "Account" / "TESTACCOUNT" / "SavedVariables" / "AnkiCraft.lua"
    sv.write_text("AnkiCraftDB = {{{")
    old = time.time() - 10
    os.utime(sv, (old, old))
    logs = []
    b = Bridge({"wow_path": str(wow), "media": False}, log=logs.append)
    for _ in range(Bridge.MAX_READ_ATTEMPTS):
        b.full_sync(col)
    assert len(logs) == 1 and "Could not read" in logs[0]
    assert b.changed_sv_files() == []


def test_crlf_and_bom_savedvariables(col, wow):
    n = add_basic(col, "D", "x")
    cid = n.cards()[0].id
    sv = wow / "_forever_" / "WTF" / "Account" / "TESTACCOUNT" / "SavedVariables" / "AnkiCraft.lua"
    text = (
        '\r\nAnkiCraftDB = {\r\n["installId"] = "crlf",\r\n["pending"] = {\r\n{\r\n["seq"] = 1,\r\n'
        f'["t"] = "answer",\r\n["cid"] = "{cid}",\r\n["ease"] = 3,\r\n["reps"] = 0,\r\n'
        '}, -- [1]\r\n},\r\n}\r\n'
    )
    sv.write_bytes(b"\xef\xbb\xbf" + text.encode())
    old = time.time() - 10
    os.utime(sv, (old, old))
    results, _ = Bridge({"wow_path": str(wow), "media": False}, log=lambda *_: None).full_sync(col)
    assert results[0].answered == 1
