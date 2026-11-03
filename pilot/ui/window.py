"""Hlavní okno voice-pilotu."""

from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..engine import Engine
from ..theme import palette, stylesheet
from .icons import app_icon, mic_icon, state_dot, stop_icon
from .settings import SettingsDialog

STATE_TEXT = {
    "idle": "Připraven",
    "listening": "Poslouchám…",
    "thinking": "Přemýšlím…",
    "speaking": "Mluvím…",
    "error": "Něco se pokazilo",
}

STATE_HINT = {
    "idle": "Zmáčkni F9 a mluv",
    "listening": "Zmáčkni F9 pro ukončení",
    "thinking": "Chvilku strpení",
    "speaking": "Můžeš mě přerušit",
    "error": "Podrobnosti jsou v logu",
}


class MainWindow(QMainWindow):
    update_ready = Signal(object, str)
    download_ready = Signal(str)
    download_progress = Signal(float)
    download_failed = Signal(str)

    def __init__(self, cfg, engine: Engine):
        super().__init__()
        self.cfg = cfg
        self.engine = engine
        self.theme = "dark"
        self._turns = 0
        self._allow_close = False
        self._update = None

        self.setWindowTitle("voice-pilot")
        self.setWindowIcon(app_icon())
        self.resize(1040, 680)
        self.setMinimumSize(860, 560)

        self._build()
        self._wire()
        self.apply_theme(self.theme)
        self._refresh_state("idle")
        self._startup_check()

    # ------------------------------------------------------------ stavba

    def _build(self) -> None:
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_header())

        middle = QHBoxLayout()
        middle.setContentsMargins(0, 0, 0, 0)
        middle.setSpacing(0)
        middle.addWidget(self._build_rail())
        middle.addWidget(self._build_stage(), 1)
        outer.addLayout(middle, 1)

        outer.addWidget(self._build_status())
        self.setCentralWidget(root)

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("Header")
        header.setFixedHeight(52)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(14, 0, 10, 0)
        layout.setSpacing(11)

        mark = QLabel()
        mark.setPixmap(app_icon(28).pixmap(28, 28))
        mark.setFixedSize(28, 28)
        layout.addWidget(mark)

        titles = QVBoxLayout()
        titles.setContentsMargins(0, 0, 0, 0)
        titles.setSpacing(0)

        name = QLabel("voice-pilot")
        name.setObjectName("AppName")
        sub = QLabel(f"verze {__version__}")
        sub.setObjectName("AppSub")
        titles.addWidget(name)
        titles.addWidget(sub)
        layout.addLayout(titles)

        layout.addStretch(1)

        self.update_badge = QLabel("")
        self.update_badge.setObjectName("Badge")
        self.update_badge.setProperty("kind", "accent")
        self.update_badge.hide()
        layout.addWidget(self.update_badge)

        self.theme_button = self._icon_button("☀", "Přepnout světlý/tmavý režim")
        self.theme_button.clicked.connect(self.toggle_theme)
        layout.addWidget(self.theme_button)

        self.settings_button = self._icon_button("⚙", "Nastavení")
        self.settings_button.clicked.connect(self.open_settings)
        layout.addWidget(self.settings_button)

        self.hide_button = self._icon_button("—", "Skrýt do lišty")
        self.hide_button.clicked.connect(self.hide)
        layout.addWidget(self.hide_button)

        return header

    def _build_rail(self) -> QWidget:
        rail = QWidget()
        rail.setObjectName("Rail")
        rail.setFixedWidth(264)

        layout = QVBoxLayout(rail)
        layout.setContentsMargins(12, 14, 8, 8)
        layout.setSpacing(8)

        title = QLabel("Historie")
        title.setObjectName("RailTitle")
        layout.addWidget(title)

        self.history = QListWidget()
        self.history.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.history.setWordWrap(True)
        self.history.setSpacing(1)
        self.history.itemClicked.connect(self._replay)
        layout.addWidget(self.history, 1)

        self.rail_empty = QLabel("Zatím nic.\nZmáčkni F9 a mluv.")
        self.rail_empty.setObjectName("Muted")
        self.rail_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.history.addItem(QListWidgetItem(""))  # placeholder, nahradí se
        self._placeholder = self.history.item(0)
        self._placeholder.setFlags(Qt.ItemFlag.NoItemFlags)

        layout.addWidget(self.rail_empty)
        return rail

    def _build_stage(self) -> QWidget:
        stage = QWidget()
        stage.setObjectName("Stage")

        layout = QVBoxLayout(stage)
        layout.setContentsMargins(28, 26, 28, 20)
        layout.setSpacing(14)

        # --- mikrofon
        mic_row = QHBoxLayout()
        mic_row.addStretch(1)
        self.mic_button = QPushButton("")
        self.mic_button.setObjectName("MicButton")
        self.mic_button.setFixedSize(88, 88)
        self.mic_button.setIconSize(QSize(36, 36))
        self.mic_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mic_button.clicked.connect(self._on_mic)
        mic_row.addWidget(self.mic_button)
        mic_row.addStretch(1)
        layout.addLayout(mic_row)

        self.state_label = QLabel(STATE_TEXT["idle"])
        self.state_label.setObjectName("StateLabel")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.state_label)

        self.hint_label = QLabel(STATE_HINT["idle"])
        self.hint_label.setObjectName("Muted")
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.hint_label)

        layout.addSpacing(8)

        # --- karta s posledním kolem
        card = QWidget()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(6)

        self.screen_label = QLabel("")
        self.screen_label.setObjectName("Muted")
        card_layout.addWidget(self.screen_label)

        self.transcript = QLabel("")
        self.transcript.setObjectName("Transcript")
        self.transcript.setWordWrap(True)
        card_layout.addWidget(self.transcript)

        self.answer = QLabel("")
        self.answer.setObjectName("Answer")
        self.answer.setWordWrap(True)
        self.answer.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card_layout.addWidget(self.answer)

        self.plan_label = QLabel("")
        self.plan_label.setObjectName("Muted")
        self.plan_label.setWordWrap(True)
        card_layout.addWidget(self.plan_label)

        card_layout.addStretch(1)
        layout.addWidget(card, 1)

        # --- psaný vstup
        ask_row = QHBoxLayout()
        ask_row.setSpacing(8)
        self.ask_input = QLineEdit()
        self.ask_input.setPlaceholderText("Nebo napiš dotaz a zmáčkni Enter…")
        self.ask_input.returnPressed.connect(self._on_ask)
        self.ask_button = QPushButton("Odeslat")
        self.ask_button.clicked.connect(self._on_ask)
        ask_row.addWidget(self.ask_input, 1)
        ask_row.addWidget(self.ask_button)
        layout.addLayout(ask_row)

        # --- log
        self.log_label = QLabel("")
        self.log_label.setObjectName("Muted")
        self.log_label.setWordWrap(True)
        self.log_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        layout.addWidget(self.log_label)

        return stage

    def _build_status(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("StatusBar")
        bar.setFixedHeight(30)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 0, 12, 0)
        layout.setSpacing(10)

        self.status_dot = QLabel()
        self.status_dot.setFixedSize(10, 10)
        layout.addWidget(self.status_dot)

        self.status_state = QLabel("Připraven")
        layout.addWidget(self.status_state)

        self.status_rest = QLabel("")
        layout.addWidget(self.status_rest)

        self.stop_hint = QLabel("")
        self.stop_hint.setStyleSheet(
            "color: #e11d48; font-weight: 600;"
        )
        layout.addWidget(self.stop_hint)

        layout.addStretch(1)

        self.update_button = QPushButton("Aktualizovat")
        self.update_button.setProperty("role", "ghost")
        self.update_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_button.clicked.connect(self._on_update_clicked)
        self.update_button.hide()
        layout.addWidget(self.update_button)

        return bar

    @staticmethod
    def _icon_button(glyph: str, tooltip: str) -> QPushButton:
        button = QPushButton(glyph)
        button.setProperty("role", "icon")
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    # ------------------------------------------------------------ signály

    def _wire(self) -> None:
        self.update_ready.connect(self._show_update)
        self.download_ready.connect(self._run_installer)
        self.download_progress.connect(self._on_progress)
        self.download_failed.connect(self._on_download_failed)

    def receive(self, payload: dict) -> None:
        """Sem chodí události z jádra (přes signál z hlavního vlákna)."""
        self._on_event(payload)

    def _on_event(self, payload: dict) -> None:
        kind = payload.get("type")

        if kind == "state":
            self._refresh_state(payload["value"], payload.get("detail", ""))

        elif kind == "heard":
            text = payload.get("text", "")
            if text:
                self.transcript.setText(text)
                self._add_history(text)
            else:
                self.transcript.setText("(nic jsem neslyšel)")

        elif kind == "screen":
            self.screen_label.setText(
                f'Vidím {payload["elements"]} prvků v okně „{_short(payload["window"], 40)}“'
            )

        elif kind == "answer":
            self.answer.setText(payload["text"])
            self.plan_label.setText("")
            self._log("Odpověď přečtena nahlas.")

        elif kind == "plan":
            popis = payload["description"]
            prefix = "Pozor, nevratné: " if payload["destructive"] else "Chystám se "
            self.plan_label.setText(prefix + popis)
            self._log(f"Čekám na potvrzení — {popis}")

        elif kind == "executed":
            if payload.get("cancelled"):
                self.plan_label.setText("Zrušeno, nic jsem neudělal.")
                self._log("Akce zrušena.")
            else:
                vysledky = payload.get("results", [])
                self.plan_label.setText("Hotovo: " + "; ".join(vysledky))
                self._log(f"Provedeno {len(vysledky)} akcí.")

        elif kind == "control":
            self.stop_hint.setText(
                "AI pracuje — Ctrl+Alt+Esc přeruší" if payload.get("on") else ""
            )

        elif kind == "log":
            self._log(payload["text"])

    def _refresh_state(self, state: str, detail: str = "") -> None:
        self.state_label.setText(STATE_TEXT.get(state, state))
        self.hint_label.setText(detail or STATE_HINT.get(state, ""))
        self.status_state.setText(STATE_TEXT.get(state, state))
        self.status_dot.setPixmap(state_dot(state).pixmap(10, 10))

        self.mic_button.setProperty("state", state)
        self.mic_button.style().unpolish(self.mic_button)
        self.mic_button.style().polish(self.mic_button)
        self._update_mic_icon(state)

    def _update_mic_icon(self, state: str) -> None:
        colors = palette(self.theme)
        if state == "listening":
            icon = stop_icon("#ffffff", 34)
        elif state == "thinking":
            icon = mic_icon(colors["warn"], 34)
        elif state == "speaking":
            icon = mic_icon(colors["accent"], 34)
        elif state == "error":
            icon = mic_icon(colors["danger"], 34)
        else:
            icon = mic_icon(colors["muted"], 34)
        self.mic_button.setIcon(icon)

    # ------------------------------------------------------------ akce

    def _on_mic(self) -> None:
        self.engine.toggle()

    def _on_ask(self) -> None:
        text = self.ask_input.text().strip()
        if not text:
            return
        self.ask_input.clear()
        self.engine.ask(text)

    def _add_history(self, text: str) -> None:
        if self.history.count() == 1 and self._placeholder is not None:
            self.history.takeItem(0)
            self._placeholder = None
            self.rail_empty.hide()

        time = dt.datetime.now().strftime("%H:%M")
        item = QListWidgetItem(f"{time}  {_short(text, 44)}")
        item.setData(Qt.ItemDataRole.UserRole, text)
        item.setToolTip(text)
        self.history.insertItem(0, item)
        self._turns += 1

    def _replay(self, item: QListWidgetItem) -> None:
        text = item.data(Qt.ItemDataRole.UserRole)
        if text:
            self.ask_input.setText(text)
            self.ask_input.setFocus()

    def _log(self, text: str) -> None:
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        self.log_label.setText(f"{stamp}  {text}")

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.cfg, self)
        if dialog.exec():
            self.apply_theme(self.theme)
            self._log("Nastavení uloženo. Změny se projeví při dalším spuštění.")

    def toggle_theme(self) -> None:
        self.apply_theme("light" if self.theme == "dark" else "dark")

    def apply_theme(self, theme: str) -> None:
        self.theme = theme
        self.setStyleSheet(stylesheet(theme))
        self.theme_button.setText("☾" if theme == "light" else "☀")
        self._refresh_state(self.engine.state, self.hint_label.text() or "")

    # ---------------------------------------------------------- aktualizace

    def check_updates(self) -> None:
        from .. import updater

        self.update_button.setEnabled(False)
        self.update_button.setText("Kontroluji…")

        def work() -> None:
            update, message = updater.check()
            self.update_ready.emit(update, message)

        import threading

        threading.Thread(target=work, daemon=True).start()

    def _show_update(self, update, message: str) -> None:
        self.update_button.setEnabled(True)
        self.update_button.setText("Zkontrolovat aktualizace")
        self._log(message)

        if update is None:
            self._update = None
            self.update_badge.hide()
            self.update_button.hide()
            return

        self._update = update
        self.update_badge.setText(f"nová {update.version}")
        self.update_badge.show()
        self.update_button.setText(f"Nainstalovat {update.version}")
        self.update_button.show()

    def _on_update_clicked(self) -> None:
        if self._update is None:
            self.check_updates()
            return
        self._install_update()

    def _install_update(self) -> None:
        from .. import updater

        update = self._update
        if update is None:
            return

        self.update_button.setEnabled(False)
        self.update_button.setText("Stahuji… 0 %")
        self._log(f"Stahuji verzi {update.version}…")

        def work() -> None:
            try:
                path = updater.download(update, progress=self.download_progress.emit)
            except Exception as exc:
                self.download_failed.emit(str(exc))
                return
            self.download_ready.emit(str(path))

        import threading

        threading.Thread(target=work, daemon=True).start()

    def _on_progress(self, fraction: float) -> None:
        self.update_button.setText(f"Stahuji… {fraction * 100:.0f} %")

    def _on_download_failed(self, message: str) -> None:
        self.update_button.setEnabled(True)
        self.update_button.setText("Zkusit znovu")
        self._log(f"Stažení selhalo: {message}")

    def _run_installer(self, path: str) -> None:
        import subprocess

        self._log("Staženo. Spouštím instalátor, aplikace se zavře.")
        self.update_button.setText("Spouštím instalátor…")
        try:
            subprocess.Popen([path], close_fds=True)
        except Exception as exc:
            self._on_download_failed(f"instalátor se nepodařilo spustit: {exc}")
            return

        QTimer.singleShot(900, self._quit_for_update)

    def _quit_for_update(self) -> None:
        self._allow_close = True
        from PySide6.QtWidgets import QApplication

        QApplication.quit()

    def _startup_check(self) -> None:
        ok, detail = self.engine.preflight()
        self.status_rest.setText(detail if ok else "OpenCode neběží")
        if not ok:
            self._log(detail)
            self.answer.setText(
                "Nemůžu se spojit s OpenCode. Spusť desktopovou aplikaci "
                "OpenCode a nech ji otevřenou — bez ní nemám čím myslet."
            )
            return

        self._log(detail)
        QTimer.singleShot(1200, self.check_updates)

    # ------------------------------------------------------------ zavírání

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._allow_close:
            event.accept()
            return
        event.ignore()
        self.hide()
        self._log("Skryto do lišty. Odtud mě dostaneš dvojklikem na ikonu.")

    def really_quit(self) -> None:
        self._allow_close = True
        self.close()


def _short(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
