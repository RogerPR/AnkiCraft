"""AnkiCraft Bridge: sync Anki with the AnkiCraft World of Warcraft addon.

While Anki is open this add-on:
  * exports your due cards to WoW (Interface/AddOns/AnkiCraft_Data),
  * watches WoW's SavedVariables and applies reviews/new notes/flags you
    made in-game, using Anki's real scheduler and the in-game answer time.
"""

from __future__ import annotations

import os
import time

try:
    from aqt import gui_hooks, mw
except ImportError:  # running outside Anki (unit tests)
    mw = None

if mw is not None:
    from anki.collection import OpChanges
    from aqt.operations import CollectionOp, QueryOp
    from aqt.qt import QAction, QTimer, qconnect
    from aqt.utils import showInfo, tooltip

    from .bridge import Bridge, merged_config

    ADDON_DIR = os.path.dirname(__file__)
    LOG_DIR = os.path.join(ADDON_DIR, "user_files")
    LOG_PATH = os.path.join(LOG_DIR, "ankicraft.log")
    EXPORT_DEBOUNCE_MS = 8000

    class Controller:
        def __init__(self) -> None:
            self.bridge: Bridge | None = None
            self.log_lines: list[str] = []
            self.busy = False
            self.dirty = False  # an export is wanted once we are idle
            self.today: int | None = None
            self.restart_notice_shown = False
            self.export_error_shown = False
            self.poll = QTimer(mw)
            qconnect(self.poll.timeout, self.tick)
            self.debounce = QTimer(mw)
            self.debounce.setSingleShot(True)
            qconnect(self.debounce.timeout, self.request_export)

        # ------------------------------------------------------- config/log
        def config(self) -> dict:
            return merged_config(mw.addonManager.getConfig(__name__))

        def save_config(self, cfg: dict) -> None:
            mw.addonManager.writeConfig(__name__, cfg)
            if self.bridge:
                self.bridge.cfg = merged_config(cfg)
            self.restart_poll()

        def log(self, msg: str) -> None:
            line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
            self.log_lines = (self.log_lines + [line])[-300:]
            try:
                os.makedirs(LOG_DIR, exist_ok=True)
                if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 1_000_000:
                    os.replace(LOG_PATH, LOG_PATH + ".old")
                with open(LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                pass

        # ------------------------------------------------------- lifecycle
        def on_profile_open(self) -> None:
            self.bridge = Bridge(self.config(), log=self.log)
            self.log("Profile opened. " + self.bridge.status())
            self.restart_poll()
            self.sync_now(force=True, quiet=True)

        def on_profile_close(self) -> None:
            self.poll.stop()
            self.debounce.stop()
            self.bridge = None

        def restart_poll(self) -> None:
            self.poll.stop()
            if self.bridge and self.bridge.cfg.get("auto_sync", True):
                self.poll.start(max(1, int(self.bridge.cfg.get("poll_seconds", 3))) * 1000)

        def on_operation(self, changes: OpChanges, handler: object | None) -> None:
            if handler is self or not self.bridge:
                return
            if changes.card or changes.note_text or changes.deck or changes.deck_config or changes.notetype:
                self.debounce.start(EXPORT_DEBOUNCE_MS)

        def on_ankiweb_sync(self) -> None:
            self.request_export()

        # ------------------------------------------------------- work
        def tick(self) -> None:
            if not self.bridge or not mw.col or self.busy:
                return
            today = mw.col.sched.today
            if self.today is not None and today != self.today:
                self.dirty = True  # new day: new cards are due
            self.today = today
            changed = self.bridge.changed_sv_files()
            if changed:
                self.sync_paths(changed, quiet=False)
            elif self.dirty:
                self.request_export()

        def sync_now(self, force: bool = True, quiet: bool = False, on_done=None) -> None:
            if not self.bridge or not mw.col:
                return
            paths = self.bridge.sv_files() if force else self.bridge.changed_sv_files()
            self.sync_paths(paths, quiet=quiet, on_done=on_done)

        def sync_paths(self, paths: list[str], quiet: bool, on_done=None) -> None:
            if self.busy:
                self.dirty = True
                return
            self.busy = True
            bridge = self.bridge
            holder: dict = {}

            def op(col):
                results, changes = bridge.import_files(col, paths, undo_name="AnkiCraft: reviews from WoW")
                holder["results"] = results
                return changes or OpChanges()

            def done(_changes) -> None:
                results = holder.get("results") or []
                if results and not quiet:
                    tooltip("AnkiCraft: " + "; ".join(r.summary() for r in results), period=4000)
                self.busy = False
                self.request_export(on_done=on_done)

            def failed(exc: Exception) -> None:
                self.busy = False
                self.log(f"Sync failed: {exc!r}")
                tooltip(f"AnkiCraft sync failed: {exc}")

            CollectionOp(parent=mw, op=op).success(done).failure(failed).run_in_background(initiator=self)

        def request_export(self, on_done=None) -> None:
            if not self.bridge or not mw.col:
                return
            if self.busy:
                self.dirty = True
                return
            self.busy = True
            self.dirty = False
            bridge = self.bridge

            def finished(res) -> None:
                self.busy = False
                if res is not None:
                    self.export_error_shown = False
                    self.log(f"Exported {res.cards} cards from {res.decks} decks to WoW.")
                    if res.restart_needed and not self.restart_notice_shown:
                        self.restart_notice_shown = True
                        showInfo(
                            "AnkiCraft Bridge set up your card data for World of Warcraft "
                            f"({', '.join(res.restart_reasons)}).\n\n"
                            "Fully restart World of Warcraft once (exit the game, not just /reload) "
                            "so it can see the new files. After that, /reload is enough.",
                            title="AnkiCraft Bridge",
                        )
                if on_done:
                    on_done(res)
                if self.dirty:
                    self.request_export()

            def failed(exc: Exception) -> None:
                self.busy = False
                self.log(f"Export failed: {exc}")
                if not self.export_error_shown:
                    self.export_error_shown = True
                    tooltip("AnkiCraft: couldn't send cards to WoW. See Tools > AnkiCraft Bridge.", period=6000)
                if on_done:
                    on_done(None)

            QueryOp(parent=mw, op=lambda col: bridge.export(col), success=finished).failure(
                failed
            ).run_in_background()

        # ------------------------------------------------------- UI
        def open_settings(self) -> None:
            from .settings_dialog import SettingsDialog

            if not self.bridge:
                self.bridge = Bridge(self.config(), log=self.log)
            SettingsDialog(mw, self).show()

    controller = Controller()

    gui_hooks.profile_did_open.append(controller.on_profile_open)
    gui_hooks.profile_will_close.append(controller.on_profile_close)
    gui_hooks.operation_did_execute.append(controller.on_operation)
    gui_hooks.sync_did_finish.append(controller.on_ankiweb_sync)

    _action = QAction("AnkiCraft Bridge (World of Warcraft)…", mw)
    qconnect(_action.triggered, controller.open_settings)
    mw.form.menuTools.addAction(_action)
    mw.addonManager.setConfigAction(__name__, controller.open_settings)
