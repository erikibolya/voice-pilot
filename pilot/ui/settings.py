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

JAZYKY = [
    ("Automaticky (podle řeči)", "auto"),
    ("Čeština", "cs"),
    ("English", "en"),
]

# hlasy pro edge-tts, rozdělené podle jazyka
HLASY = {
    "cs": [
        ("Vlasta (žena)", "cs-CZ-VlastaNeural"),
        ("Antonín (muž)", "cs-CZ-AntoninNeural"),
    ],
    "en": [
        ("Aria (žena)", "en-US-AriaNeural"),
        ("Guy (muž)", "en-US-GuyNeural"),
        ("Jenny (žena, příjemnější)", "en-US-JennyNeural"),
    ],
}

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

        self.language = QComboBox()
        for label, value in JAZYKY:
            self.language.addItem(label, value)
        self._select(self.language, cfg.language)
        form.addRow("Jazyk", self.language)

        self.voice = QComboBox()
        self._napln_hlasy(cfg.language)
        self._select(self.voice, cfg.voice)
        form.addRow("Hlas", self.voice)

        self.language.currentIndexChanged.connect(self._zmen_jazyk)

        self.engine = QComboBox()
        for label, value in ENGINES:
            self.engine.addItem(label, value)
        self._select(self.engine, cfg.tts_engine)
        form.addRow("Řeč", self.engine)

        self.engine.currentIndexChanged.connect(self._podle_enginu)

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

        note = QLabel("")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.note = note
        self._podle_enginu()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _napln_hlasy(self, jazyk: str) -> None:
        self.voice.blockSignals(True)
        self.voice.clear()
        for label, value in HLASY.get(jazyk, HLASY["cs"]):
            self.voice.addItem(label, value)
        self.voice.blockSignals(False)

    def _zmen_jazyk(self) -> None:
        """Při změně jazyka se nabídnou hlasy, které k němu patří."""
        jazyk = self.language.currentData()
        self._napln_hlasy("cs" if jazyk == "auto" else jazyk)
        self._podle_enginu()

    def _podle_enginu(self) -> None:
        """Hlas jde vybrat jen u edge-tts; Piper má jediný český hlas.

        Dřív šlo přepnout hlas i u Piperu, ale nic to nedělalo — a vypadalo
        to jako rozbitá aplikace.
        """
        piper = self.engine.currentData() == "piper"
        auto = self.language.currentData() == "auto"
        self.voice.setEnabled(not piper and not auto)

        if auto and not piper:
            self.note.setText(
                "Jazyk se pozná z řeči a hlas se vybere podle něj. "
                "Můžeš mluvit česky i anglicky v jednom sezení."
            )
            return
        if piper:
            jazyk = self.language.currentData()
            if jazyk == "en":
                self.note.setText(
                    "Piper má stažený jen český hlas (jirka). Pro angličtinu "
                    "použij edge-tts, nebo si stáhni anglický model."
                )
            else:
                self.note.setText(
                    "Piper má pro češtinu jediný hlas — jirka, mužský. "
                    "Ženský hlas nabízí jen edge-tts."
                )
        else:
            self.note.setText(
                "Jazyk mění přepis řeči, hlas i jazyk odpovědí. Změny se "
                "projeví po restartu aplikace."
            )

    @staticmethod
    def _select(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _save(self) -> None:
        self.cfg.hotkey = self.hotkey.combo
        self.cfg.language = self.language.currentData()
        self.cfg.voice = self.voice.currentData()
        self.cfg.tts_engine = self.engine.currentData()
        self.cfg.model_id = self.model.currentData()
        self.cfg.whisper_model = self.whisper.currentData()
        self.cfg.save()
        self.accept()
