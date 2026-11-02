"""Potvrzení akce před provedením.

Panel se objeví vpravo dole, nad ostatními okny, ale **nebere fokus** —
jinak by uživateli psaní skončilo v naší aplikaci místo v té, kterou
zrovna ovládá. Potvrzuje se proto globální zkratkou.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

TIMEOUT = 45.0


class Confirmer(QObject):
    """Blokuje vlákno enginu, dokud člověk neodpoví."""

    requested = Signal(str, bool)
    dismissed = Signal()

    def __init__(self, timeout: float = TIMEOUT):
        super().__init__()
        self.timeout = timeout
        self._event = threading.Event()
        self._result = False
        self._pending = False

    def ask(self, description: str, destructive: bool) -> bool:
        """Volá se z pracovního vlákna — počká na odpověď z hlavního."""
        self._result = False
        self._event.clear()
        self._pending = True

        self.requested.emit(description, destructive)

        answered = self._event.wait(timeout=self.timeout)
        self._pending = False
        self.dismissed.emit()

        return bool(self._result) if answered else False

    def answer(self, ok: bool) -> None:
        """Volá se z hlavního vlákna (tlačítko) nebo z vlákna kláves."""
        if not self._pending:
            return
        self._result = ok
        self._event.set()


class ConfirmBar(QWidget):
    def __init__(self, confirmer: Confirmer):
        super().__init__(None)
        self.confirmer = confirmer

        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setObjectName("ConfirmBar")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        self.title = QLabel("Provést akci?")
        self.title.setObjectName("ConfirmTitle")
        layout.addWidget(self.title)

        self.popis = QLabel("")
        self.popis.setObjectName("Answer")
        self.popis.setWordWrap(True)
        layout.addWidget(self.popis)

        self.varovani = QLabel("Tohle se nedá vzít zpět.")
        self.varovani.setObjectName("Badge")
        self.varovani.setProperty("kind", "danger")
        self.varovani.setStyleSheet("padding: 4px 10px;")
        self.varovani.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.varovani.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
        )
        self.varovani.hide()

        varovani_row = QHBoxLayout()
        varovani_row.setContentsMargins(0, 0, 0, 0)
        varovani_row.addWidget(self.varovani)
        varovani_row.addStretch(1)
        layout.addLayout(varovani_row)

        self.hint = QLabel("Ctrl+Alt+Enter provede · Ctrl+Alt+Esc zruší")
        self.hint.setObjectName("Muted")
        layout.addWidget(self.hint)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)

        self.zrusit = QPushButton("Zrušit")
        self.zrusit.clicked.connect(lambda: self.confirmer.answer(False))
        buttons.addWidget(self.zrusit)

        self.provest = QPushButton("Provést")
        self.provest.setProperty("role", "primary")
        self.provest.clicked.connect(lambda: self.confirmer.answer(True))
        buttons.addWidget(self.provest)

        layout.addLayout(buttons)

        self.confirmer.requested.connect(self.show_request)
        self.confirmer.dismissed.connect(self.hide)

    def show_request(self, description: str, destructive: bool) -> None:
        self.popis.setText(description[:400])
        self.varovani.setVisible(destructive)
        self.provest.setText("Provést i tak" if destructive else "Provést")

        self.adjustSize()
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(
            screen.right() - self.width() - 24,
            screen.bottom() - self.height() - 24,
        )
        self.show()
        self.raise_()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.confirmer.answer(False)
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.confirmer.answer(True)
        else:
            super().keyPressEvent(event)
