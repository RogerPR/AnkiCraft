import pytest

from ankicraft_bridge import luaser

WOW_SV = rb'''
AnkiCraftDB = {
["installId"] = "abc-123",
["nextSeq"] = 4,
["pending"] = {
{
["seq"] = 1,
["t"] = "answer",
["cid"] = "1793958150233",
["ease"] = 3,
["at"] = 1793950000,
["ms"] = 4200,
["reps"] = 0,
}, -- [1]
{
["seq"] = 2,
["t"] = "add",
["fields"] = {
"\230\188\162\229\173\151 \"quoted\" back\\slash", -- [1]
"line1\nline2", -- [2]
},
["tags"] = "jp",
}, -- [2]
},
["settings"] = {
["fontSize"] = 18.5,
["autoTaxi"] = true,
["neg"] = -3,
["off"] = false,
},
}
OtherVar = nil
'''


def test_parse_wow_savedvariables():
    parsed = luaser.parse_assignments(WOW_SV)
    db = parsed["AnkiCraftDB"]
    assert db["installId"] == "abc-123"
    ops = db["pending"]
    assert isinstance(ops, list) and len(ops) == 2
    assert ops[0]["cid"] == "1793958150233"
    assert ops[1]["fields"][0] == '漢字 "quoted" back\\slash'
    assert ops[1]["fields"][1] == "line1\nline2"
    assert db["settings"] == {"fontSize": 18.5, "autoTaxi": True, "neg": -3, "off": False}
    assert parsed["OtherVar"] is None


def test_roundtrip():
    value = {
        "s": 'a"b\\c\nd|e 漢字',
        "list": [1, 2.5, True, False, "x"],
        "nested": {"end": 1, "with space": [{"a": 1}]},
        "big": 1793958150233,
        12: "int key",
    }
    text = luaser.dumps(value)
    assert luaser.parse_value(text) == value


def test_sparse_and_mixed_tables():
    assert luaser.parse_value("{[1]='a',[3]='c'}") == {1: "a", 3: "c"}
    assert luaser.as_list(luaser.parse_value("{[1]='a',[3]='c'}")) == ["a", "c"]
    assert luaser.parse_value("{}") == []
    assert luaser.parse_value("{ x = 1; 'a' }") == {"x": 1, 1: "a"}


def test_decimal_escape_and_long_string():
    assert luaser.parse_value(r'"\65\066\0679"') == "ABC9"
    assert luaser.parse_value("[[hello\nworld]]") == "hello\nworld"


def test_errors():
    with pytest.raises(luaser.LuaParseError):
        luaser.parse_value('{"unterminated')
    with pytest.raises(luaser.LuaParseError):
        luaser.parse_assignments("X = {1 2}")
