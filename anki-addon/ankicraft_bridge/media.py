"""Media slot pool for WoW.

WoW only sees files that existed when the game client started, so we create
a fixed pool of placeholder files once (``i001.tga``, ``m001.mp3``,
``o001.ogg``...) and afterwards only overwrite their contents. Slots are
recycled least-recently-used first.
"""

from __future__ import annotations

import json
import os
import struct
import time
from dataclasses import dataclass

from . import fsutil

KINDS = {
    # kind: (prefix, extension)
    "img": ("i", ".tga"),
    "mp3": ("m", ".mp3"),
    "ogg": ("o", ".ogg"),
}
AUDIO_EXT = {".mp3": "mp3", ".ogg": "ogg"}
STATE_FILE = "slots.json"


def next_pow2(n: int) -> int:
    p = 1
    while p < n:
        p <<= 1
    return max(p, 2)


def write_tga(path: str, width: int, height: int, bgra_top_down: bytes) -> None:
    """Write an uncompressed 32-bit TGA (bottom-left origin, 8 alpha bits)."""
    assert len(bgra_top_down) == width * height * 4
    header = struct.pack(
        "<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, width, height, 32, 8
    )
    row = width * 4
    rows = [bgra_top_down[y * row : (y + 1) * row] for y in range(height - 1, -1, -1)]
    fsutil.write_atomic(path, header + b"".join(rows))


def read_tga_header(path: str) -> tuple[int, int, int, int]:
    with open(path, "rb") as f:
        h = f.read(18)
    _, _, itype, _, _, _, _, _, w, hgt, bpp, desc = struct.unpack("<BBBHHBHHHHBB", h)
    return itype, w, hgt, bpp


def convert_image(src: str, dst: str, max_size: int) -> tuple[int, int, int, int] | None:
    """Load any Qt-readable image, scale to fit max_size, pad to power-of-two
    and write as TGA. Returns (w, h, texture_w, texture_h) or None."""
    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QImage, QPainter
    except ImportError:  # pragma: no cover - always present inside Anki
        return None
    img = QImage(src)
    if img.isNull():
        return None
    w, h = img.width(), img.height()
    if w <= 0 or h <= 0:
        return None
    scale = min(1.0, max_size / max(w, h))
    if scale < 1.0:
        img = img.scaled(
            max(1, round(w * scale)),
            max(1, round(h * scale)),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        w, h = img.width(), img.height()
    tw, th = next_pow2(w), next_pow2(h)
    canvas = QImage(tw, th, QImage.Format.Format_ARGB32)
    canvas.fill(0)
    p = QPainter(canvas)
    p.drawImage(0, 0, img)
    p.end()
    # Format_ARGB32 is stored as 0xAARRGGBB words = B,G,R,A bytes on
    # little-endian machines (every platform WoW/Anki runs on).
    ptr = canvas.constBits()
    ptr.setsize(canvas.sizeInBytes())
    data = bytes(ptr)
    bpl = canvas.bytesPerLine()
    if bpl != tw * 4:
        data = b"".join(data[y * bpl : y * bpl + tw * 4] for y in range(th))
    write_tga(dst, tw, th, data)
    return w, h, tw, th


_PLACEHOLDER_TGA: bytes | None = None


def _placeholder_tga() -> bytes:
    global _PLACEHOLDER_TGA
    if _PLACEHOLDER_TGA is None:
        header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, 2, 2, 32, 8)
        _PLACEHOLDER_TGA = header + b"\0" * 16
    return _PLACEHOLDER_TGA


@dataclass
class SlotRef:
    file: str  # slot file name, e.g. "i003.tga"
    w: int = 0
    h: int = 0
    tw: int = 0
    th: int = 0


class MediaPool:
    def __init__(self, root: str, img_slots: int = 200, audio_slots: int = 200, max_image: int = 512):
        self.root = root
        self.sizes = {"img": img_slots, "mp3": audio_slots, "ogg": audio_slots}
        self.max_image = max_image
        self.state_path = os.path.join(root, STATE_FILE)
        self.state = self._load_state()

    # ------------------------------------------------------------ state
    def _load_state(self) -> dict:
        try:
            with open(self.state_path, encoding="utf-8") as f:
                st = json.load(f)
            if isinstance(st, dict):
                for k in KINDS:
                    st.setdefault(k, {})
                return st
        except (OSError, ValueError):
            pass
        return {k: {} for k in KINDS}

    def save(self) -> None:
        os.makedirs(self.root, exist_ok=True)
        fsutil.write_atomic(self.state_path, json.dumps(self.state))

    @staticmethod
    def slot_name(kind: str, n: int) -> str:
        prefix, ext = KINDS[kind]
        return f"{prefix}{n:03d}{ext}"

    def ensure_pool(self) -> int:
        """Create missing placeholder files. Returns how many were created
        (non-zero means WoW must be fully restarted to see them)."""
        os.makedirs(self.root, exist_ok=True)
        created = 0
        for kind, count in self.sizes.items():
            for n in range(1, count + 1):
                path = os.path.join(self.root, self.slot_name(kind, n))
                if not os.path.exists(path):
                    with open(path, "wb") as f:
                        if kind == "img":
                            f.write(_placeholder_tga())
                    created += 1
        return created

    def existing_slots(self, kind: str) -> list[str]:
        """Slots that exist on disk (bounded by configured size)."""
        names = []
        for n in range(1, self.sizes[kind] + 1):
            name = self.slot_name(kind, n)
            if os.path.exists(os.path.join(self.root, name)):
                names.append(name)
        return names

    # ------------------------------------------------------------ assign
    def assign(self, wanted: list[tuple[str, str]], media_dir: str) -> dict[tuple[str, str], SlotRef]:
        """Assign slots for (kind, filename) pairs; kind is "img" or "audio".
        Writes converted files when needed. Missing/unsupported media and
        overflow beyond the pool size are silently left out."""
        now = int(time.time())
        result: dict[tuple[str, str], SlotRef] = {}
        # resolve the concrete pool kind + source signature
        jobs: list[tuple[tuple[str, str], str, str, str]] = []  # (orig, pool_kind, src, sig)
        for kind, fname in wanted:
            if (kind, fname) in result or any(j[0] == (kind, fname) for j in jobs):
                continue
            src = os.path.join(media_dir, os.path.basename(fname))
            try:
                st = os.stat(src)
            except OSError:
                continue
            if kind == "img":
                pool_kind = "img"
            else:
                pool_kind = AUDIO_EXT.get(os.path.splitext(fname)[1].lower())
                if not pool_kind:
                    continue
            sig = f"{fname}|{int(st.st_mtime)}|{st.st_size}|{self.max_image if kind == 'img' else 0}"
            jobs.append(((kind, fname), pool_kind, src, sig))

        for pool_kind in KINDS:
            mine = [j for j in jobs if j[1] == pool_kind]
            if not mine:
                continue
            slots = self.state[pool_kind]
            available = self.existing_slots(pool_kind)
            by_sig = {info.get("sig"): name for name, info in slots.items() if name in available}
            needed_sigs = {j[3] for j in mine}
            # slots we may recycle: unused first, then LRU among slots not needed now
            free = [n for n in available if n not in slots]
            recyclable = sorted(
                (n for n in available if n in slots and slots[n].get("sig") not in needed_sigs),
                key=lambda n: slots[n].get("used", 0),
            )
            candidates = free + recyclable
            for orig, _, src, sig in mine:
                name = by_sig.get(sig)
                if name is None:
                    if not candidates:
                        continue
                    name = candidates.pop(0)
                    dst = os.path.join(self.root, name)
                    info: dict = {"sig": sig}
                    if pool_kind == "img":
                        try:
                            dims = convert_image(src, dst, self.max_image)
                        except Exception:
                            dims = None
                        if not dims:
                            continue
                        info.update(w=dims[0], h=dims[1], tw=dims[2], th=dims[3])
                    else:
                        try:
                            with open(src, "rb") as fi:
                                fsutil.write_atomic(dst, fi.read())
                        except OSError:
                            continue
                    slots[name] = info
                    by_sig[sig] = name
                info = slots[name]
                info["used"] = now
                result[orig] = SlotRef(
                    file=name,
                    w=info.get("w", 0),
                    h=info.get("h", 0),
                    tw=info.get("tw", 0),
                    th=info.get("th", 0),
                )
        self.save()
        return result
