import os

from PyQt6.QtGui import QColor, QGuiApplication, QImage

from ankicraft_bridge.media import MediaPool, next_pow2, read_tga_header

_app = QGuiApplication.instance() or QGuiApplication([])


def _make_png(path, w, h, color):
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor(*color))
    assert img.save(str(path))


def test_next_pow2():
    assert [next_pow2(x) for x in (1, 2, 3, 300, 512, 513)] == [2, 2, 4, 512, 512, 1024]


def test_pool_creation_and_image_conversion(tmp_path):
    media_dir = tmp_path / "collection.media"
    media_dir.mkdir()
    _make_png(media_dir / "red.png", 300, 200, (255, 0, 0, 255))
    _make_png(media_dir / "huge.png", 2000, 1000, (0, 0, 255, 128))
    (media_dir / "word.mp3").write_bytes(b"ID3fake")
    (media_dir / "clip.wav").write_bytes(b"RIFF")

    pool = MediaPool(str(tmp_path / "pool"), img_slots=3, audio_slots=2, max_image=512)
    assert pool.ensure_pool() == 3 + 2 + 2
    assert pool.ensure_pool() == 0

    res = pool.assign(
        [("img", "red.png"), ("img", "huge.png"), ("img", "missing.png"), ("audio", "word.mp3"), ("audio", "clip.wav")],
        str(media_dir),
    )
    red = res[("img", "red.png")]
    assert (red.w, red.h, red.tw, red.th) == (300, 200, 512, 256)
    huge = res[("img", "huge.png")]
    assert (huge.w, huge.h, huge.tw, huge.th) == (512, 256, 512, 256)
    assert ("img", "missing.png") not in res
    assert ("audio", "clip.wav") not in res  # unsupported format
    assert res[("audio", "word.mp3")].file == "m001.mp3"

    # the TGA is readable, has the right header and a red top-left pixel
    tga = os.path.join(pool.root, red.file)
    assert read_tga_header(tga) == (2, 512, 256, 32)
    back = QImage(tga)
    if not back.isNull():  # Qt's TGA plugin is optional
        assert back.pixelColor(0, 0).red() == 255
        assert back.pixelColor(400, 0).alpha() == 0  # padding is transparent
    with open(tga, "rb") as f:
        raw = f.read()
    # bottom-left origin: first stored row is the image's last row (padding),
    # top-left pixel of the image lives in the last stored row.
    last_row = raw[18 + 255 * 512 * 4 : 18 + 255 * 512 * 4 + 4]
    assert last_row == bytes([0, 0, 255, 255])  # B, G, R, A

    # stable: same files keep their slots and are not rewritten
    mtime = os.path.getmtime(tga)
    res2 = pool.assign([("img", "red.png")], str(media_dir))
    assert res2[("img", "red.png")].file == red.file
    assert os.path.getmtime(tga) == mtime


def test_pool_recycles_lru(tmp_path):
    media_dir = tmp_path / "m"
    media_dir.mkdir()
    for i in range(4):
        _make_png(media_dir / f"{i}.png", 4, 4, (i * 50, 0, 0, 255))
    pool = MediaPool(str(tmp_path / "pool"), img_slots=2, audio_slots=0)
    pool.ensure_pool()
    a = pool.assign([("img", "0.png"), ("img", "1.png")], str(media_dir))
    b = pool.assign([("img", "2.png")], str(media_dir))
    assert b[("img", "2.png")].file in {a[("img", "0.png")].file, a[("img", "1.png")].file}
    # pool overflow: only 2 slots, so the 3rd image in one export is dropped
    c = pool.assign([("img", "0.png"), ("img", "1.png"), ("img", "3.png")], str(media_dir))
    assert len(c) == 2
