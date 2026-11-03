"""Spuštění grafického režimu."""

from __future__ import annotations

import sys

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication

from ..engine import Engine
from ..hotkey import HotkeyWatcher
from .confirm import ConfirmBar, Confirmer
from .icons import app_icon
from .overlay import Overlays
from .tray import Tray
from .window import MainWindow


class EventBridge(QObject):
    """Převádí události z jádra (mohou přijít z vlákna) do hlavního vlákna Qt."""

    event = Signal(dict)


class HotkeyBridge(QObject):
    """Přemostí globální klávesy z vlákna pynputu do hlavního vlákna Qt."""

    started = Signal()
    stopped = Signal()
    confirm = Signal()
    cancel = Signal()


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
    overlays = Overlays()

    bridge.event.connect(window.receive)
    bridge.event.connect(tray.receive)
    tray.show()

    confirmer = Confirmer()
    bar = ConfirmBar(confirmer)  # noqa: F841 — drží se, dokud běží aplikace
    engine.confirmer = confirmer.ask

    # --- klávesa: drží se, po puštění se přestane nahrávat -----------------
    keys = HotkeyBridge()

    keys.started.connect(engine.start_dictation)
    keys.stopped.connect(engine.stop_dictation)
    keys.confirm.connect(lambda: confirmer.answer(True))

    def zrus() -> None:
        """Ctrl+Alt+Esc: zruší čekající potvrzení, jinak přeruší celý úkol."""
        if confirmer.pending:
            confirmer.answer(False)
        else:
            engine.abort()

    keys.cancel.connect(zrus)

    diktovani = {"zapnuto": False}

    def prekryvy(payload: dict) -> None:
        """Překryvy se řídí stavem, ne vstupní cestou — platí i pro tlačítko."""
        typ = payload.get("type")

        if typ == "dictation":
            diktovani["zapnuto"] = bool(payload.get("on"))
            if diktovani["zapnuto"]:
                overlays.begin_dictation()
            else:
                overlays.end_dictation()
            return

        if typ == "state" and not diktovani["zapnuto"]:
            if payload.get("value") == "listening":
                overlays.begin_dictation()
            else:
                overlays.end_dictation()
        elif typ == "control":
            overlays.show_control(bool(payload.get("on")))

    engine.on_level = overlays.level
    bridge.event.connect(prekryvy)

    # most pro rozšíření v prohlížeči (webové stránky)
    try:
        from .. import bridge as _bridge

        _bridge.most().start()
    except Exception:
        pass

    # Oba modely se načítají v jednom vlákně a popořadě: Whisper i Piper
    # inicializují CUDA/DLL a souběžně to umí shodit proces.
    def prehrej() -> None:
        try:
            engine.transcriber.prewarm()
        except Exception:
            pass
        try:
            engine.speaker.prewarm()
        except Exception:
            pass

    import threading

    threading.Thread(target=prehrej, daemon=True).start()

    watcher = HotkeyWatcher(cfg.hotkey, keys.started.emit, keys.stopped.emit)
    started = watcher.start()

    if started:
        _start_confirm_hotkeys(keys)
    else:
        window.receive({"type": "log", "text": "Globální klávesu se nepodařilo zaregistrovat."})

    window.show()

    try:
        return app.exec()
    finally:
        watcher.stop()
        engine.shutdown()


def _start_confirm_hotkeys(bridge: HotkeyBridge):
    """Potvrzení a zrušení akce — samostatné, vždycky aktivní."""
    from pynput import keyboard

    try:
        listener = keyboard.GlobalHotKeys(
            {
                "<ctrl>+<alt>+enter": bridge.confirm.emit,
                "<ctrl>+<alt>+esc": bridge.cancel.emit,
            }
        )
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
