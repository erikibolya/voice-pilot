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
        # QScreen umí Qt mezitím smazat (změna monitorů) — držíme jen jméno
        self.screen_name = screen.name()

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

    def _obrazovka(self):
        from PySide6.QtGui import QGuiApplication

        for screen in QGuiApplication.screens():
            try:
                if screen.name() == self.screen_name:
                    return screen
            except RuntimeError:
                continue
        return QGuiApplication.primaryScreen()

    def set_theme(self, theme: str) -> None:
        self._tema = theme
        self.update()

    def set_active(self, aktivni: bool) -> None:
        if aktivni == self._aktivni:
            return
        self._aktivni = aktivni
        if aktivni:
            obrazovka = self._obrazovka()
            if obrazovka is not None:
                self.setGeometry(obrazovka.geometry())
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
        pulz = 0.55 + 0.35 * math.sin(self._faze)

        # ---------- barevný inset shadow po stranách ----------
        barva = QColor("#7c5cff")          # fialovomodrá, čitelná v obou režimech
        hloubka = 170
        sila = 0.34 * (0.75 + 0.25 * pulz)

        def prechod(x0: float, y0: float, x1: float, y1: float) -> QLinearGradient:
            g = QLinearGradient(x0, y0, x1, y1)
            vnitrni = QColor(barva)
            vnitrni.setAlphaF(sila)
            vnejsi = QColor(barva)
            vnejsi.setAlphaF(0.0)
            g.setColorAt(0.0, vnitrni)
            g.setColorAt(1.0, vnejsi)
            return g

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(prechod(0, 0, 0, hloubka))
        painter.drawRect(QRectF(0, 0, sirka, hloubka))

        painter.setBrush(prechod(0, vyska, 0, vyska - hloubka))
        painter.drawRect(QRectF(0, vyska - hloubka, sirka, hloubka))

        painter.setBrush(prechod(0, 0, hloubka, 0))
        painter.drawRect(QRectF(0, 0, hloubka, vyska))

        painter.setBrush(prechod(sirka, 0, sirka - hloubka, 0))
        painter.drawRect(QRectF(sirka - hloubka, 0, hloubka, vyska))

        # jemná linka po obvodu, ať je okraj čitelný i na světlé ploše
        obrys = QColor(barva)
        obrys.setAlphaF(0.5)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(obrys, 2))
        painter.drawRoundedRect(QRectF(3, 3, sirka - 6, vyska - 6), 16, 16)

        # ---------- chip uprostřed ----------
        text = "AI is using your computer"
        font = QFont(c["font"], 10)
        font.setBold(True)
        painter.setFont(font)

        metr = painter.fontMetrics()
        textova = metr.horizontalAdvance(text)
        chip_w = textova + 62
        chip_h = 38
        cx = sirka / 2
        cy = vyska * 0.42
        chip = QRectF(cx - chip_w / 2, cy - chip_h / 2, chip_w, chip_h)

        pozadi = QColor(c["panel2"])
        pozadi.setAlpha(244)
        painter.setBrush(pozadi)
        ram = QColor(barva)
        ram.setAlphaF(0.9)
        painter.setPen(QPen(ram, 1))
        painter.drawRoundedRect(chip, chip_h / 2, chip_h / 2)

        # pulzující tečka
        stred = QPointF(chip.left() + 23, chip.center().y())
        halo = QColor(barva)
        halo.setAlphaF(0.22 + 0.28 * pulz)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(stred, 9 + 3 * pulz, 9 + 3 * pulz)

        plna = QColor(barva)
        plna.setAlphaF(0.85 + 0.15 * pulz)
        painter.setBrush(plna)
        painter.drawEllipse(stred, 4.5, 4.5)

        painter.setPen(QColor(c["text"]))
        painter.drawText(
            QRectF(chip.left() + 40, chip.top(), chip_w - 48, chip_h),
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
