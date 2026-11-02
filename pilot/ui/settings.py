"""Nastavení — to, co se dá měnit bez editace config.json."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

VOICES = [
    ("Vlasta (žena)", "cs-CZ-VlastaNeural"),
    ("Antonín (muž)", "cs-CZ-AntoninNeural"),
]

MODELS = [
    ("DeepSeek Flash — rychlý", "deepseek-flash"),
    ("DeepSeek V4 Pro — přesnější", "deepseek-v4-pro"),
]

WHISPER_SIZES = [
    ("large-v3 — nejlepší čeština (3 GB)", "large-v3"),
    ("medium — poloviční (1,5 GB)", "medium"),
    ("small — nejrychlejší (0,5 GB)", "small"),
]


class SettingsDialog(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Nastavení")
        self.setMinimumWidth(430)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(9)

        self.hotkey = QLineEdit(cfg.hotkey)
        self.hotkey.setPlaceholderText("f9")
        form.addRow("Klávesa", self.hotkey)

        self.voice = QComboBox()
        for label, value in VOICES:
            self.voice.addItem(label, value)
        self._select(self.voice, cfg.voice)
        form.addRow("Hlas", self.voice)

        self.model = QComboBox()
        for label, value in MODELS:
            self.model.addItem(label, value)
        self._select(self.model, cfg.model_id)
        form.addRow("Model", self.model)

        self.whisper = QComboBox()
        for label, value in WHISPER_SIZES:
            self.whisper.addItem(label, value)
        self._select(self.whisper, cfg.whisper_model)
        form.addRow("Přepis řeči", self.whisper)

        layout.addLayout(form)

        note = QLabel(
            "Změny se projeví po restartu aplikace. "
            "Během nahrávání je nechte být."
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _select(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _save(self) -> None:
        self.cfg.hotkey = self.hotkey.text().strip() or "f9"
        self.cfg.voice = self.voice.currentData()
        self.cfg.model_id = self.model.currentData()
        self.cfg.whisper_model = self.whisper.currentData()
        self.cfg.save()
        self.accept()
