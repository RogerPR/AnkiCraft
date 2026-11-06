"""Settings dialog for AnkiCraft Bridge (Tools > AnkiCraft Bridge)."""

from __future__ import annotations

import os

from aqt import mw
from aqt.qt import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    Qt,
    QVBoxLayout,
    qconnect,
)
from aqt.utils import openFolder

from . import wowpaths
from .bridge import merged_config

FURIGANA = [
    ("brackets", "漢字[かんじ]  (kanji + reading)"),
    ("kanji", "漢字  (hide readings)"),
    ("kana", "かんじ  (reading only)"),
]


class SettingsDialog(QDialog):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.cfg = merged_config(controller.config())
        self.setWindowTitle("AnkiCraft Bridge")
        self.setMinimumWidth(560)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        layout = QVBoxLayout(self)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        # --- WoW location
        box = QGroupBox("World of Warcraft")
        form = QFormLayout(box)
        row = QHBoxLayout()
        self.path = QLineEdit(self.cfg.get("wow_path", ""))
        self.path.setPlaceholderText(wowpaths.detect_root() or "not detected - choose your World of Warcraft folder")
        browse = QPushButton("Browse…")
        qconnect(browse.clicked, self.browse)
        row.addWidget(self.path)
        row.addWidget(browse)
        form.addRow("Game folder", row)
        self.flavor = QComboBox()
        self.flavor.setEditable(True)
        form.addRow("Game version folder", self.flavor)
        qconnect(self.path.editingFinished, self.refresh_flavors)
        layout.addWidget(box)

        # --- Cards
        box = QGroupBox("Cards sent to WoW")
        v = QVBoxLayout(box)
        v.addWidget(QLabel("Decks (none ticked = all top-level decks):"))
        self.decks = QListWidget()
        self.decks.setMaximumHeight(160)
        chosen = set(self.cfg.get("decks") or [])
        for d in sorted(mw.col.decks.all_names_and_ids(include_filtered=True), key=lambda d: d.name):
            item = QListWidgetItem(d.name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if d.name in chosen else Qt.CheckState.Unchecked)
            self.decks.addItem(item)
        v.addWidget(self.decks)
        form = QFormLayout()
        self.max_cards = QSpinBox()
        self.max_cards.setRange(10, 9999)
        self.max_cards.setValue(int(self.cfg["max_cards_per_deck"]))
        form.addRow("Max cards per deck", self.max_cards)
        self.furigana = QComboBox()
        for key, label in FURIGANA:
            self.furigana.addItem(label, key)
        keys = [k for k, _ in FURIGANA]
        current = self.cfg.get("furigana", "brackets")
        self.furigana.setCurrentIndex(keys.index(current) if current in keys else 0)
        form.addRow("Furigana", self.furigana)
        v.addLayout(form)
        layout.addWidget(box)

        # --- Media
        box = QGroupBox("Images and audio")
        form = QFormLayout(box)
        self.media = QCheckBox("Send images and audio to WoW")
        self.media.setChecked(bool(self.cfg.get("media", True)))
        form.addRow(self.media)
        self.img_size = QSpinBox()
        self.img_size.setRange(64, 1024)
        self.img_size.setSingleStep(64)
        self.img_size.setValue(int(self.cfg["image_max_size"]))
        form.addRow("Max image size (px)", self.img_size)
        self.img_slots = QSpinBox()
        self.img_slots.setRange(0, 2000)
        self.img_slots.setValue(int(self.cfg["image_slots"]))
        form.addRow("Image slots", self.img_slots)
        self.audio_slots = QSpinBox()
        self.audio_slots.setRange(0, 2000)
        self.audio_slots.setValue(int(self.cfg["audio_slots"]))
        form.addRow("Audio slots (per format)", self.audio_slots)
        note = QLabel(
            "WoW only sees files that existed when the game started. Raising the slot "
            "counts creates new files, so restart WoW afterwards."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: gray")
        form.addRow(note)
        layout.addWidget(box)

        self.auto = QCheckBox("Sync automatically while Anki is open")
        self.auto.setChecked(bool(self.cfg.get("auto_sync", True)))
        layout.addWidget(self.auto)

        # --- Log
        layout.addWidget(QLabel("Activity:"))
        self.logview = QPlainTextEdit()
        self.logview.setReadOnly(True)
        self.logview.setMaximumHeight(140)
        layout.addWidget(self.logview)

        # --- Buttons
        buttons = QDialogButtonBox()
        self.sync_btn = buttons.addButton("Save && Sync now", QDialogButtonBox.ButtonRole.ActionRole)
        folder_btn = buttons.addButton("Open data folder", QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Save)
        buttons.addButton(QDialogButtonBox.StandardButton.Close)
        qconnect(self.sync_btn.clicked, self.save_and_sync)
        qconnect(folder_btn.clicked, self.open_folder)
        qconnect(buttons.accepted, self.save_and_close)
        qconnect(buttons.rejected, self.reject)
        layout.addWidget(buttons)

        self.refresh_flavors()
        self.refresh_status()

    # ----------------------------------------------------------------
    def root(self) -> str | None:
        p = self.path.text().strip()
        return wowpaths.normalize_root(p) if p else wowpaths.detect_root()

    def browse(self) -> None:
        start = self.root() or ("C:\\" if os.name == "nt" else "/Applications")
        d = QFileDialog.getExistingDirectory(self, "Choose your World of Warcraft folder", start)
        if d:
            self.path.setText(wowpaths.normalize_root(d))
            self.refresh_flavors()

    def refresh_flavors(self) -> None:
        current = self.flavor.currentText() or self.cfg.get("flavor") or wowpaths.DEFAULT_FLAVOR
        self.flavor.clear()
        root = self.root()
        names = wowpaths.flavors(root) if root else []
        if current not in names:
            names.append(current)
        self.flavor.addItems(names)
        self.flavor.setCurrentText(current)

    def collect(self) -> dict:
        cfg = dict(self.cfg)
        path = self.path.text().strip()
        cfg["wow_path"] = wowpaths.normalize_root(path) if path else ""
        cfg["flavor"] = self.flavor.currentText().strip() or wowpaths.DEFAULT_FLAVOR
        cfg["decks"] = [
            self.decks.item(i).text()
            for i in range(self.decks.count())
            if self.decks.item(i).checkState() == Qt.CheckState.Checked
        ]
        cfg["max_cards_per_deck"] = self.max_cards.value()
        cfg["furigana"] = self.furigana.currentData()
        cfg["media"] = self.media.isChecked()
        cfg["image_max_size"] = self.img_size.value()
        cfg["image_slots"] = self.img_slots.value()
        cfg["audio_slots"] = self.audio_slots.value()
        cfg["auto_sync"] = self.auto.isChecked()
        return cfg

    def save(self) -> None:
        self.cfg = self.collect()
        self.controller.save_config(self.cfg)

    def save_and_close(self) -> None:
        self.save()
        self.controller.request_export()
        self.accept()

    def save_and_sync(self) -> None:
        self.save()
        self.sync_btn.setEnabled(False)

        def done(_res) -> None:
            self.sync_btn.setEnabled(True)
            self.refresh_status()

        self.controller.sync_now(force=True, quiet=False, on_done=done)
        self.refresh_status()

    def open_folder(self) -> None:
        b = self.controller.bridge
        addons = b.addons_dir() if b else None
        if addons:
            target = os.path.join(addons, "AnkiCraft_Data")
            openFolder(target if os.path.isdir(target) else addons)

    def refresh_status(self) -> None:
        b = self.controller.bridge
        status = b.status() if b else "Open a profile first."
        files = b.sv_files() if b else []
        if files:
            status += f"\nWatching {len(files)} WoW account(s)."
        elif b and b.addons_dir():
            status += "\nNo AnkiCraft SavedVariables yet - log into WoW with the addon enabled once."
        self.status.setText(status)
        self.logview.setPlainText("\n".join(self.controller.log_lines[-100:]) or "(nothing yet)")
        self.logview.verticalScrollBar().setValue(self.logview.verticalScrollBar().maximum())
