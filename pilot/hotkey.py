"""Globální klávesa pro diktování — drží se, ne přepíná.

Dřív se mačkalo F9 a stav se přepínal. Teď se klávesa (nebo kombinace)
**drží**: stisk začne nahrávat, puštění ukončí. Je to stejné jako u vysílačky
a nedá se zapomenout nahrávání vypnout.

Syntetické stisky (z jiných aplikací) se ignorují — jinak by cizí program
mohl spustit nahrávání.
"""

from __future__ import annotations

import time
from typing import Callable

from pynput import keyboard

MODIFIERS = {
    "ctrl": keyboard.Key.ctrl,
    "alt": keyboard.Key.alt,
    "shift": keyboard.Key.shift,
    "win": keyboard.Key.cmd,
}

SPECIAL = {
    "space": keyboard.Key.space,
    "enter": keyboard.Key.enter,
    "tab": keyboard.Key.tab,
    "esc": keyboard.Key.esc,
    "backspace": keyboard.Key.backspace,
    "delete": keyboard.Key.delete,
    "up": keyboard.Key.up,
    "down": keyboard.Key.down,
    "left": keyboard.Key.left,
    "right": keyboard.Key.right,
    "home": keyboard.Key.home,
    "end": keyboard.Key.end,
    "pageup": keyboard.Key.page_up,
    "pagedown": keyboard.Key.page_down,
    "insert": keyboard.Key.insert,
    "menu": keyboard.Key.menu,
}

# pynput hlásí levou a pravou variantu zvlášť
NORMALIZACE = {
    "ctrl_l": "ctrl", "ctrl_r": "ctrl",
    "alt_l": "alt", "alt_r": "alt", "alt_gr": "alt",
    "shift_l": "shift", "shift_r": "shift",
    "cmd_l": "win", "cmd_r": "win",
}


def parse(combo: str) -> list[str]:
    """`ctrl+alt+space` -> ['ctrl', 'alt', 'space']."""
    casti = [c.strip().lower() for c in combo.replace(" ", "").split("+")]
    casti = [c for c in casti if c]
    if not casti:
        raise ValueError("prázdná kombinace")
    return casti


def je_bezpecna(combo: str) -> bool:
    """Samotné písmeno by se spouštělo psaním — povolujeme jen s modifikátorem."""
    try:
        casti = parse(combo)
    except ValueError:
        return False

    if len(casti) > 1:
        return True

    jedina = casti[0]
    return jedina.startswith("f") or jedina in SPECIAL


def _nazev(klavesa) -> str:
    """Převede klávesu z pynputu na náš název (`ctrl`, `space`, `a`)."""
    if isinstance(klavesa, keyboard.Key):
        jmeno = klavesa.name
        return NORMALIZACE.get(jmeno, jmeno)

    try:
        znak = klavesa.char
    except AttributeError:
        return str(klavesa)

    return znak.lower() if znak else ""


def _na_klavesu(nazev: str):
    if nazev in MODIFIERS:
        return MODIFIERS[nazev]
    if nazev in SPECIAL:
        return SPECIAL[nazev]
    if len(nazev) == 1:
        return nazev
    if nazev.startswith("f") and nazev[1:].isdigit():
        return getattr(keyboard.Key, nazev, None)
    return None


class HotkeyWatcher:
    """Sleduje kombinaci kdekoliv v systému a hlásí začátek a konec držení."""

    def __init__(
        self,
        combo: str,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
    ):
        self.combo = combo
        self.on_start = on_start
        self.on_stop = on_stop

        self._pozadovane = set(parse(combo))
        self._stisknute: set[str] = set()
        self._aktivni = False
        self._konec_v = 0.0
        self._injektovano = False
        self._listener: keyboard.Listener | None = None

    # ---------------------------------------------------------------- běh

    def start(self) -> bool:
        try:
            self._listener = keyboard.Listener(
                on_press=self._press,
                on_release=self._release,
                win32_event_filter=self._filtr,
            )
            self._listener.start()
            return True
        except Exception:
            self._listener = None
            return False

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    @property
    def is_active(self) -> bool:
        return self._aktivni

    # ------------------------------------------------------------ události

    def _filtr(self, msg, data) -> bool:
        """Zapamatuje, jestli událost vyrobil program (ne člověk)."""
        try:
            self._injektovano = bool(data.flags & 0x10)  # LLKHF_INJECTED
        except Exception:
            self._injektovano = False
        return True  # událost propustíme dál, jen ji nebudeme počítat

    def _press(self, klavesa) -> None:
        if self._injektovano:
            return

        nazev = _nazev(klavesa)
        if not nazev:
            return

        self._stisknute.add(nazev)

        if self._aktivni:
            return
        if time.monotonic() - self._konec_v < 0.25:
            return  # potlačení dvojího spuštění
        if not self._pozadovane.issubset(self._stisknute):
            return

        self._aktivni = True
        try:
            self.on_start()
        except Exception:
            pass

    def _release(self, klavesa) -> None:
        nazev = _nazev(klavesa)
        self._stisknute.discard(nazev)

        if not self._aktivni:
            return

        # ukončíme, jakmile pustíš kteroukoli klávesu z kombinace
        if nazev in self._pozadovane:
            self._aktivni = False
            self._konec_v = time.monotonic()
            try:
                self.on_stop()
            except Exception:
                pass


def popis(combo: str) -> str:
    """`ctrl+alt+space` -> `Ctrl+Alt+Space` pro rozhraní."""
    nazvy = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win",
             "space": "Space", "esc": "Esc", "pageup": "PageUp", "pagedown": "PageDown"}
    return "+".join(
        nazvy.get(c, c.upper() if len(c) == 1 else c.capitalize())
        for c in parse(combo)
    )
