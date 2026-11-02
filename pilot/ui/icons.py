"""Ikony kreslené za běhu — žádné obrázky, které by se musely balit."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def app_icon(size: int = 64, accent: str = "#2f81f7") -> QIcon:
    """Zaoblený čtverec s mikrofonem."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    radius = size * 0.22
    painter.setBrush(QBrush(QColor(accent)))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)

    white = QColor("#ffffff")
    painter.setBrush(QBrush(white))
    painter.setPen(Qt.PenStyle.NoPen)

    # tělo mikrofonu
    capsule_w = size * 0.24
    capsule_h = size * 0.36
    painter.drawRoundedRect(
        QRectF(
            (size - capsule_w) / 2,
            size * 0.20,
            capsule_w,
            capsule_h,
        ),
        capsule_w / 2,
        capsule_w / 2,
    )

    # oblouk pod ním
    painter.setBrush(Qt.BrushStyle.NoBrush)
    pen = QPen(white)
    pen.setWidthF(max(2.0, size * 0.055))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    arc = QRectF(size * 0.26, size * 0.30, size * 0.48, size * 0.40)
    painter.drawArc(arc, 180 * 16, 180 * 16)

    # nožička
    painter.drawLine(
        QPointF(size / 2, size * 0.70),
        QPointF(size / 2, size * 0.80),
    )
    painter.end()

    return QIcon(pixmap)


def dot_icon(color: str, size: int = 16) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QBrush(QColor(color)))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QRectF(3, 3, size - 6, size - 6))
    painter.end()
    return QIcon(pixmap)


def state_dot(state: str) -> QIcon:
    colors = {
        "listening": "#e11d48",
        "thinking": "#d29922",
        "speaking": "#2f81f7",
        "error": "#e11d48",
        "idle": "#16a34a",
    }
    return dot_icon(colors.get(state, "#8b98a8"))


def mic_icon(color: str = "#8b98a8", size: int = 34) -> QIcon:
    """Plochý mikrofon — stejný tah jako ikony v RedLine."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    pen = QPen(QColor(color))
    pen.setWidthF(max(1.8, size * 0.085))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    capsule_w = size * 0.30
    capsule_h = size * 0.44
    painter.drawRoundedRect(
        QRectF((size - capsule_w) / 2, size * 0.12, capsule_w, capsule_h),
        capsule_w / 2,
        capsule_w / 2,
    )

    painter.drawArc(
        QRectF(size * 0.22, size * 0.28, size * 0.56, size * 0.44),
        180 * 16,
        180 * 16,
    )
    painter.drawLine(
        QPointF(size / 2, size * 0.72),
        QPointF(size / 2, size * 0.86),
    )
    painter.end()

    return QIcon(pixmap)


def stop_icon(color: str = "#ffffff", size: int = 34) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QBrush(QColor(color)))
    painter.setPen(Qt.PenStyle.NoPen)
    side = size * 0.40
    painter.drawRoundedRect(
        QRectF((size - side) / 2, (size - side) / 2, side, side), 3, 3
    )
    painter.end()

    return QIcon(pixmap)
