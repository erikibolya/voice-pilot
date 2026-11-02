"""Vizuální styl voice-pilotu.

Barevné tokeny jsou převzaté z RedLine (`desktop/ui/app.css`), aby obě
aplikace vypadaly jako jedna rodina: tmavé pozadí #0d1117, panely po
vrstvách, osmičkový rádius, akcentní modrá a 13px UI písmo.
"""

from __future__ import annotations

DARK = {
    "bg": "#0d1117",
    "panel": "#151a21",
    "panel2": "#1b222b",
    "panel3": "#232c37",
    "border": "#2a3441",
    "border_soft": "#222a34",
    "text": "#e6edf3",
    "muted": "#8b98a8",
    "accent": "#2f81f7",
    "accent_soft": "#1f4fa0",
    "ok": "#16a34a",
    "warn": "#d29922",
    "danger": "#e11d48",
    "radius": "8px",
    "font": "Segoe UI",
}

LIGHT = {
    "bg": "#eef2f7",
    "panel": "#ffffff",
    "panel2": "#f6f8fb",
    "panel3": "#e9eef5",
    "border": "#d5dde8",
    "border_soft": "#e4eaf2",
    "text": "#1e293b",
    "muted": "#64748b",
    "accent": "#0369a1",
    "accent_soft": "#bae6fd",
    "ok": "#15803d",
    "warn": "#b45309",
    "danger": "#be123c",
    "radius": "8px",
    "font": "Segoe UI",
}


def palette(theme: str) -> dict[str, str]:
    return LIGHT if theme == "light" else DARK


def stylesheet(theme: str = "dark") -> str:
    c = palette(theme)
    return f"""
* {{
    font-family: "{c['font']}", system-ui, sans-serif;
    font-size: 13px;
    outline: none;
}}

QMainWindow, QDialog {{
    background: {c['bg']};
}}

QWidget {{
    color: {c['text']};
}}

/* ---------- horní lišta ---------- */
#Header {{
    background: {c['panel']};
    border-bottom: 1px solid {c['border']};
}}

#AppName {{
    font-size: 14px;
    font-weight: 600;
}}

#AppSub {{
    color: {c['muted']};
    font-size: 11px;
}}

/* ---------- levá kolejnice ---------- */
#Rail {{
    background: {c['panel']};
    border-right: 1px solid {c['border']};
}}

#RailTitle {{
    color: {c['muted']};
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .4px;
}}

/* ---------- karty ---------- */
#Card {{
    background: {c['panel2']};
    border: 1px solid {c['border']};
    border-radius: {c['radius']};
}}

#Stage {{
    background: {c['bg']};
}}

/* ---------- tlačítka ---------- */
QPushButton {{
    background: {c['panel2']};
    border: 1px solid {c['border']};
    border-radius: {c['radius']};
    padding: 6px 11px;
    color: {c['text']};
}}
QPushButton:hover {{
    background: {c['panel3']};
}}
QPushButton:pressed {{
    background: {c['panel3']};
}}
QPushButton:disabled {{
    color: {c['muted']};
    background: {c['panel2']};
}}

QPushButton[role="primary"] {{
    background: {c['accent']};
    border-color: {c['accent']};
    color: #ffffff;
    font-weight: 600;
}}
QPushButton[role="primary"]:hover {{
    background: {c['accent']};
    border-color: {c['text']};
}}

QPushButton[role="danger"] {{
    background: {c['danger']};
    border-color: {c['danger']};
    color: #ffffff;
    font-weight: 600;
}}

QPushButton[role="ghost"] {{
    background: transparent;
    border-color: transparent;
    color: {c['muted']};
}}
QPushButton[role="ghost"]:hover {{
    background: {c['panel3']};
    color: {c['text']};
}}

/* čtvercová ikonová tlačítka 32x32 */
QPushButton[role="icon"] {{
    min-width: 30px;
    max-width: 30px;
    min-height: 30px;
    max-height: 30px;
    padding: 0;
    border-radius: 6px;
    background: transparent;
    border-color: transparent;
    color: {c['muted']};
    font-size: 15px;
}}
QPushButton[role="icon"]:hover {{
    background: {c['panel3']};
    color: {c['text']};
}}

/* ---------- velké tlačítko mikrofonu ---------- */
QPushButton#MicButton {{
    border-radius: 44px;
    min-width: 88px;
    max-width: 88px;
    min-height: 88px;
    max-height: 88px;
    padding: 0;
    font-size: 26px;
    background: {c['panel2']};
    border: 1px solid {c['border']};
    color: {c['muted']};
}}
QPushButton#MicButton:hover {{
    border-color: {c['accent']};
    color: {c['text']};
}}
QPushButton#MicButton[state="listening"] {{
    background: {c['danger']};
    border-color: {c['danger']};
    color: #ffffff;
}}
QPushButton#MicButton[state="thinking"] {{
    border-color: {c['warn']};
    color: {c['warn']};
}}
QPushButton#MicButton[state="speaking"] {{
    border-color: {c['accent']};
    color: {c['accent']};
}}

/* ---------- texty ---------- */
#StateLabel {{
    font-size: 15px;
    font-weight: 600;
}}

#Muted {{
    color: {c['muted']};
}}

#Transcript {{
    font-size: 20px;
    font-weight: 600;
    line-height: 1.35;
}}

#Answer {{
    font-size: 14px;
    line-height: 1.5;
}}

/* ---------- vstupy ---------- */
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {{
    background: {c['panel2']};
    border: 1px solid {c['border']};
    border-radius: {c['radius']};
    padding: 6px 9px;
    selection-background-color: {c['accent']};
}}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border-color: {c['accent']};
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
}}
QComboBox QAbstractItemView {{
    background: {c['panel2']};
    border: 1px solid {c['border']};
    selection-background-color: {c['panel3']};
    outline: none;
}}

/* ---------- seznam ---------- */
QListWidget {{
    background: transparent;
    border: none;
    outline: none;
}}
QListWidget::item {{
    padding: 7px 9px;
    border-radius: 6px;
    margin-bottom: 2px;
}}
QListWidget::item:hover {{
    background: {c['panel2']};
}}
QListWidget::item:selected {{
    background: {c['panel3']};
    color: {c['text']};
}}

/* ---------- potvrzovací panel ---------- */
#ConfirmBar {{
    background: {c['panel2']};
    border: 1px solid {c['border']};
    border-radius: {c['radius']};
}}
#ConfirmTitle {{
    font-size: 14px;
    font-weight: 600;
}}

/* ---------- posuvníky ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {c['panel3']};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {c['border']};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ---------- stavový pruh ---------- */
#StatusBar {{
    background: {c['panel']};
    border-top: 1px solid {c['border']};
}}
#StatusBar QLabel {{
    color: {c['muted']};
    font-size: 11px;
}}

/* ---------- odznaky ---------- */
#Badge {{
    border-radius: 9px;
    padding: 2px 8px;
    font-size: 10px;
    font-weight: 600;
    background: {c['panel3']};
    color: {c['muted']};
}}
#Badge[kind="ok"] {{
    background: {c['ok']};
    color: #ffffff;
}}
#Badge[kind="accent"] {{
    background: {c['accent']};
    color: #ffffff;
}}
#Badge[kind="danger"] {{
    background: {c['danger']};
    color: #ffffff;
}}

/* ---------- menu a tooltip ---------- */
QMenu {{
    background: {c['panel2']};
    border: 1px solid {c['border']};
    border-radius: {c['radius']};
    padding: 5px;
}}
QMenu::item {{
    padding: 6px 22px 6px 10px;
    border-radius: 5px;
}}
QMenu::item:selected {{
    background: {c['panel3']};
}}
QMenu::separator {{
    height: 1px;
    background: {c['border']};
    margin: 5px 8px;
}}
QToolTip {{
    background: {c['panel3']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: 5px;
    padding: 4px 7px;
}}
"""
