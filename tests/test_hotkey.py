"""Testy klávesy pro diktování — držení a puštění."""

from __future__ import annotations

import pytest
from pynput import keyboard

from pilot import hotkey
from pilot.hotkey import HotkeyWatcher


def test_parsovani_kombinace():
    assert hotkey.parse("ctrl+alt+space") == ["ctrl", "alt", "space"]
    assert hotkey.parse(" F9 ") == ["f9"]
    assert hotkey.parse("ctrl+shift+f10") == ["ctrl", "shift", "f10"]


def test_prazdna_kombinace_selze():
    with pytest.raises(ValueError):
        hotkey.parse("   ")


def test_samotne_pismeno_by_se_spoustelo_psanim():
    assert not hotkey.je_bezpecna("a")
    assert not hotkey.je_bezpecna("1")


def test_funkcni_a_specialni_klavesy_jsou_v_poradku():
    assert hotkey.je_bezpecna("f9")
    assert hotkey.je_bezpecna("space")
    assert hotkey.je_bezpecna("ctrl+a")
    assert hotkey.je_bezpecna("ctrl+alt+space")


def test_popis_pro_cteni():
    assert hotkey.popis("ctrl+alt+space") == "Ctrl+Alt+Space"
    assert hotkey.popis("f9") == "F9"


def _watcher(combo="ctrl+alt+space"):
    udalosti: list[str] = []
    w = HotkeyWatcher(
        combo,
        lambda: udalosti.append("start"),
        lambda: udalosti.append("stop"),
    )
    w._injektovano = False
    return w, udalosti


def test_drzeni_spusti_az_po_cele_kombinaci():
    w, udalosti = _watcher()

    w._press(keyboard.Key.ctrl_l)
    assert udalosti == []
    w._press(keyboard.Key.alt_l)
    assert udalosti == []
    w._press(keyboard.Key.space)

    assert udalosti == ["start"]


def test_pusteni_ukonci():
    w, udalosti = _watcher()
    w._press(keyboard.Key.ctrl_l)
    w._press(keyboard.Key.alt_l)
    w._press(keyboard.Key.space)

    w._release(keyboard.Key.space)

    assert udalosti == ["start", "stop"]
    assert not w.is_active


def test_pusteni_jine_klavesy_neukonci():
    w, udalosti = _watcher()
    w._press(keyboard.Key.ctrl_l)
    w._press(keyboard.Key.alt_l)
    w._press(keyboard.Key.space)

    w._release(keyboard.Key.f5)

    assert udalosti == ["start"]


def test_injektovana_klavesa_se_ignoruje():
    """Cizí aplikace nesmí spustit nahrávání."""
    w, udalosti = _watcher()

    w._injektovano = True
    w._press(keyboard.Key.ctrl_l)
    w._press(keyboard.Key.alt_l)
    w._press(keyboard.Key.space)

    assert udalosti == []
    assert not w.is_active


def test_bez_modifikatoru_staci_jedna_klavesa():
    w, udalosti = _watcher("f9")

    w._press(keyboard.Key.f9)
    assert udalosti == ["start"]

    w._release(keyboard.Key.f9)
    assert udalosti == ["start", "stop"]


def test_rychle_druhe_stisknuti_se_potlaci():
    """Ať se nahrávání nespustí dvakrát za sebou omylem."""
    w, udalosti = _watcher("f9")

    w._press(keyboard.Key.f9)
    w._release(keyboard.Key.f9)
    w._press(keyboard.Key.f9)

    assert udalosti == ["start", "stop"]


def test_shift_se_nerovna_velkemu_pismenu():
    w, udalosti = _watcher("ctrl+a")

    w._injektovano = False
    w._press(keyboard.Key.ctrl_l)
    w._press("a")

    assert udalosti == ["start"]
