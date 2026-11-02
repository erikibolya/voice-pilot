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


def test_snapshot_precte_aktivni_okno(cfg):
    snap = eyes.snapshot(cfg)

    assert snap.active_title, "aktivní okno musí mít název"
    assert isinstance(snap.elements, list)
    assert all(e.index == i + 1 for i, e in enumerate(snap.elements)), "čísla musí jít popořadě"


def test_prvky_maji_rozumnou_geometrii(cfg):
    snap = eyes.snapshot(cfg)
    for element in snap.elements:
        assert element.w > 0 and element.h > 0, f"prvek {element.index} nemá rozměr"
        assert element.name.strip(), f"prvek {element.index} nemá název"
        cx, cy = element.center
        assert element.x <= cx <= element.x + element.w


def test_render_obsahuje_nazev_okna(cfg):
    snap = eyes.snapshot(cfg)
    text = snap.render()
    assert "AKTIVNÍ OKNO" in text
    assert snap.active_title in text


def test_by_index_najde_prvek(cfg):
    snap = eyes.snapshot(cfg)
    if not snap.elements:
        pytest.skip("na ploše není žádný čitelný prvek")
    first = snap.elements[0]
    assert snap.by_index(first.index) is first
    assert snap.by_index(9999) is None


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
    from pilot.app import Pilot

    receno = []
    monkeypatch.setattr(Pilot, "_say", lambda self, text: receno.append(text))

    pilot = Pilot(cfg)
    pilot.handle("Co máš na obrazovce?")

    assert receno, "asistent nic neřekl"
    assert len(receno[0]) > 5


@pytest.mark.slow
def test_pilot_si_pamatuje_predchozi_vetu(cfg):
    from pilot.brain import Brain

    brain = Brain(cfg)
    brain.history.append(("jak se jmenuješ?", "Jmenuju se Pilot."))
    prompt = brain._build_prompt("a co děláš?", eyes.snapshot(cfg))

    assert "Jmenuju se Pilot." in prompt
    assert "a co děláš?" in prompt
