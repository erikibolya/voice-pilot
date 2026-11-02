"""Grafika nad obrazovkou: co zrovna dělám.

Dvě věci:
  * `DictationOverlay` — pruh dole uprostřed, který pulzuje podle hlasu,
    dokud držíš klávesu. Je vidět, že poslouchám.
  * `ControlFrame` — rám kolem obrazovky, který se rozsvítí, když přebírám
    kontrolu nad počítačem. Nedá se přehlédnout a nedá se splést s ničím
    jiným, co na ploše běží.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QWidget

from ..theme import palette

POCET_SLOUPCU = 30


class DictationOverlay(QWidget):
    """Pruh dole uprostřed, který reaguje na hlas."""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.setFixedSize(360, 92)

        self._urovne = [0.0] * POCET_SLOUPCU
        self._ticho = 0
        self._tema = "dark"

        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30 fps
        self._timer.timeout.connect(self._tik)

    # ------------------------------------------------------------- ovládání

    def set_theme(self, theme: str) -> None:
        self._tema = theme
        self.update()

    def push_level(self, level: float) -> None:
        """Volá se z audio vlákna — jen uloží hodnotu."""
        self._urovne.append(max(0.0, min(1.0, level)))
        del self._urovne[:-POCET_SLOUPCU]
        self._ticho = 0

    def show_for_cursor(self) -> None:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        self.move(
            geo.center().x() - self.width() // 2,
            geo.bottom() - self.height() - 40,
        )
        self.show()
        self.raise_()
        self._timer.start()

    def hide_overlay(self) -> None:
        self._timer.stop()
        self.hide()

    # ------------------------------------------------------------- kreslení

    def _tik(self) -> None:
        # bez signálu sloupce postupně klesnou, aby pruh nezůstal zaseknutý
        self._ticho += 1
        if self._ticho > 2:
            self._urovne.append(self._urovne[-1] * 0.85)
            del self._urovne[:-POCET_SLOUPCU]
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        c = palette(self._tema)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # pozadí
        pozadi = QColor(c["panel2"])
        pozadi.setAlpha(238)
        painter.setBrush(pozadi)
        ram = QPen(QColor(c["border"]), 1)
        painter.setPen(ram)
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 16, 16)

        # štítek
        font = QFont(c["font"], 8)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(c["muted"]))
        painter.drawText(
            QRectF(18, 10, self.width() - 36, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "DIKTUJI",
        )

        # sloupce
        levy = 18.0
        pravy = 18.0
        spodek = self.height() - 16.0
        vrsek = 32.0
        dostupna = self.width() - levy - pravy
        sirka = dostupna / POCET_SLOUPCU
        max_vyska = spodek - vrsek

        for i, uroven in enumerate(self._urovne):
            x = levy + i * sirka
            vyska = max(3.0, uroven * max_vyska)

            svetlost = 0.45 + 0.55 * (i / max(1, POCET_SLOUPCU - 1))
            barva = QColor(c["accent"])
            barva.setAlphaF(max(0.25, min(1.0, svetlost)))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(barva)
            painter.drawRoundedRect(
                QRectF(x + 1.5, spodek - vyska, max(2.0, sirka - 3.0), vyska),
                1.5,
                1.5,
            )

        painter.end()


class ControlFrame(QWidget):
    """Rám kolem jedné obrazovky, který hlásí „ovládám počítač“."""

    def __init__(self, screen):
        super().__init__(None)
        self.screen = screen
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._aktivni = False
        self._faze = 0.0
        self._tema = "dark"

        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tik)

        self.setGeometry(screen.geometry())

    def set_theme(self, theme: str) -> None:
        self._tema = theme
        self.update()

    def set_active(self, aktivni: bool) -> None:
        if aktivni == self._aktivni:
            return
        self._aktivni = aktivni
        if aktivni:
            self.setGeometry(self.screen.geometry())
            self.show()
            self.raise_()
            self._timer.start()
        else:
            self._timer.stop()
            self.hide()

    def _tik(self) -> None:
        self._faze = (self._faze + 0.05) % (2 * math.pi)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._aktivni:
            return

        c = palette(self._tema)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        sirka, vyska = self.width(), self.height()
        pulz = 0.55 + 0.25 * math.sin(self._faze)

        # vnější záře — několik průhledných rámů
        for i, tloustka in enumerate((18, 12, 7)):
            barva = QColor(c["accent"])
            barva.setAlphaF(0.10 * (3 - i) * pulz)
            pero = QPen(barva, tloustka)
            painter.setPen(pero)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(
                QRectF(tloustka / 2 + 1, tloustka / 2 + 1,
                       sirka - tloustka - 2, vyska - tloustka - 2),
                14, 14,
            )

        # ostrá linka
        barva = QColor(c["accent"])
        barva.setAlphaF(0.85)
        painter.setPen(QPen(barva, 2))
        painter.drawRoundedRect(QRectF(2, 2, sirka - 4, vyska - 4), 12, 12)

        # štítek nahoře uprostřed
        text = "PILOT OVLÁDÁ POČÍTAČ"
        font = QFont(c["font"], 9)
        font.setBold(True)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.4)
        painter.setFont(font)

        metr = painter.fontMetrics()
        textova = metr.horizontalAdvance(text)
        box_sirka = textova + 42
        box_vyska = 30
        box = QRectF((sirka - box_sirka) / 2, 10, box_sirka, box_vyska)

        pozadi = QColor(c["panel2"])
        pozadi.setAlpha(240)
        painter.setBrush(pozadi)
        painter.setPen(QPen(QColor(c["accent"]), 1))
        painter.drawRoundedRect(box, 15, 15)

        tecka = QPointF(box.left() + 16, box.center().y())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(c["accent"]))
        painter.drawEllipse(tecka, 4, 4)

        painter.setPen(QColor(c["text"]))
        painter.drawText(
            QRectF(box.left() + 28, box.top(), box_sirka - 32, box_vyska),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            text,
        )

        painter.end()


class Overlays:
    """Drží všechny překryvy a stará se o jejich stav."""

    def __init__(self):
        self.diktovani = DictationOverlay()
        self.ramy = [ControlFrame(s) for s in QGuiApplication.screens()]
        self._tema = "dark"

    def set_theme(self, theme: str) -> None:
        self._tema = theme
        self.diktovani.set_theme(theme)
        for ram in self.ramy:
            ram.set_theme(theme)

    def begin_dictation(self) -> None:
        self.diktovani.show_for_cursor()

    def end_dictation(self) -> None:
        self.diktovani.hide_overlay()

    def level(self, hodnota: float) -> None:
        self.diktovani.push_level(hodnota)

    def show_control(self, aktivni: bool) -> None:
        # obrazovky se mohly mezitím změnit (připojení monitoru)
        if len(self.ramy) != len(QGuiApplication.screens()):
            for ram in self.ramy:
                ram.close()
            self.ramy = [ControlFrame(s) for s in QGuiApplication.screens()]
            for ram in self.ramy:
                ram.set_theme(self._tema)

        for ram in self.ramy:
            ram.set_active(aktivni)
