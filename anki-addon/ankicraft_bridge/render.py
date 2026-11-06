"""Convert rendered Anki card HTML into WoW FontString markup.

WoW can only show plain text with ``|cffRRGGBB...|r`` color codes, so this
flattens HTML: block elements become newlines, emphasis becomes colors, ruby
(furigana) becomes ``漢字[かんじ]``, images and sounds are pulled out as
separate media references. No Anki/Qt imports so it is unit-testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import unquote

BOLD = "ffd100"
ITALIC = "a8d8ff"
UNDERLINE = "ffffff"
CLOZE = "4fa3ff"
READING = "a0a0a0"

_NAMED_COLORS = {
    "black": "000000", "white": "ffffff", "red": "ff4040", "green": "40c040",
    "blue": "4080ff", "yellow": "ffff40", "orange": "ffa040", "purple": "c080ff",
    "gray": "a0a0a0", "grey": "a0a0a0", "pink": "ff80c0", "brown": "c08040",
    "cyan": "40ffff", "magenta": "ff40ff", "lime": "80ff40", "navy": "6070ff",
    "teal": "40c0c0", "maroon": "c04040", "olive": "c0c040", "silver": "c0c0c0",
}

_BLOCK = {
    "br", "div", "p", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "hr",
    "ul", "ol", "table", "center", "blockquote", "section", "article", "pre",
    "dt", "dd", "dl", "header", "footer", "figure", "figcaption",
}
_VOID = {"br", "img", "hr", "input", "meta", "link", "wbr", "source", "col", "area", "base", "embed", "track"}
_SKIP = {"style", "script", "head", "title", "rp", "template", "noscript", "button", "select", "textarea", "audio", "video", "svg", "math"}

_PLAY_RE = re.compile(r"\[anki:play:([qa]):(\d+)\]")
_SOUND_RE = re.compile(r"\[sound:([^\]]+)\]")
_ANSWER_HR_RE = re.compile(r"<hr[^>]*id\s*=\s*[\"']?answer[\"']?[^>]*>", re.I)
_COLOR_STYLE_RE = re.compile(r"(?:^|;)\s*color\s*:\s*([^;]+)", re.I)
_RGB_RE = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)")


def css_color_to_hex(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower().replace("!important", "").strip()
    if v.startswith("#"):
        h = v[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) >= 6 and all(c in "0123456789abcdef" for c in h[:6]):
            return h[:6]
        return None
    m = _RGB_RE.match(v)
    if m:
        return "".join(f"{min(255, int(x)):02x}" for x in m.groups())
    return _NAMED_COLORS.get(v)


def _readable(hexcolor: str) -> str:
    """Card colors are designed for white backgrounds; WoW's is dark.
    Lighten very dark colors so they stay legible."""
    r, g, b = (int(hexcolor[i : i + 2], 16) for i in (0, 2, 4))
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    if lum >= 60:
        return hexcolor
    if max(r, g, b) - min(r, g, b) < 60:  # black / dark gray -> white
        return "ffffff"
    return "".join(f"{min(255, int(c + (255 - c) * 0.5)):02x}" for c in (r, g, b))


@dataclass
class Rendered:
    text: str
    images: list[str] = field(default_factory=list)
    # audio tag references: ("q"|"a", index) for [anki:play] or ("file", name)
    audio: list[tuple[str, str | int]] = field(default_factory=list)


class _Html2Wow(HTMLParser):
    def __init__(self, furigana: str):
        super().__init__(convert_charrefs=True)
        self.furigana = furigana
        self.out: list[str] = []
        self.images: list[str] = []
        self.stack: list[tuple[str, str | None]] = []  # (tag, pushed color)
        self.colors: list[str] = []
        self.skip_depth = 0
        self.ruby_depth = 0
        self.in_rt = False
        self.ruby_base: list[str] = []
        self.ruby_reading: list[str] = []

    # -- helpers
    def _emit(self, text: str) -> None:
        if self.ruby_depth and not self.in_rt:
            self.ruby_base.append(text)
        elif self.in_rt:
            self.ruby_reading.append(text)
        else:
            self.out.append(text)

    def _newline(self, hard: bool = False) -> None:
        """Block boundaries add a newline only if not already at line start;
        <br> (hard) always adds one so <br><br> keeps a blank line."""
        if self.ruby_depth:
            return
        if not hard:
            for piece in reversed(self.out):
                if piece.startswith("|c") or piece == "|r":
                    continue
                if not piece.strip(" "):
                    continue
                if piece.endswith("\n"):
                    return
                break
            else:
                return  # nothing emitted yet
        self.out.append("\n")

    def _push_color(self, color: str) -> None:
        self.colors.append(color)
        self._emit(f"|cff{color}")

    def _pop_color(self) -> None:
        if self.colors:
            self.colors.pop()
        self._emit("|r")
        if self.colors:
            self._emit(f"|cff{self.colors[-1]}")

    def _flush_ruby_pair(self) -> None:
        base = "".join(self.ruby_base).strip()
        reading = "".join(self.ruby_reading).strip()
        self.ruby_base, self.ruby_reading = [], []
        saved_depth, self.ruby_depth = self.ruby_depth, 0
        if not reading:
            self._emit(base)
        elif self.furigana == "kana":
            self._emit(reading)
        elif self.furigana == "kanji":
            self._emit(base)
        else:
            self._emit(base)
            outer = self.colors[-1] if self.colors else None
            self._emit(f"|cff{READING}[{reading}]|r")
            if outer:
                self._emit(f"|cff{outer}")
        self.ruby_depth = saved_depth

    # -- parser callbacks
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag in _SKIP:
            if tag not in _VOID:
                self.skip_depth += 1
                self.stack.append((tag, None))
            return
        if self.skip_depth:
            if tag not in _VOID:
                self.stack.append((tag, None))
            return
        if tag == "img":
            src = a.get("src", "").strip()
            if src and not src.startswith(("data:", "http:", "https:")):
                self.images.append(unquote(src))
            return
        if tag == "ruby":
            self.ruby_depth += 1
            self.stack.append((tag, None))
            return
        if tag == "rt":
            if self.ruby_depth:
                self.in_rt = True
            self.stack.append((tag, None))
            return
        if tag in _BLOCK:
            self._newline(hard=(tag == "br"))
        if tag in _VOID:
            return

        color = None
        style_color = _COLOR_STYLE_RE.search(a.get("style", ""))
        classes = a.get("class", "").split()
        if "cloze" in classes:
            color = CLOZE
        elif style_color and css_color_to_hex(style_color.group(1)):
            color = _readable(css_color_to_hex(style_color.group(1)))  # type: ignore[arg-type]
        elif tag == "font" and css_color_to_hex(a.get("color")):
            color = _readable(css_color_to_hex(a.get("color")))  # type: ignore[arg-type]
        elif tag in ("b", "strong"):
            color = BOLD
        elif tag in ("i", "em"):
            color = ITALIC
        elif tag in ("u",):
            color = UNDERLINE
        elif tag in ("h1", "h2", "h3"):
            color = BOLD
        if color:
            self._push_color(color)
        self.stack.append((tag, color))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _VOID:
            return
        # find the matching open tag; ignore stray end tags
        idx = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                idx = i
                break
        if idx is None:
            return
        while len(self.stack) > idx:
            t, color = self.stack.pop()
            self._close(t, color)

    def _close(self, tag: str, color: str | None) -> None:
        if tag in _SKIP:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if tag == "rt":
            if self.in_rt:
                self.in_rt = False
                self._flush_ruby_pair()
            return
        if tag == "ruby":
            if self.ruby_base or self.ruby_reading:
                self._flush_ruby_pair()
            self.ruby_depth = max(0, self.ruby_depth - 1)
            return
        if color:
            self._pop_color()
        if tag in _BLOCK:
            self._newline()

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = re.sub(r"[ \t\r\n\f\xa0]+", " ", data).replace("|", "||")
        if text:
            self._emit(text)

    def result(self) -> str:
        if self.ruby_base or self.ruby_reading:
            self._flush_ruby_pair()
        while self.colors:
            self._pop_color()
        text = "".join(self.out)
        lines = [ln.strip() for ln in text.split("\n")]
        # remove color-only empty lines' effect on spacing
        text = "\n".join(lines)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip("\n ").strip()


def html_to_wow(html: str, furigana: str = "brackets") -> Rendered:
    audio: list[tuple[str, str | int]] = []

    def _play(m: re.Match[str]) -> str:
        audio.append((m.group(1), int(m.group(2))))
        return " "

    def _sound(m: re.Match[str]) -> str:
        audio.append(("file", m.group(1)))
        return " "

    html = _PLAY_RE.sub(_play, html)
    html = _SOUND_RE.sub(_sound, html)
    p = _Html2Wow(furigana)
    p.feed(html)
    p.close()
    return Rendered(text=p.result(), images=p.images, audio=audio)


def split_answer(answer_html: str) -> tuple[str, bool]:
    """Return (answer-only html, is_full). If the template has no
    ``<hr id=answer>`` the whole answer is returned and is_full is True."""
    m = _ANSWER_HR_RE.search(answer_html)
    if not m:
        return answer_html, True
    styles = "".join(re.findall(r"<style.*?</style>", answer_html[: m.start()], re.S | re.I))
    return styles + answer_html[m.end() :], False


def resolve_audio(refs: list[tuple[str, str | int]], q_tags: list, a_tags: list) -> list[str]:
    """Map audio refs to media filenames, using Anki AV tag lists."""
    files: list[str] = []
    for kind, val in refs:
        if kind == "file":
            name = str(val)
        else:
            tags = q_tags if kind == "q" else a_tags
            idx = int(val)
            if idx >= len(tags):
                continue
            name = getattr(tags[idx], "filename", None)  # TTSTag has no filename
            if not name:
                continue
        if name not in files:
            files.append(name)
    return files


def render_card(card, furigana: str = "brackets") -> dict:
    """Render an anki.cards.Card into the export dict fields."""
    q_html = card.question()
    a_html = card.answer()
    q_tags = card.question_av_tags()
    a_tags = card.answer_av_tags()
    q = html_to_wow(q_html, furigana)
    a_part, a_full = split_answer(a_html)
    a = html_to_wow(a_part, furigana)
    return {
        "q": q.text,
        "a": a.text,
        "aFull": a_full,
        "qImages": q.images,
        "aImages": a.images,
        "qAudio": resolve_audio(q.audio, q_tags, a_tags),
        "aAudio": resolve_audio(a.audio, q_tags, a_tags),
    }


def plain_to_html(text: str) -> str:
    """Convert text typed in WoW into note-field HTML."""
    import html as _html

    text = text.replace("||", "|")
    return _html.escape(text, quote=False).replace("\n", "<br>")
