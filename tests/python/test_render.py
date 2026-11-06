from ankicraft_bridge.render import (
    BOLD,
    CLOZE,
    READING,
    html_to_wow,
    plain_to_html,
    resolve_audio,
    split_answer,
)


def test_basic_blocks_and_entities():
    r = html_to_wow("<div>one</div><div>two&nbsp;&amp; three</div>line<br>next")
    assert r.text == "one\ntwo & three\nline\nnext"


def test_style_removed():
    r = html_to_wow("<style>.card{color:red}</style><script>x()</script>Hello")
    assert r.text == "Hello"


def test_bold_and_nested_colors():
    r = html_to_wow("a <b>bold <i>it</i> more</b> z")
    assert r.text == f"a |cff{BOLD}bold |cffa8d8ffit|r|cff{BOLD} more|r z"


def test_pipe_is_escaped():
    assert html_to_wow("a|b").text == "a||b"


def test_furigana_styles():
    html = "<ruby>漢字<rt>かんじ</rt></ruby>を<ruby>読<rp>(</rp><rt>よ</rt><rp>)</rp></ruby>む"
    assert html_to_wow(html, "brackets").text == f"漢字|cff{READING}[かんじ]|rを読|cff{READING}[よ]|rむ"
    assert html_to_wow(html, "kanji").text == "漢字を読む"
    assert html_to_wow(html, "kana").text == "かんじをよむ"


def test_cloze_highlight():
    r = html_to_wow('The <span class="cloze" data-cloze="x">[...]</span> sat')
    assert r.text == f"The |cff{CLOZE}[...]|r sat"


def test_inline_color_dark_is_lightened():
    r = html_to_wow('<span style="color: rgb(0, 0, 0);">dark</span><font color="#ff0000">red</font>')
    assert r.text == "|cffffffffdark|r|cffff0000red|r"


def test_images_and_audio_extracted():
    r = html_to_wow('x <img src="pic%20one.png"> [anki:play:q:0] [anki:play:a:1] <img src="https://e.com/a.png">')
    assert r.images == ["pic one.png"]
    assert r.audio == [("q", 0), ("a", 1)]
    assert r.text == "x"


def test_split_answer():
    a, full = split_answer("<style>s</style>Q<hr id=answer>A")
    assert not full and a == "<style>s</style>A"
    a, full = split_answer("only answer")
    assert full and a == "only answer"


def test_resolve_audio():
    class T:
        def __init__(self, f):
            self.filename = f

    class TTS:
        pass

    files = resolve_audio([("q", 0), ("a", 0), ("a", 5), ("q", 1), ("file", "z.ogg")], [T("q.mp3"), TTS()], [T("a.mp3")])
    assert files == ["q.mp3", "a.mp3", "z.ogg"]


def test_plain_to_html():
    assert plain_to_html("a < b\nc || d") == "a &lt; b<br>c | d"
