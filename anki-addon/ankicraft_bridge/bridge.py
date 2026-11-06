"""Qt-free orchestration: watch SavedVariables, apply ops, export data.

The Anki GUI glue in __init__.py calls into this; tests call it directly.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from . import exporter, importer, wowpaths
from .media import MediaPool

DEFAULT_CONFIG = {
    "wow_path": "",
    "flavor": wowpaths.DEFAULT_FLAVOR,
    "decks": [],
    "max_cards_per_deck": 1000,
    "max_total_cards": 5000,
    "furigana": "brackets",
    "media": True,
    "image_max_size": 512,
    "image_slots": 200,
    "audio_slots": 200,
    "auto_sync": True,
    "poll_seconds": 3,
}


# Defaults from 1.0.0 that were too low (a deck with 574 due cards was cut
# to 300). Saved configs still holding these exact values get the new ones.
_OLD_DEFAULTS = {"max_cards_per_deck": 300, "max_total_cards": 2000}


def merged_config(cfg: dict | None) -> dict:
    out = dict(DEFAULT_CONFIG)
    out.update({k: v for k, v in (cfg or {}).items() if not k.startswith("_")})
    if all(out.get(k) == v for k, v in _OLD_DEFAULTS.items()):
        out.update({k: DEFAULT_CONFIG[k] for k in _OLD_DEFAULTS})
    return out


@dataclass
class ExportResult:
    cards: int = 0
    decks: int = 0
    data_dir: str = ""
    restart_needed: bool = False
    restart_reasons: list[str] = field(default_factory=list)


class Bridge:
    def __init__(self, cfg: dict | None = None, log=print):
        self.cfg = merged_config(cfg)
        self.log = log
        self._mtimes: dict[str, float] = {}
        self._read_failures: dict[tuple[str, float], int] = {}
        self.last_sync: dict | None = None

    # ------------------------------------------------------------ paths
    def root(self) -> str | None:
        p = (self.cfg.get("wow_path") or "").strip()
        if p:
            p = wowpaths.normalize_root(p)
            return p if os.path.isdir(p) else None
        return wowpaths.detect_root()

    def flavor(self) -> str:
        return self.cfg.get("flavor") or wowpaths.DEFAULT_FLAVOR

    def addons_dir(self) -> str | None:
        root = self.root()
        if not root:
            return None
        d = wowpaths.addons_dir(root, self.flavor())
        return d if os.path.isdir(d) else None

    def sv_files(self) -> list[str]:
        root = self.root()
        return wowpaths.savedvariables_files(root, self.flavor()) if root else []

    def status(self) -> str:
        root = self.root()
        if not root:
            return "World of Warcraft folder not found. Set it in AnkiCraft Bridge settings."
        if not self.addons_dir():
            return f"No Interface/AddOns folder for flavor {self.flavor()} in {root}."
        if not wowpaths.addon_installed(root, self.flavor()):
            return "The AnkiCraft WoW addon is not installed in this flavor yet (install it from CurseForge)."
        return f"Connected to {os.path.join(root, self.flavor())}"

    # ------------------------------------------------------------ import
    def changed_sv_files(self, settle_seconds: float = 1.0) -> list[str]:
        """SavedVariables files whose mtime changed since last processed and
        that have not been modified in the last settle_seconds."""
        out = []
        now = time.time()
        for path in self.sv_files():
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if self._mtimes.get(path) == mtime or now - mtime < settle_seconds:
                continue
            out.append(path)
        return out

    def mark_seen(self, path: str) -> None:
        try:
            self._mtimes[path] = os.path.getmtime(path)
        except OSError:
            pass

    MAX_READ_ATTEMPTS = 5

    def note_read_failure(self, path: str, error: Exception) -> bool:
        """Returns True when we should stop retrying this version of the file."""
        try:
            key = (path, os.path.getmtime(path))
        except OSError:
            return True
        n = self._read_failures.get(key, 0) + 1
        self._read_failures[key] = n
        if n >= self.MAX_READ_ATTEMPTS:
            self.log(f"Could not read {path}: {error}")
            return True
        return False

    def import_files(self, col, paths: list[str], undo_name: str | None = None):
        """Apply new ops from the given SavedVariables files. With undo_name
        everything is merged into one undo step; returns (results, OpChanges
        or None)."""
        work = []
        acks = importer.get_acks(col)
        for path in paths:
            try:
                db = importer.read_savedvariables(path)
            except Exception as e:
                # Probably caught WoW mid-write (or the file is locked on
                # Windows): retry on the next poll, give up after a few tries.
                if not self.note_read_failure(path, e):
                    continue
                db = None
            self.mark_seen(path)
            if not db or not isinstance(db.get("installId"), str):
                continue
            install_id = db["installId"]
            ops = [op for op in importer.pending_ops(db) if op["seq"] > acks.get(install_id, 0)]
            if ops:
                work.append((install_id, ops))
        if not work:
            return [], None
        pos = col.add_custom_undo_entry(undo_name) if undo_name else None
        results = []
        for install_id, ops in work:
            res = importer.apply_ops(col, install_id, ops)
            if res.total:
                self.log(f"Applied from WoW: {res.summary()}")
                for err in res.errors:
                    self.log(f"  {err}")
                results.append(res)
        if results:
            self.last_sync = {
                "at": int(time.time()),
                "answered": sum(r.answered for r in results),
                "added": sum(r.added for r in results),
                "changed": sum(r.changed for r in results),
                "conflicts": sum(r.conflicts for r in results),
                "errors": sum(len(r.errors) for r in results),
            }
        changes = col.merge_undo_entries(pos) if pos is not None else None
        return results, changes

    # ------------------------------------------------------------ export
    def media_pool(self, addons: str) -> MediaPool | None:
        if not self.cfg.get("media", True):
            return None
        return MediaPool(
            os.path.join(addons, exporter.DATA_ADDON, "media"),
            img_slots=int(self.cfg["image_slots"]),
            audio_slots=int(self.cfg["audio_slots"]),
            max_image=int(self.cfg["image_max_size"]),
        )

    def export(self, col) -> ExportResult | None:
        addons = self.addons_dir()
        if not addons:
            self.log(self.status())
            return None
        res = ExportResult()
        pool = self.media_pool(addons)
        if pool is not None:
            created = pool.ensure_pool()
            if created:
                res.restart_needed = True
                res.restart_reasons.append(f"created {created} media slot files")
        root = self.root()
        interface = wowpaths.interface_version(root, self.flavor(), exporter.DEFAULT_INTERFACE) if root else exporter.DEFAULT_INTERFACE
        data = exporter.build_export(col, self.cfg, importer.get_acks(col), pool, self.last_sync)
        try:
            folder, created = exporter.write_data_addon(addons, data, interface)
        except PermissionError as e:
            raise PermissionError(
                f"Can't write to {addons} ({e}). Another program may be holding the file "
                "(try again in a moment), or your user can't write to the WoW folder: "
                "make sure the WoW folder isn't read-only and Anki isn't blocked by antivirus "
                "'controlled folder access'."
            ) from e
        if created:
            res.restart_needed = True
            res.restart_reasons.append("created the AnkiCraft_Data addon")
        res.cards = len(data["cards"])
        res.decks = len(data["decks"])
        res.data_dir = folder
        return res

    def full_sync(self, col, force: bool = False) -> tuple[list[importer.SyncResult], ExportResult | None]:
        paths = self.sv_files() if force else self.changed_sv_files()
        results, _ = self.import_files(col, paths)
        return results, self.export(col)
