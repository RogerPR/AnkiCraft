"""Tiny Lua-literal serializer and SavedVariables parser.

Only the subset WoW writes to SavedVariables is supported: tables, strings,
numbers, booleans and nil, with ``-- comments``. No Anki/Qt imports here so it
can be unit-tested standalone.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------- serializing

_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\n": "\\n",
    "\r": "\\r",
    "\0": "\\0",
    "\t": "\\t",
}
_ESC_RE = re.compile(r'[\\"\n\r\0\t]')
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LUA_KEYWORDS = {
    "and", "break", "do", "else", "elseif", "end", "false", "for", "function",
    "if", "in", "local", "nil", "not", "or", "repeat", "return", "then", "true",
    "until", "while",
}


def quote(s: str) -> str:
    return '"' + _ESC_RE.sub(lambda m: _ESCAPES[m.group(0)], s) + '"'


def _key(k: Any) -> str:
    if isinstance(k, str):
        if _IDENT_RE.match(k) and k not in _LUA_KEYWORDS:
            return k
        return "[" + quote(k) + "]"
    if isinstance(k, bool):
        return "[" + ("true" if k else "false") + "]"
    if isinstance(k, (int, float)):
        return "[" + _num(k) + "]"
    raise TypeError(f"unsupported Lua key type: {type(k)!r}")


def _num(v: int | float) -> str:
    if isinstance(v, int):
        return str(v)
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError("NaN/inf not representable")
    if v.is_integer() and abs(v) < 2**53:
        return str(int(v))
    return repr(v)


def dumps(v: Any) -> str:
    """Serialize a Python value as a compact Lua literal."""
    out: list[str] = []
    _dump(v, out)
    return "".join(out)


def _dump(v: Any, out: list[str]) -> None:
    if v is None:
        out.append("nil")
    elif v is True:
        out.append("true")
    elif v is False:
        out.append("false")
    elif isinstance(v, (int, float)):
        out.append(_num(v))
    elif isinstance(v, str):
        out.append(quote(v))
    elif isinstance(v, (list, tuple)):
        out.append("{")
        for item in v:
            _dump(item, out)
            out.append(",")
        out.append("}")
    elif isinstance(v, dict):
        out.append("{")
        for k, item in v.items():
            if item is None:
                continue
            out.append(_key(k))
            out.append("=")
            _dump(item, out)
            out.append(",")
        out.append("}")
    else:
        raise TypeError(f"unsupported Lua value type: {type(v)!r}")


# -------------------------------------------------------------------- parsing


class LuaParseError(ValueError):
    pass


_NUM_RE = re.compile(rb"-?(?:0[xX][0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)")
_NAME_RE = re.compile(rb"[A-Za-z_][A-Za-z0-9_]*")
_SIMPLE_ESC = {
    ord("n"): b"\n", ord("t"): b"\t", ord("r"): b"\r", ord("a"): b"\a",
    ord("b"): b"\b", ord("f"): b"\f", ord("v"): b"\v", ord("\\"): b"\\",
    ord('"'): b'"', ord("'"): b"'", ord("\n"): b"\n",
}


class _Parser:
    def __init__(self, data: bytes):
        self.s = data
        self.i = 0
        self.n = len(data)

    def error(self, msg: str) -> LuaParseError:
        line = self.s.count(b"\n", 0, self.i) + 1
        return LuaParseError(f"{msg} at line {line}")

    def skip(self) -> None:
        s, n = self.s, self.n
        while self.i < n:
            c = s[self.i]
            if c in b" \t\r\n\f\v":
                self.i += 1
            elif s.startswith(b"--", self.i):
                if s.startswith(b"--[[", self.i):
                    end = s.find(b"]]", self.i)
                    self.i = n if end < 0 else end + 2
                else:
                    end = s.find(b"\n", self.i)
                    self.i = n if end < 0 else end + 1
            elif c == 0xEF and s.startswith(b"\xef\xbb\xbf", self.i):  # BOM
                self.i += 3
            else:
                break

    def peek(self) -> int | None:
        self.skip()
        return self.s[self.i] if self.i < self.n else None

    def expect(self, ch: bytes) -> None:
        self.skip()
        if not self.s.startswith(ch, self.i):
            raise self.error(f"expected {ch.decode()!r}")
        self.i += len(ch)

    def parse_assignments(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        while True:
            self.skip()
            if self.i >= self.n:
                return result
            m = _NAME_RE.match(self.s, self.i)
            if not m:
                raise self.error("expected variable name")
            name = m.group(0).decode()
            self.i = m.end()
            self.expect(b"=")
            result[name] = self.value()

    def value(self) -> Any:
        c = self.peek()
        if c is None:
            raise self.error("unexpected end of input")
        if c == ord("{"):
            return self.table()
        if c in (ord('"'), ord("'")):
            return self.string()
        if self.s.startswith(b"[[", self.i) or self.s.startswith(b"[=", self.i):
            return self.long_string()
        m = _NUM_RE.match(self.s, self.i)
        if m and (c in b"-.0123456789"):
            self.i = m.end()
            txt = m.group(0).decode()
            if "x" in txt.lower():
                return int(txt, 16)
            if any(ch in txt for ch in ".eE"):
                f = float(txt)
                return int(f) if f.is_integer() and abs(f) < 2**53 else f
            return int(txt)
        m = _NAME_RE.match(self.s, self.i)
        if m:
            word = m.group(0)
            self.i = m.end()
            if word == b"true":
                return True
            if word == b"false":
                return False
            if word == b"nil":
                return None
            if word in (b"inf",):
                return float("inf")
            if word in (b"nan",):
                return float("nan")
            raise self.error(f"unexpected word {word.decode()!r}")
        raise self.error(f"unexpected character {chr(c)!r}")

    def string(self) -> str:
        q = self.s[self.i]
        self.i += 1
        buf = bytearray()
        s = self.s
        while True:
            if self.i >= self.n:
                raise self.error("unterminated string")
            c = s[self.i]
            if c == q:
                self.i += 1
                return buf.decode("utf-8", errors="replace")
            if c == ord("\\"):
                self.i += 1
                e = s[self.i]
                if e in _SIMPLE_ESC:
                    buf += _SIMPLE_ESC[e]
                    self.i += 1
                elif e == ord("\r"):
                    buf += b"\n"
                    self.i += 1
                    if self.i < self.n and s[self.i] == ord("\n"):
                        self.i += 1
                elif 48 <= e <= 57:
                    j = self.i
                    while j < self.n and j - self.i < 3 and 48 <= s[j] <= 57:
                        j += 1
                    buf.append(int(s[self.i:j]) & 0xFF)
                    self.i = j
                else:
                    buf.append(e)
                    self.i += 1
            else:
                buf.append(c)
                self.i += 1

    def long_string(self) -> str:
        m = re.compile(rb"\[(=*)\[").match(self.s, self.i)
        if not m:
            raise self.error("bad long string")
        close = b"]" + m.group(1) + b"]"
        start = m.end()
        if self.s.startswith(b"\n", start):
            start += 1
        end = self.s.find(close, start)
        if end < 0:
            raise self.error("unterminated long string")
        self.i = end + len(close)
        return self.s[start:end].decode("utf-8", errors="replace")

    def table(self) -> Any:
        self.expect(b"{")
        arr: list[Any] = []
        keyed: dict[Any, Any] = {}
        while True:
            c = self.peek()
            if c == ord("}"):
                self.i += 1
                break
            if c == ord("[") and not (
                self.s.startswith(b"[[", self.i) or self.s.startswith(b"[=", self.i)
            ):
                self.i += 1
                k = self.value()
                self.expect(b"]")
                self.expect(b"=")
                keyed[k] = self.value()
            else:
                m = _NAME_RE.match(self.s, self.i)
                after = None
                if m and m.group(0) not in (b"true", b"false", b"nil"):
                    j = m.end()
                    while j < self.n and self.s[j] in b" \t\r\n":
                        j += 1
                    after = self.s[j : j + 1]
                if m and after == b"=" and self.s[j : j + 2] != b"==":
                    self.i = j + 1
                    keyed[m.group(0).decode()] = self.value()
                else:
                    arr.append(self.value())
            c = self.peek()
            if c in (ord(","), ord(";")):
                self.i += 1
            elif c != ord("}"):
                raise self.error("expected ',' or '}'")
        if not keyed:
            return arr
        for idx, item in enumerate(arr, start=1):
            keyed[idx] = item
        # A table that only has consecutive integer keys from 1 is a list.
        if keyed and all(isinstance(k, int) and not isinstance(k, bool) for k in keyed):
            n = len(keyed)
            if set(keyed) == set(range(1, n + 1)):
                return [keyed[i] for i in range(1, n + 1)]
        return {k: v for k, v in keyed.items() if v is not None}


def parse_assignments(data: bytes | str) -> dict[str, Any]:
    """Parse a SavedVariables file: a sequence of ``Name = value`` lines."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return _Parser(data).parse_assignments()


def parse_value(data: bytes | str) -> Any:
    if isinstance(data, str):
        data = data.encode("utf-8")
    p = _Parser(data)
    v = p.value()
    p.skip()
    if p.i != p.n:
        raise p.error("trailing data")
    return v


def as_list(v: Any) -> list[Any]:
    """Coerce a parsed Lua table into a list (sparse arrays become ordered)."""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, dict):
        ints = sorted(k for k in v if isinstance(k, int) and not isinstance(k, bool))
        return [v[k] for k in ints]
    return [v]
