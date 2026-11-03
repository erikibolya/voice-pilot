"""Ikona v systémové liště."""

from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .icons import app_icon


class Tray(QSystemTrayIcon):
    def __init__(self, window, engine, parent=None):
        super().__init__(app_icon(), parent)
        self.window = window
        self.engine = engine

        from ..hotkey import popis

        self._popis = popis(engine.cfg.hotkey)
        self.setToolTip(f"voice-pilot — drž {self._popis} a mluv")

        menu = QMenu()

        self.action_show = QAction("Zobrazit okno", menu)
        self.action_show.triggered.connect(self._show)
        menu.addAction(self.action_show)

        menu.addSeparator()

        self.action_listen = QAction("Nahrát teď", menu)
        self.action_listen.triggered.connect(engine.toggle)
        menu.addAction(self.action_listen)

        self.action_settings = QAction("Nastavení…", menu)
        self.action_settings.triggered.connect(self._settings)
        menu.addAction(self.action_settings)

        self.action_update = QAction("Zkontrolovat aktualizace", menu)
        self.action_update.triggered.connect(window.check_updates)
        menu.addAction(self.action_update)

        menu.addSeparator()

        self.action_quit = QAction("Ukončit", menu)
        self.action_quit.triggered.connect(self._quit)
        menu.addAction(self.action_quit)

        self.setContextMenu(menu)
        self.activated.connect(self._activated)

    def _activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._toggle_window()

    def _toggle_window(self) -> None:
        if self.window.isVisible():
            self.window.hide()
        else:
            self._show()

    def _show(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def _settings(self) -> None:
        self._show()
        self.window.open_settings()

    def _quit(self) -> None:
        self.engine.shutdown()
        self.window.really_quit()
        from PySide6.QtWidgets import QApplication

        QApplication.quit()

    def receive(self, payload: dict) -> None:
        """Napojení na jádro — stejná cesta jako okno."""
        self._on_event(payload)

    def _on_event(self, payload: dict) -> None:
        if payload.get("type") != "state":
            return
        state = payload.get("value")
        labels = {
            "idle": f"Připraven — {self._popis} zapne diktování",
            "listening": "Diktuji…",
            "thinking": "Pracuji…",
            "speaking": "Mluvím…",
            "error": "Chyba — podívej se do okna",
        }
        self.setToolTip(f"voice-pilot — {labels.get(state, state)}")
        self.action_listen.setText(
            "Ukončit diktování" if state == "listening" else "Diktovat"
        )
