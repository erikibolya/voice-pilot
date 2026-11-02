"""Spuštění grafického režimu."""

from __future__ import annotations

import sys

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication

from ..engine import Engine
from .icons import app_icon
from .tray import Tray
from .window import MainWindow


class EventBridge(QObject):
    """Převádí události z jádra (mohou přijít z vlákna) do hlavního vlákna Qt."""

    event = Signal(dict)


class HotkeyBridge(QObject):
    """Přemostí globální klávesu z vlákna pynputu do hlavního vlákna Qt."""

    pressed = Signal()


def run(cfg) -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("voice-pilot")
    app.setApplicationDisplayName("voice-pilot")
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)

    _set_app_id("dev.erikibolya.voicepilot")

    bridge = EventBridge()
    engine = Engine(cfg, on_event=bridge.event.emit)

    window = MainWindow(cfg, engine)
    tray = Tray(window, engine)
    bridge.event.connect(window.receive)
    bridge.event.connect(tray.receive)
    tray.show()

    hotkey = HotkeyBridge()
    hotkey.pressed.connect(engine.toggle)
    listener = _start_hotkey(cfg.hotkey, hotkey)

    window.show()

    try:
        return app.exec()
    finally:
        if listener is not None:
            listener.stop()
        engine.shutdown()


def _start_hotkey(hotkey: str, bridge: HotkeyBridge):
    from pynput import keyboard

    combo = hotkey if hotkey.startswith("<") else f"<{hotkey}>"
    try:
        listener = keyboard.GlobalHotKeys({combo: bridge.pressed.emit})
        listener.start()
        return listener
    except Exception:
        return None


def _set_app_id(app_id: str) -> None:
    """Aby Windows ukazovaly správnou ikonu v hlavním panelu."""
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def render_png(path: str, cfg, theme: str = "dark", size: tuple[int, int] = (1040, 680)) -> str:
    """Vykreslí okno do PNG bez zobrazení na ploše.

    Na snímky obrazovky se nedá spolehnout — okno může být zakryté jinou
    aplikací. `QWidget.grab()` kreslí přímo do paměti.
    """
    app = QApplication.instance() or QApplication(sys.argv)

    bridge = EventBridge()
    engine = Engine(cfg, on_event=bridge.event.emit)
    window = MainWindow(cfg, engine)
    bridge.event.connect(window.receive)

    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.resize(*size)
    window.apply_theme(theme)
    _demo_state(window)

    window.show()
    app.processEvents()

    pixmap = window.grab()
    ok = pixmap.save(path)
    window.really_quit()
    app.processEvents()

    if not ok:
        raise RuntimeError(f"snímek se nepodařilo uložit do {path}")
    return path


def _demo_state(window) -> None:
    """Ukázkový obsah, aby snímek nebyl prázdný."""
    window.receive(
        {
            "type": "heard",
            "text": "Otevři mi složku s fakturami a řekni, kolik tam je souborů.",
            "seconds": 4.2,
        }
    )
    window.receive(
        {
            "type": "screen",
            "elements": 42,
            "window": "Faktury – Průzkumník souborů",
        }
    )
    window.receive(
        {
            "type": "answer",
            "text": (
                "Ve složce Faktury je dvanáct PDF, nejnovější je z prvního "
                "listopadu. Chceš je seřadit podle data?"
            ),
        }
    )
    window.receive({"type": "state", "value": "idle", "detail": ""})
    window.receive({"type": "log", "text": "Připraven."})
