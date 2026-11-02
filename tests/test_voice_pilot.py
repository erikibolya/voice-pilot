"""Testy voice-pilotu.

Puštění:  .venv\\Scripts\\python.exe -m pytest -q
Pomalé testy (model, hlas):  .venv\\Scripts\\python.exe -m pytest -q -m "not slow"
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import miniaudio
import numpy as np
import pytest

from pilot import config, eyes
from pilot.config import Config

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def cfg() -> Config:
    return config.load()


# ---------------------------------------------------------------- nastavení


def test_config_se_ulozi_a_nacte(tmp_path, monkeypatch):
    target = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", target)

    c = config.load()
    c.model_id = "nejaky-model"
    c.save()

    again = config.load()
    assert again.model_id == "nejaky-model"
    assert again.language == "cs"


def test_neznamy_klic_v_configu_neshodi_nacteni(tmp_path, monkeypatch):
    target = tmp_path / "config.json"
    target.write_text('{"model_id": "x", "neco_noveho": 1}', encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_PATH", target)

    assert config.load().model_id == "x"


# -------------------------------------------------------------------- oči


@pytest.mark.desktop
def test_snapshot_precte_aktivni_okno(cfg):
    snap = eyes.snapshot(cfg)

    assert snap.active_title, "aktivní okno musí mít název"
    assert isinstance(snap.elements, list)
    assert all(e.index == i + 1 for i, e in enumerate(snap.elements)), "čísla musí jít popořadě"


@pytest.mark.desktop
def test_prvky_maji_rozumnou_geometrii(cfg):
    snap = eyes.snapshot(cfg)
    for element in snap.elements:
        assert element.w > 0 and element.h > 0, f"prvek {element.index} nemá rozměr"
        assert element.name.strip(), f"prvek {element.index} nemá název"
        cx, cy = element.center
        assert element.x <= cx <= element.x + element.w


@pytest.mark.desktop
def test_render_obsahuje_nazev_okna(cfg):
    snap = eyes.snapshot(cfg)
    text = snap.render()
    assert "AKTIVNÍ OKNO" in text
    assert snap.active_title in text


@pytest.mark.desktop
def test_by_index_najde_prvek(cfg):
    snap = eyes.snapshot(cfg)
    if not snap.elements:
        pytest.skip("na ploše není žádný čitelný prvek")
    first = snap.elements[0]
    assert snap.by_index(first.index) is first
    assert snap.by_index(9999) is None


@pytest.mark.desktop
def test_screenshot_se_ulozi():
    path = eyes.screenshot("pytest")
    assert path.exists()
    assert path.stat().st_size > 10_000, "screenshot je podezřele malý"


# ------------------------------------------------------------------- hlas


@pytest.mark.slow
def test_edge_vyrobi_zvuk(cfg):
    from pilot.tts import Speaker

    path = Speaker(cfg)._edge("Toto je test hlasu.")
    assert path.exists()
    assert path.stat().st_size > 1000


def test_prehravac_zvlada_cestu_s_diakritikou(cfg):
    """Regrese: C knihovny na Windows neumí cestu s českou diakritikou."""
    from pilot.tts import Speaker

    speaker = Speaker(cfg)
    path = speaker._edge("Test.")
    assert any(ord(ch) > 127 for ch in str(path)), "test má smysl jen na cestě s diakritikou"

    decoded = miniaudio.decode(
        path.read_bytes(),
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,
    )
    assert len(decoded.samples) > 0


# -------------------------------------------------------------------- uši


def _nahrat(text: str, sample_rate: int) -> np.ndarray:
    import edge_tts

    out = ROOT / "cache" / "tts" / "pytest_stt.mp3"
    out.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(edge_tts.Communicate(text, "cs-CZ-VlastaNeural").save(str(out)))

    decoded = miniaudio.decode(
        out.read_bytes(),
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,
        sample_rate=sample_rate,
    )
    pcm = np.frombuffer(decoded.samples, dtype=np.int16)
    return (pcm.astype(np.float32) / 32768.0).copy()


@pytest.mark.slow
def test_whisper_prepise_cestinu(cfg):
    from pilot.stt import Transcriber

    veta = "Otevři mi prosím složku s fakturami."
    audio = _nahrat(veta, cfg.sample_rate)

    text = Transcriber(cfg).transcribe(audio)

    zdrojova = set(veta.lower().replace(",", "").split())
    ziskana = set(text.lower().replace(",", "").split())
    shoda = len(zdrojova & ziskana) / len(zdrojova)
    assert shoda >= 0.8, f"přepis nesedí ({shoda:.0%}): {text!r}"


def test_ticho_se_zahodi(cfg):
    from pilot.stt import Transcriber

    ticho = np.zeros(cfg.sample_rate * 3, dtype=np.float32)
    assert Transcriber(cfg).transcribe(ticho) == ""


def test_trim_silence_orizne_okraje():
    from pilot.stt import trim_silence

    audio = np.zeros(16000, dtype=np.float32)
    audio[6000:9000] = 0.5
    orezane = trim_silence(audio)

    assert orezane.size < audio.size
    assert orezane.size >= 3000


def test_normalize_srovna_tichy_mikrofon():
    from pilot.stt import normalize

    tichy = np.full(1000, 0.01, dtype=np.float32)
    out = normalize(tichy)

    assert float(np.abs(out).max()) == pytest.approx(0.9, rel=1e-3)


def test_normalize_nedela_nic_s_tisem():
    from pilot.stt import normalize

    ticho = np.zeros(500, dtype=np.float32)
    assert normalize(ticho).size == 500
    assert float(np.abs(normalize(ticho)).max()) == 0.0


# ------------------------------------------------------------------ mozek


@pytest.mark.slow
def test_model_odpovi_cesky(cfg):
    from pilot.oc import OpenCode

    client = OpenCode(cfg.service_url, cfg.service_password_file, cfg.provider_id, cfg.model_id)
    odpoved = client.generate("Odpověz jednou větou česky: jak se máš?")

    assert odpoved
    assert any(ch in odpoved for ch in "áčďéěíňóřšťúůýž"), "odpověď nevypadá česky"


# --------------------------------------------------------------- kontrola mozku


@pytest.mark.desktop
def test_preflight_najde_bezici_opencode(cfg):
    from pilot.oc import OpenCode

    client = OpenCode(cfg.service_url, cfg.service_password_file, cfg.provider_id, cfg.model_id)
    ok, detail = client.preflight()

    assert ok, detail
    assert "OpenCode" in detail


def test_preflight_hlasi_kdyz_sluzba_nebezi(cfg):
    from pilot.oc import OpenCode

    client = OpenCode("http://127.0.0.1:59999", cfg.service_password_file, "x", "y")
    ok, detail = client.preflight()

    assert not ok
    assert "neběží" in detail


def test_preflight_hlasi_chybejici_prihlaseni(tmp_path, cfg):
    from pilot.oc import OpenCode

    client = OpenCode(cfg.service_url, str(tmp_path / "nic.json"), "x", "y")
    ok, detail = client.preflight()

    assert not ok
    assert "přihlášení" in detail


@pytest.mark.slow
def test_cely_kolo_od_otazky_k_odpovedi(cfg, monkeypatch):
    """Uživatelský scénář: řekne otázku, dostane odpověď o obrazovce."""
    from pilot.engine import IDLE, Engine

    udalosti: list[dict] = []
    engine = Engine(cfg, on_event=udalosti.append)

    receno: list[str] = []
    monkeypatch.setattr(engine.speaker, "say", lambda text: receno.append(text))

    engine.ask("Co máš na obrazovce?", background=False)

    odpovedi = [u for u in udalosti if u["type"] == "answer"]
    assert odpovedi, "asistent nic neodpověděl"
    assert len(odpovedi[0]["text"]) > 5

    assert receno == [odpovedi[0]["text"]], "odpověď se nepřečetla nahlas"
    assert engine.state == IDLE, "po dokončení se má vrátit do klidu"


@pytest.mark.slow
def test_kolo_se_uklidí_po_dokonceni(cfg, monkeypatch):
    from pilot.engine import Engine

    engine = Engine(cfg, on_event=lambda e: None)
    monkeypatch.setattr(engine.speaker, "say", lambda text: None)

    engine.ask("Co je na obrazovce?", background=False)

    assert engine.state == "idle"
    assert not engine.is_busy


# --------------------------------------------------------------- aktualizace


@pytest.mark.parametrize(
    "kandidat,aktualni,ocekavano",
    [
        ("v0.2.1", "0.2.0", True),
        ("v0.3.0", "0.2.9", True),
        ("v0.2.0", "0.2.0", False),
        ("v0.1.9", "0.2.0", False),
        ("v1.0.0", "0.9.9", True),
        ("v0.10.0", "0.9.0", True),
        ("0.2.1", "0.2.0", True),
    ],
)
def test_porovnani_verzi(kandidat, aktualni, ocekavano):
    from pilot.updater import is_newer

    assert is_newer(kandidat, aktualni) is ocekavano


def test_verze_se_parsuji_spravne():
    from pilot.updater import parse_version

    assert parse_version("v0.2.1") == (0, 2, 1)
    assert parse_version("0.2.1-dev.3") == (0, 2, 1)
    assert parse_version("nesmysl") == (0,)


def test_kontrola_aktualizaci_nezhavari_bez_site(monkeypatch):
    from pilot import updater

    def explode(*args, **kwargs):
        raise OSError("bez sítě")

    monkeypatch.setattr(updater.urllib.request, "urlopen", explode)

    update, message = updater.check()
    assert update is None
    assert "GitHub" in message


# ---------------------------------------------------------------------- okno


def _qt():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize(
    "modul",
    [
        "pilot.engine",
        "pilot.updater",
        "pilot.theme",
        "pilot.ui.icons",
        "pilot.ui.settings",
        "pilot.ui.window",
        "pilot.ui.tray",
        "pilot.ui.app",
    ],
)
def test_modul_jde_importovat(modul):
    """Regrese: syntaktická chyba v UI modulu projde testy, které ho neimportují."""
    import importlib

    importlib.import_module(modul)


def test_okno_se_postavi_a_umi_stav(cfg, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    from pilot.engine import Engine
    from pilot.ui.window import MainWindow

    app = _qt()
    window = MainWindow(cfg, Engine(cfg, on_event=lambda e: None))

    try:
        assert window.windowTitle() == "voice-pilot"

        window.receive({"type": "state", "value": "listening", "detail": ""})
        assert "Poslouchám" in window.state_label.text()
        assert window.mic_button.property("state") == "listening"

        window.receive({"type": "heard", "text": "kolik je hodin"})
        assert window.transcript.text() == "kolik je hodin"
        assert window.history.count() == 1

        window.receive({"type": "answer", "text": "Nevím přesně."})
        assert window.answer.text() == "Nevím přesně."
    finally:
        window.really_quit()
        app.processEvents()


def test_okno_prepne_tema(cfg, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    from pilot.engine import Engine
    from pilot.ui.window import MainWindow

    app = _qt()
    window = MainWindow(cfg, Engine(cfg, on_event=lambda e: None))

    try:
        assert window.theme == "dark"
        dark = window.styleSheet()

        window.toggle_theme()
        assert window.theme == "light"
        light = window.styleSheet()

        assert dark != light
        assert "#0d1117" in dark
        assert "#eef2f7" in light
    finally:
        window.really_quit()
        app.processEvents()


@pytest.mark.slow
def test_pilot_si_pamatuje_predchozi_vetu(cfg):
    from pilot.brain import Brain

    brain = Brain(cfg)
    brain.history.append(("jak se jmenuješ?", "Jmenuju se Pilot."))
    prompt = brain._build_prompt("a co děláš?", eyes.snapshot(cfg))

    assert "Jmenuju se Pilot." in prompt
    assert "a co děláš?" in prompt
