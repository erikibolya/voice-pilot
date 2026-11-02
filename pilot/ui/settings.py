"""Nastavení — to, co se dá měnit bez editace config.json."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from .. import hotkey

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

ENGINES = [
    ("Automaticky — edge, když vypadne net, přepne na Piper", "auto"),
    ("edge-tts — nejlepší kvalita, potřebuje internet", "edge"),
    ("Piper — lokální a rychlý, robotičtější", "piper"),
]

# Qt klávesa -> náš název
SPECIALNI = {
    Qt.Key.Key_Space: "space",
    Qt.Key.Key_Return: "enter",
    Qt.Key.Key_Enter: "enter",
    Qt.Key.Key_Escape: "esc",
    Qt.Key.Key_Tab: "tab",
    Qt.Key.Key_Backspace: "backspace",
    Qt.Key.Key_Delete: "delete",
    Qt.Key.Key_Up: "up",
    Qt.Key.Key_Down: "down",
    Qt.Key.Key_Left: "left",
    Qt.Key.Key_Right: "right",
    Qt.Key.Key_Home: "home",
    Qt.Key.Key_End: "end",
    Qt.Key.Key_PageUp: "pageup",
    Qt.Key.Key_PageDown: "pagedown",
    Qt.Key.Key_Insert: "insert",
}


class HotkeyEdit(QPushButton):
    """Tlačítko, které po kliknutí zachytí stisknutou kombinaci."""

    def __init__(self, combo: str, parent=None):
        super().__init__(hotkey.popis(combo), parent)
        self.combo = combo
        self._zachytavam = False
        self._puvodni = combo
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._zacni_zachyt)

    def _zacni_zachyt(self) -> None:
        self._zachytavam = True
        self._puvodni = self.combo
        self.setText("stiskni kombinaci…")

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if not self._zachytavam:
            super().keyPressEvent(event)
            return

        if event.key() == Qt.Key.Key_Escape:
            self._zachytavam = False
            self.setText(hotkey.popis(self.combo))
            return

        kombinace = _sestav(event)
        if kombinace is None:
            return  # jen modifikátor, čekáme dál

        self._zachytavam = False

        if not hotkey.je_bezpecna(kombinace):
            self.combo = self._puvodni
            self.setText(f"{hotkey.popis(kombinace)} — potřebuje aspoň modifikátor")
            return

        self.combo = kombinace
        self.setText(hotkey.popis(kombinace))

    def focusOutEvent(self, event) -> None:  # noqa: N802
        if self._zachytavam:
            self._zachytavam = False
            self.setText(hotkey.popis(self.combo))
        super().focusOutEvent(event)


def _sestav(event) -> str | None:
    """Poskládá `ctrl+alt+space` z události Qt."""
    casti: list[str] = []
    mods = event.modifiers()

    if mods & Qt.KeyboardModifier.ControlModifier:
        casti.append("ctrl")
    if mods & Qt.KeyboardModifier.AltModifier:
        casti.append("alt")
    if mods & Qt.KeyboardModifier.ShiftModifier:
        casti.append("shift")
    if mods & Qt.KeyboardModifier.MetaModifier:
        casti.append("win")

    key = event.key()

    if key in SPECIALNI:
        casti.append(SPECIALNI[key])
    elif Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
        casti.append(f"f{key - Qt.Key.Key_F1 + 1}")
    elif Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
        casti.append(chr(key).lower())
    elif Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        casti.append(chr(key))
    else:
        return None

    return "+".join(casti)


class SettingsDialog(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Nastavení")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(9)

        self.hotkey = HotkeyEdit(cfg.hotkey)
        self.hotkey.setToolTip(
            "Klávesu drž, dokud mluvíš. Puštěním se nahrávání ukončí."
        )
        form.addRow("Klávesa", self.hotkey)

        self.voice = QComboBox()
        for label, value in VOICES:
            self.voice.addItem(label, value)
        self._select(self.voice, cfg.voice)
        form.addRow("Hlas", self.voice)

        self.engine = QComboBox()
        for label, value in ENGINES:
            self.engine.addItem(label, value)
        self._select(self.engine, cfg.tts_engine)
        form.addRow("Řeč", self.engine)

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
            "Klávesa se drží, dokud mluvíš. Změny se projeví po restartu "
            "aplikace. Během nahrávání je nechte být."
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
        self.cfg.hotkey = self.hotkey.combo
        self.cfg.voice = self.voice.currentData()
        self.cfg.tts_engine = self.engine.currentData()
        self.cfg.model_id = self.model.currentData()
        self.cfg.whisper_model = self.whisper.currentData()
        self.cfg.save()
        self.accept()
