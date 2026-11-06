"""Build the bundled Japanese font for the WoW addon.

usage: python tools/build_font.py <NotoSansJP[wght].ttf> <out.ttf>

Source: https://github.com/google/fonts/tree/main/ofl/notosansjp (SIL OFL 1.1)
Steps: pin the variable font to Regular (wght=400) as a static TrueType
font, then keep only the characters useful in WoW cards: Latin, Japanese
punctuation, kana and every kanji in JIS X 0208 + Microsoft extensions
(cp932, ~6,800 kanji covering all Joyo and Jinmeiyo kanji).
"""

import sys

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

RANGES = [
    (0x0020, 0x007E),  # ASCII
    (0x00A0, 0x024F),  # Latin-1, Latin Extended-A/B
    (0x0300, 0x036F),  # combining diacritics
    (0x0370, 0x03FF),  # Greek
    (0x0400, 0x04FF),  # Cyrillic
    (0x2000, 0x206F),  # general punctuation
    (0x2070, 0x209F),  # super/subscripts
    (0x20A0, 0x20CF),  # currency
    (0x2100, 0x214F),  # letterlike
    (0x2150, 0x218F),  # number forms
    (0x2190, 0x21FF),  # arrows
    (0x2200, 0x22FF),  # math operators
    (0x2460, 0x24FF),  # enclosed alphanumerics ①
    (0x2500, 0x257F),  # box drawing
    (0x25A0, 0x25FF),  # geometric shapes ■▲●
    (0x2600, 0x26FF),  # misc symbols ★
    (0x3000, 0x303F),  # CJK symbols and punctuation
    (0x3040, 0x309F),  # hiragana
    (0x30A0, 0x30FF),  # katakana
    (0x31F0, 0x31FF),  # katakana phonetic extensions
    (0x3200, 0x32FF),  # enclosed CJK
    (0x3300, 0x33FF),  # CJK compatibility ㌔
    (0xFF00, 0xFFEF),  # half/full-width forms
]
# Joyo kanji added in 2010 that are outside JIS X 0208
EXTRA = "𠮟塡剝頰叱填剥頬"


def codepoints() -> set[int]:
    cps: set[int] = set()
    for lo, hi in RANGES:
        cps.update(range(lo, hi + 1))
    for cp in range(0x4E00, 0xA000):
        try:
            chr(cp).encode("cp932")
            cps.add(cp)
        except UnicodeEncodeError:
            pass
    for cp in range(0xF900, 0xFB00):  # CJK compatibility ideographs in cp932
        try:
            chr(cp).encode("cp932")
            cps.add(cp)
        except UnicodeEncodeError:
            pass
    cps.update(ord(c) for c in EXTRA)
    return cps


def main(src: str, dst: str) -> None:
    font = TTFont(src)
    if "fvar" in font:
        font = instancer.instantiateVariableFont(font, {"wght": 400}, updateFontNames=True)
    options = subset.Options()
    options.layout_features = ["kern", "palt", "vert", "ccmp", "locl"]
    options.name_IDs = ["*"]
    options.name_languages = ["*"]
    options.notdef_outline = True
    options.recalc_bounds = True
    options.drop_tables += ["BASE", "STAT", "MVAR", "HVAR", "VVAR"]
    sub = subset.Subsetter(options)
    sub.populate(unicodes=sorted(codepoints()))
    sub.subset(font)
    font.save(dst)
    cmap = font.getBestCmap()
    print(f"wrote {dst}: {len(cmap)} characters, {len(font.getGlyphOrder())} glyphs")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
