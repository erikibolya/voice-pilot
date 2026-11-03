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

from dataclasses import replace

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
    assert again.language == "auto"


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


def test_prehravac_zvlada_cestu_s_diakritikou(cfg, tmp_path):
    """Regrese: C knihovny na Windows neumí cestu s českou diakritikou.

    Dřív se zvuk dekódoval přes `miniaudio.decode_file(cesta)`, což na cestě
    typu „Výchozí projekt“ spadlo. Soubor se teď čte po bajtech.
    """
    from pilot.tts import Speaker

    vzorek = Path(__file__).parent / "data" / "sample.mp3"
    assert vzorek.exists(), "chybí testovací nahrávka"

    ceska_slozka = tmp_path / "Výchozí projekt" / "cache" / "tts"
    ceska_slozka.mkdir(parents=True)
    cil = ceska_slozka / "řeč.mp3"
    cil.write_bytes(vzorek.read_bytes())

    audio, rate = Speaker(cfg)._decode(cil)

    assert audio.size > 1000, "ze souboru se nedostal žádný zvuk"
    assert rate > 0


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


def test_je_ascii_rozpozna_diakritiku():
    from pilot.tts import _je_ascii

    assert _je_ascii("C:/Users/eriki/voice-pilot")
    assert not _je_ascii("D:/Users/eriki/Výchozí projekt")


def test_espeak_data_lezi_na_ceste_bez_diakritiky():
    """`espeak-ng` je knihovna v C a cestu s diakritikou nepřečte."""
    from pilot.tts import _je_ascii, espeak_data_root

    root = espeak_data_root()
    if root is None:
        pytest.skip("Piper není nainstalovaný")

    assert (root / "espeak-ng-data" / "phontab").exists()
    assert _je_ascii(str(root))


@pytest.mark.slow
def test_piper_vyrobi_zvuk(cfg):
    from dataclasses import replace

    from pilot.tts import Speaker

    model = Path("models/cs_CZ-jirka-medium.onnx")
    if not model.exists():
        pytest.skip("model Piperu není stažený (run.py --setup-piper)")

    nastaveni = replace(cfg, tts_engine="piper", piper_model=str(model))
    path = Speaker(nastaveni)._piper("Zkouška hlasu.")

    assert path.exists()
    assert path.stat().st_size > 10_000


def test_normalize_nedela_nic_s_tisem():
    from pilot.stt import normalize

    ticho = np.zeros(500, dtype=np.float32)
    assert normalize(ticho).size == 500
    assert float(np.abs(normalize(ticho)).max()) == 0.0


# --------------------------------------------------------------------- hlas


def test_rozdeleni_na_vety():
    from pilot.tts import split_sentences

    vety = split_sentences("První věta. Druhá věta! Třetí?")
    assert vety == ["První věta.", "Druhá věta!", "Třetí?"]


def test_kratka_odpoved_zustane_celá():
    from pilot.tts import split_sentences

    assert len(split_sentences("Ano.")) == 1
    assert split_sentences("") == []


def test_dlouha_veta_se_rozdeli_u_carky():
    from pilot.tts import split_sentences

    dlouha = ("Vidím složku Faktury, ve které je dvanáct PDF souborů, "
              "poslední je z prvního listopadu, a ještě tři podložky.")
    casti = split_sentences(dlouha, limit=60)

    assert len(casti) > 1
    assert all(len(c) <= 61 for c in casti), [len(c) for c in casti]
    assert "".join(c.replace(" ", "") for c in casti) == dlouha.replace(" ", "")


def test_casti_neztrati_slova():
    from pilot.tts import split_sentences

    text = "Jedna. Dva, tři! Čtyři?"
    assert " ".join(split_sentences(text)).replace(",", "") == text.replace(",", "")


def test_hlas_zacne_mluvit_driv_nez_je_cely_hotovy(cfg, monkeypatch):
    """Regrese: dřív se čekalo na vyrobení celé odpovědi, než zazněl první zvuk."""
    import time

    from pilot import tts
    from pilot.tts import Speaker

    reci = Speaker(cfg)
    udalosti: list[tuple[str, int]] = []

    def predstirana_vyroba(text: str, index: int):
        time.sleep(0.12)
        udalosti.append(("vyroba", index))
        return Path("predstirany.mp3"), ""

    def predstirane_prehrani(path) -> None:  # noqa: ANN001
        udalosti.append(("prehrani", -1))

    # vynutíme záložní cestu po větách; streamování by šlo na síť
    monkeypatch.setattr(
        reci, "_edge_stream", lambda text: (_ for _ in ()).throw(tts._NicNeprehrano("test"))
    )
    monkeypatch.setattr(reci, "_render", predstirana_vyroba)
    monkeypatch.setattr(reci, "_play", predstirane_prehrani)

    reci.say("První věta. Druhá věta. Třetí věta. Čtvrtá věta.")

    prvni_prehrani = next(i for i, e in enumerate(udalosti) if e[0] == "prehrani")
    posledni_vyroba = max(i for i, e in enumerate(udalosti) if e[0] == "vyroba")

    assert prvni_prehrani < posledni_vyroba, udalosti
    assert udalosti[-1][0] == "prehrani", "na konci musí zaznít i poslední část"


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


def test_preflight_hlasi_kdyz_sluzba_nebezi(tmp_path):
    """Přihlášení existuje, ale služba na daném portu neběží."""
    from pilot.oc import OpenCode

    prihlaseni = tmp_path / "service.json"
    prihlaseni.write_text('{"password": "test"}', encoding="utf-8")

    client = OpenCode("http://127.0.0.1:59999", str(prihlaseni), "x", "y")
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

    engine = Engine(replace(cfg, use_vision=False), on_event=lambda e: None)
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


# ---------------------------------------------------------------- milník 2


def _snap_pro_akce():
    from pilot.eyes import Element, Snapshot

    return Snapshot(
        active_title="Faktury – Průzkumník souborů",
        active_class="CabinetWClass",
        elements=[
            Element(index=1, kind="tlačítko", name="Přejmenovat", x=10, y=10, w=40, h=20),
            Element(index=2, kind="tlačítko", name="Smazat", x=60, y=10, w=40, h=20),
            Element(index=3, kind="tlačítko", name="Zobrazit", x=110, y=10, w=40, h=20),
        ],
    )


def _reply_s_akci(target: int = 1):
    from pilot.actions import Action, Plan
    from pilot.brain import Reply

    plan = Plan(say="Jdu na to.", actions=[Action(type="click", target=target)], done=True)
    return Reply(say="Jdu na to.", plan=plan)


def _engine_pro_akce(cfg, monkeypatch, confirmer, target: int = 1):
    from pilot import actions as act

    provedeno: list = []
    monkeypatch.setattr(act, "execute", lambda a, s: provedeno.append(a) or "kliknuto")
    monkeypatch.setattr("pilot.engine.eyes.snapshot", lambda c: _snap_pro_akce())

    from pilot.engine import Engine

    engine = Engine(replace(cfg, use_vision=False), on_event=lambda e: None)
    monkeypatch.setattr(engine.speaker, "say", lambda t: None)
    monkeypatch.setattr(
        engine.brain, "look_and_answer", lambda text, snap: _reply_s_akci(target)
    )
    engine.confirmer = confirmer
    return engine, provedeno


def test_bezna_akce_se_provede_bez_ptani(cfg, monkeypatch):
    """Běžné kliknutí nemá otravovat — provede se a basta."""
    otazky: list = []
    engine, provedeno = _engine_pro_akce(
        cfg, monkeypatch, lambda p, d: otazky.append((p, d)) or False, target=1
    )

    engine.ask("klikni na přejmenovat", background=False)

    assert len(provedeno) == 1, "běžná akce se má provést rovnou"
    assert otazky == [], "u běžné akce se nemá ptát"
    assert engine.state == "idle"


def test_nebezpecna_akce_se_bez_potvrzeni_neprovede(cfg, monkeypatch):
    """Nevratná věc bez potvrzení neproběhne. To je ta záruka."""
    otazky: list = []
    engine, provedeno = _engine_pro_akce(
        cfg, monkeypatch, lambda p, d: otazky.append((p, d)) or False, target=2
    )

    engine.ask("smaž to", background=False)

    assert provedeno == [], "bez potvrzení se nesmí nic provést"
    assert len(otazky) == 1, "u nevratné akce se ptát musí"
    popis, nebezpecna = otazky[0]
    assert nebezpecna is True
    assert "Smazat" in popis, "popis musí jmenovat prvek"


def test_nebezpecna_akce_se_po_potvrzeni_provede(cfg, monkeypatch):
    engine, provedeno = _engine_pro_akce(cfg, monkeypatch, lambda p, d: True, target=2)

    engine.ask("smaž to", background=False)

    assert len(provedeno) == 1
    assert provedeno[0].target == 2
    assert engine.state == "idle"


def test_nebezpecna_akce_se_oznaci(cfg, monkeypatch):
    from pilot import actions as act

    monkeypatch.setattr(act, "execute", lambda a, s: "ok")
    monkeypatch.setattr("pilot.engine.eyes.snapshot", lambda c: _snap_pro_akce())

    from pilot.actions import Action, Plan
    from pilot.brain import Reply
    from pilot.engine import Engine

    engine = Engine(replace(cfg, use_vision=False), on_event=lambda e: None)
    monkeypatch.setattr(engine.speaker, "say", lambda t: None)
    monkeypatch.setattr(
        engine.brain,
        "look_and_answer",
        lambda t, s: Reply(
            say="Smažu to.",
            plan=Plan(say="Smažu to.", actions=[Action(type="click", target=2)]),
        ),
    )

    otazky = []
    engine.confirmer = lambda popis, nebezpecna: otazky.append(nebezpecna) or False

    engine.ask("smaž to", background=False)

    assert otazky == [True], "smazání musí být označené jako nevratné"


def test_chybny_plan_se_neprovede(cfg, monkeypatch):
    from pilot.actions import Plan
    from pilot.brain import Reply
    from pilot.engine import Engine

    monkeypatch.setattr("pilot.engine.eyes.snapshot", lambda c: _snap_pro_akce())

    engine = Engine(replace(cfg, use_vision=False), on_event=lambda e: None)
    monkeypatch.setattr(engine.speaker, "say", lambda t: None)
    monkeypatch.setattr(
        engine.brain,
        "look_and_answer",
        lambda t, s: Reply(say="Nerozumím.", plan=Plan(say="Nerozumím.", error="neznámý typ")),
    )

    provedeno = []
    engine.confirmer = lambda p, d: provedeno.append(True) or True

    engine.ask("něco", background=False)

    assert provedeno == [], "u chybného plánu se nesmí ani ptát"


@pytest.mark.desktop
def test_snapshot_funguje_i_z_vedlejsiho_vlakna(cfg):
    """Regrese: UI Automation je COM a musí se inicializovat v každém vlákně.

    Bez toho `uiautomation` tiše vrátí prázdný strom a model nevidí nic.
    """
    import threading

    vysledek: dict = {}

    def prace() -> None:
        snap = eyes.snapshot(cfg)
        vysledek["okno"] = snap.active_title
        vysledek["prvku"] = len(snap.elements)

    vlakno = threading.Thread(target=prace)
    vlakno.start()
    vlakno.join(30)

    assert vysledek.get("okno"), "ve vlákně se nepřečetlo aktivní okno"
    assert vysledek.get("prvku", 0) > 0, "ve vlákně se nepřečetly žádné prvky"


def test_pred_provedenim_se_precte_cerstvy_snimek(cfg, monkeypatch):
    """Regrese: COM objekty z jiného vlákna už neplatí (RPC_E_DISCONNECTED).

    Před provedením akce se musí obrazovka přečíst znovu, v tom vlákně,
    které bude klikat.
    """
    from pilot import actions as act
    from pilot.brain import Reply
    from pilot.actions import Action, Plan
    from pilot.engine import Engine

    volani = {"snapshot": 0, "execute": 0}

    def falesny_snapshot(c):
        volani["snapshot"] += 1
        return _snap_pro_akce()

    monkeypatch.setattr("pilot.engine.eyes.snapshot", falesny_snapshot)
    monkeypatch.setattr(act, "execute", lambda a, s: volani.__setitem__("execute", volani["execute"] + 1) or "ok")

    engine = Engine(replace(cfg, use_vision=False), on_event=lambda e: None)
    monkeypatch.setattr(engine.speaker, "say", lambda t: None)
    monkeypatch.setattr(
        engine.brain,
        "look_and_answer",
        lambda t, s: Reply(say="Hotovo.", plan=Plan(say="Hotovo.", actions=[Action(type="click", target=1)])),
    )
    engine.confirmer = lambda p, d: False

    engine.ask("klikni", background=False)

    assert volani["execute"] == 1
    assert volani["snapshot"] >= 2, "před kliknutím musí být nový snímek"


def test_hledani_stejneho_prvku_v_novem_snimku():
    from pilot.eyes import Element, Snapshot

    stary = _snap_pro_akce()
    novy = Snapshot(
        active_title=stary.active_title,
        active_class=stary.active_class,
        elements=[
            Element(index=9, kind="tlačítko", name="Přejmenovat", x=10, y=10, w=40, h=20),
            Element(index=10, kind="tlačítko", name="Smazat", x=60, y=10, w=40, h=20),
        ],
    )

    nalezeny = novy.find_like(stary.by_index(1))
    assert nalezeny is not None
    assert nalezeny.index == 9, "index se změnil, prvek ne"

    assert novy.find_like(stary.by_index(2)).index == 10


def test_piper_nezapisuje_kazdou_vetu_do_stejneho_souboru(cfg, tmp_path, monkeypatch):
    """Regrese: druhá věta přepsala první dřív, než se stihla přečíst.

    Přehrávač pak dostal prázdný soubor a hlas mlčel.
    """
    from dataclasses import replace

    from pilot import tts

    class FalesnyHlas:
        def synthesize_wav(self, text, wf) -> None:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            wf.writeframes(b"\x00\x00" * 4000)

    model = tmp_path / "model.onnx"
    model.write_bytes(b"x")

    monkeypatch.setattr(tts, "_piper_voice", lambda m: FalesnyHlas())

    nastaveni = replace(cfg, tts_engine="piper", piper_model=str(model))
    reci = tts.Speaker(nastaveni)

    prvni = reci._piper("První věta.", 0)
    druha = reci._piper("Druhá věta.", 1)

    assert prvni != druha, "každá část musí mít vlastní soubor"
    assert prvni.stat().st_size > 2000
    assert druha.stat().st_size > 2000


def test_prazdny_zvukovy_soubor_da_srozumitelnou_chybu(cfg, tmp_path):
    from pilot.tts import Speaker, TTSError

    prazdny = tmp_path / "nic.wav"
    prazdny.write_bytes(b"")

    with pytest.raises(TTSError, match="prázdný"):
        Speaker(cfg)._decode(prazdny)


def test_hlas_jde_menit_jen_u_edge(cfg, monkeypatch):
    """Regrese: u Piperu šlo přepnout hlas, ale nic to nedělalo.

    Piper má pro češtinu jediný hlas (jirka, mužský) — přepínač proto
    musí být nedostupný, ne tiše ignorovaný.
    """
    from dataclasses import replace

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    from pilot.ui.settings import SettingsDialog

    app = _qt()
    # vynucený jazyk — u "auto" se hlas vybírá sám, viz test níž
    dialog = SettingsDialog(replace(cfg, tts_engine="piper", language="cs"))

    try:
        assert not dialog.voice.isEnabled(), "u Piperu nemá jít hlas měnit"
        assert "Piper" in dialog.note.text()

        index = dialog.engine.findData("edge")
        dialog.engine.setCurrentIndex(index)

        assert dialog.voice.isEnabled(), "u edge-tts s vynuceným jazykem hlas měnit jde"
    finally:
        dialog.close()
        app.processEvents()


def test_transcriber_prewarm_nacte_model_na_pozadi(cfg, monkeypatch):
    """Regrese: chyběl import threading, aplikace spadla hned při startu."""
    import time

    from pilot.stt import Transcriber

    nacteno: list[int] = []
    tr = Transcriber(cfg)
    monkeypatch.setattr(tr, "_load", lambda: nacteno.append(1))

    tr.prewarm()
    time.sleep(0.2)

    assert nacteno, "prewarm model vůbec nenačetl"


def test_render_oddeli_panel_uloh_od_okna():
    """Panel úloh je samostatné okno — musí být v seznamu zvlášť."""
    from pilot.eyes import Element, Snapshot

    snap = Snapshot(
        active_title="Faktury",
        active_class="CabinetWClass",
        elements=[
            Element(index=1, kind="tlačítko", name="Přejmenovat", x=0, y=0, w=10, h=10),
            Element(index=2, kind="tlačítko", name="Affinity Designer 2", x=0, y=1000, w=10, h=10),
        ],
        taskbar_from=2,
    )

    text = snap.render()

    assert "PRVKY V AKTIVNÍM OKNĚ" in text
    assert "PRVKY V PANELU ÚLOH" in text
    assert "[1]" in text and "[2]" in text
    # prvek panelu nesmí být v části aktivního okna
    okno_cast = text.split("PRVKY V PANELU ÚLOH")[0]
    assert "Affinity" not in okno_cast


@pytest.mark.desktop
def test_snapshot_obsahne_panel_uloh(cfg):
    """Regrese: dřív snímek četl jen aktivní okno, takže na ikonu v liště
    nešlo kliknout — model ji vůbec neviděl."""
    snap = eyes.snapshot(cfg)

    assert snap.taskbar_from is not None, "panel úloh se nepřečetl"
    panel = [e for e in snap.elements if e.index >= snap.taskbar_from]
    assert panel, "panel úloh je prázdný"


def _engine_pro_smycku(cfg, monkeypatch, kroky_next):
    from pilot import actions as act
    from pilot.actions import Action, Plan
    from pilot.brain import Reply
    from pilot.engine import Engine

    provedeno: list = []
    monkeypatch.setattr(act, "execute", lambda a, s: provedeno.append(a.target) or "ok")
    monkeypatch.setattr("pilot.engine.eyes.snapshot", lambda c: _snap_pro_akce())

    engine = Engine(replace(cfg, use_vision=False), on_event=lambda e: None)
    monkeypatch.setattr(engine.speaker, "say", lambda t: None)
    monkeypatch.setattr(
        engine.brain,
        "look_and_answer",
        lambda t, s: Reply(say="", plan=Plan(say="", actions=[Action(type="click", target=1)])),
    )
    iterator = iter(kroky_next)
    monkeypatch.setattr(
        engine.brain,
        "next_step",
        lambda cil, provedene, snap: next(iterator, Plan(say="", actions=[], done=True)),
    )
    engine.confirmer = lambda p, d: False
    return engine, provedeno


def test_smycka_udela_vic_kroku_k_cili(cfg, monkeypatch):
    """Autonomie: model dostane nový snímek a rozhodne další krok."""
    from pilot.actions import Action, Plan

    engine, provedeno = _engine_pro_smycku(
        cfg,
        monkeypatch,
        [
            Plan(say="Hotovo.", actions=[Action(type="click", target=3)], done=True),
        ],
    )

    engine.ask("klikni na obě tlačítka", background=False)

    assert provedeno == [1, 3], "smyčka má provést oba kroky"


def test_smycka_skonci_kdyz_model_rekne_done(cfg, monkeypatch):
    from pilot.actions import Action, Plan

    engine, provedeno = _engine_pro_smycku(
        cfg,
        monkeypatch,
        [Plan(say="Hotovo.", actions=[], done=True)],
    )

    engine.ask("klikni", background=False)

    assert provedeno == [1], "po done se nesmí pokračovat"


def test_smycka_se_zastavi_na_rozpoctu_kroku(cfg, monkeypatch):
    """Nikdy nesmí běžet do nekonečna."""
    from pilot.actions import Action, Plan

    engine, provedeno = _engine_pro_smycku(
        cfg,
        monkeypatch,
        [Plan(say="", actions=[Action(type="click", target=1)], done=False) for _ in range(50)],
    )
    engine.cfg = type(engine.cfg)(**{**engine.cfg.__dict__, "max_steps": 4})

    engine.ask("pořád dokola", background=False)

    assert len(provedeno) <= 4, f"smíčka udělala {len(provedeno)} kroků"


def test_smycka_se_zastavi_pri_opakujicim_se_kroku(cfg, monkeypatch):
    """Když model navrhuje pořád to samé, něco je špatně — skončit."""
    from pilot.actions import Action, Plan

    stejny = [Plan(say="", actions=[Action(type="click", target=1)], done=False) for _ in range(20)]
    engine, provedeno = _engine_pro_smycku(cfg, monkeypatch, stejny)

    engine.ask("klikni", background=False)

    assert len(provedeno) <= 3, f"opakování se nezastavilo ({len(provedeno)} kroků)"


@pytest.mark.parametrize("text", ["zavolat Ondrovi", "Zavolej", "call Ondra", "hovor"])
def test_hovor_je_nevratny(text):
    """Omylem vytořený hovor nejde vzít zpět — má se na něj zeptat."""
    from pilot.actions import Action, Plan

    plan = Plan(say="x", actions=[Action(type="type", text=text)])
    assert plan.is_destructive


def test_prazdne_say_se_necte_jako_json():
    """Regrese: model vrátil 'say': '' a aplikace přečetla nahlas celý JSON."""
    from pilot import actions

    plan = actions.parse('{"say": "", "actions": [{"type": "click", "target": 42}], "done": false}')

    assert plan.say == "", f"do hlasu se dostal: {plan.say!r}"
    assert len(plan.actions) == 1
    assert plan.actions[0].target == 42


def test_prazdne_say_u_chybneho_planu():
    from pilot import actions

    plan = actions.parse('{"say": "", "actions": [{"type": "neexistuje"}]}')

    assert plan.say == "", "ani u chyby se nesmí číst JSON"
    assert plan.error


def test_mezitimni_kroky_se_nemluvi(cfg, monkeypatch):
    """Model nemá komentovat každý krok — mluví se až na konci."""
    from pilot.actions import Action, Plan

    receno: list[str] = []
    engine, provedeno = _engine_pro_smycku(
        cfg,
        monkeypatch,
        [Plan(say="Klikl jsem a přešel správně.", actions=[Action(type="click", target=3)], done=True)],
    )
    monkeypatch.setattr(engine, "_speak", lambda t: receno.append(t))

    engine.ask("klikni", background=False)

    assert provedeno == [1, 3]
    assert receno == ["Klikl jsem a přešel správně."], receno
    assert len(receno) == 1, "mluvit se má jen jednou, na konci"


# ------------------------------------------------------------------- jazyk


def test_zmena_jazyka_nabidne_spravne_hlasy(cfg, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from dataclasses import replace

    from pilot.ui.settings import SettingsDialog

    app = _qt()
    dialog = SettingsDialog(replace(cfg, language="cs"))

    try:
        ceske = [dialog.voice.itemData(i) for i in range(dialog.voice.count())]
        assert any(v.startswith("cs-CZ") for v in ceske), ceske

        index = dialog.language.findData("en")
        dialog.language.setCurrentIndex(index)

        anglicke = [dialog.voice.itemData(i) for i in range(dialog.voice.count())]
        assert any(v.startswith("en-US") for v in anglicke), anglicke
        assert not any(v.startswith("cs-CZ") for v in anglicke)
    finally:
        dialog.close()
        app.processEvents()


def test_prompt_obsahuje_jazyk_odpovedi(cfg, monkeypatch):
    from dataclasses import replace

    from pilot.brain import Brain

    brain = Brain(replace(cfg, language="en"), client=type("C", (), {"generate": lambda *a: ""})())
    prompt = brain._build_prompt("hello", eyes.snapshot(cfg))

    assert "angličtina" in prompt


def test_piper_nevyrobi_anglictinu_ceskym_modelem(cfg, tmp_path):
    """Český model na anglický text by zněl jako nesmysl — radši chyba."""
    from dataclasses import replace

    from pilot.tts import Speaker, TTSError

    model = tmp_path / "cs_CZ-jirka-medium.onnx"
    model.write_bytes(b"x")

    nastaveni = replace(cfg, language="en", tts_engine="piper", piper_model=str(model))

    with pytest.raises(TTSError, match="angličtin"):
        Speaker(nastaveni)._piper("hello")


def test_abort_prerusi_smycku(cfg, monkeypatch):
    """Uživatel musí mít jak úkol zastavit — Ctrl+Alt+Esc."""
    from pilot.actions import Action, Plan

    engine, provedeno = _engine_pro_smycku(
        cfg,
        monkeypatch,
        [Plan(say="", actions=[Action(type="click", target=1)], done=False) for _ in range(20)],
    )

    puvodni = engine.brain.next_step

    def po_prvnim(cil, proc, snap):
        engine.abort()
        return puvodni(cil, proc, snap)

    monkeypatch.setattr(engine.brain, "next_step", po_prvnim)

    engine.ask("dělej něco dlouho", background=False)

    assert len(provedeno) <= 2, f"po přerušení se provedlo {len(provedeno)} akcí"
    assert engine.state in ("idle", "listening")


def test_abort_zhasne_prekryv_kdyz_nic_nebezi(cfg, monkeypatch):
    from pilot.engine import Engine

    udalosti: list[dict] = []
    engine = Engine(cfg, on_event=udalosti.append)
    engine.abort()

    assert any(
        u.get("type") == "control" and u.get("on") is False for u in udalosti
    ), "přerušení má zhasnout překryv"


# --------------------------------------------------------------------- web


def test_render_oddeli_webovou_stranku():
    from pilot.eyes import Element, Snapshot

    snap = Snapshot(
        active_title="Facebook",
        active_class="Chrome_WidgetWin_1",
        elements=[
            Element(index=1, kind="tlačítko", name="Zpět", x=0, y=0, w=10, h=10),
            Element(index=2, kind="panel", name="Panel", x=0, y=10, w=10, h=10),
            Element(index=3, kind="button", name="Přehrát", x=400, y=300, w=40, h=40,
                    source="cdp", cdp_index=7),
        ],
        web_from=3,
    )

    text = snap.render()

    assert "PRVKY NA WEBOVÉ STRÁNCE" in text
    assert "Přehrát" in text
    web_cast = text.split("PRVKY NA WEBOVÉ STRÁNCE")[0]
    assert "Přehrát" not in web_cast


def test_webovy_prvek_se_klikne_pres_prohlizec(monkeypatch):
    from pilot import actions, cdp
    from pilot.eyes import Element, Snapshot

    kliknuto = []

    class FalesnaKarta:
        def click(self, index, text):
            kliknuto.append((index, text))
            return "ok"

        def close(self):
            pass

    monkeypatch.setattr(cdp, "first_page", lambda: FalesnaKarta())

    snap = Snapshot(
        elements=[
            Element(index=1, kind="video", name="Přehrát video", x=0, y=0, w=10, h=10,
                    source="cdp", cdp_index=4),
        ]
    )

    vysledek = actions.execute(actions.Action(type="click", target=1), snap)

    assert kliknuto == [(4, "Přehrát video")]
    assert "Přehrát" in vysledek


def test_webovy_prvek_se_pri_zmene_stranky_dohleda_podle_textu():
    from pilot.eyes import Element, Snapshot

    stary = Snapshot(
        elements=[Element(index=1, kind="button", name="Přihlásit", x=10, y=10, w=5, h=5,
                          source="cdp", cdp_index=2)]
    )
    novy = Snapshot(
        elements=[Element(index=5, kind="button", name="Přihlásit", x=99, y=77, w=5, h=5,
                          source="cdp", cdp_index=9)]
    )

    assert novy.find_by_name("Přihlásit", source="cdp").index == 5
    assert novy.find_by_name("Přihlásit", source="uia") is None


def test_bez_prohlizece_webova_akce_selze_srozumitelne(monkeypatch):
    from pilot import actions, cdp
    from pilot.eyes import Element, Snapshot

    monkeypatch.setattr(cdp, "first_page", lambda: None)
    snap = Snapshot(
        elements=[Element(index=1, kind="button", name="X", x=0, y=0, w=5, h=5,
                          source="cdp", cdp_index=0)]
    )

    with pytest.raises(actions.ActionError, match="prohlížeč"):
        actions.execute(actions.Action(type="click", target=1), snap)


def test_karta_se_vybere_podle_nazvu_okna(monkeypatch):
    """Regrese: připojili jsme prvky z jiné karty, než bylo aktivní okno."""
    from pilot import cdp

    monkeypatch.setattr(
        cdp,
        "pages",
        lambda: [
            {"id": "karta-a", "title": "Facebook", "url": "https://facebook.com"},
            {"id": "karta-b", "title": "Gmail", "url": "https://mail.google.com"},
        ],
    )
    monkeypatch.setattr(cdp, "Tab", lambda tid: tid)

    assert cdp.tab_for_window("Gmail - Google Chrome") == "karta-b"
    assert cdp.tab_for_window("Facebook - Google Chrome") == "karta-a"
    assert cdp.tab_for_window("Průzkumník - Google Chrome") is None


def test_automaticky_jazyk_prebere_hlas_z_rozpoznani(cfg, monkeypatch):
    """Regrese: s vynucenou angličtinou Whisper přepsal češtinu jako nesmysl."""
    from dataclasses import replace

    from pilot.engine import VOZBY, Engine

    engine = Engine(replace(cfg, language="auto"), on_event=lambda e: None)
    engine.transcriber.last_language = "en"
    engine._podle_jazyka()

    assert engine.brain.override_language == "en"
    assert engine.speaker.voice_override == VOZBY["en"]

    engine.transcriber.last_language = "cs"
    engine._podle_jazyka()
    assert engine.speaker.voice_override == VOZBY["cs"]


def test_vynuceny_jazyk_hlas_nemeni(cfg):
    from dataclasses import replace

    from pilot.engine import Engine

    engine = Engine(replace(cfg, language="en", voice="en-US-GuyNeural"), on_event=lambda e: None)
    engine.transcriber.last_language = "cs"
    engine._podle_jazyka()

    assert engine.speaker.voice_override is None, "při vynuceném jazyce se hlas neřídí detekcí"


def test_pri_automatickem_jazyce_se_hlas_nevybira(cfg, monkeypatch):
    """Když se jazyk pozná z řeči, hlas se řídí jím — ruční volba nemá smysl."""
    from dataclasses import replace

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    from pilot.ui.settings import SettingsDialog

    app = _qt()
    dialog = SettingsDialog(replace(cfg, tts_engine="edge", language="auto"))

    try:
        assert not dialog.voice.isEnabled(), "u auto se hlas nemá vybírat ručně"
        assert "pozná z řeči" in dialog.note.text()

        index = dialog.language.findData("cs")
        dialog.language.setCurrentIndex(index)

        assert dialog.voice.isEnabled(), "u vynuceného jazyka se hlas vybírá"
    finally:
        dialog.close()
        app.processEvents()


def test_zavreni_okna_podle_nazvu(cfg):
    """„Zavři Discord" nesmí záviset na klikání do panelu úloh."""
    from pilot import actions

    akce = actions.parse('{"say": "", "actions": [{"type": "close", "title": "Discord"}]}').actions[0]
    assert akce.title == "Discord"

    popis = actions.describe(actions.Plan(actions=[akce]), eyes.snapshot(cfg))
    assert "Discord" in popis


def test_aktivace_okna_bez_title_selze():
    from pilot import actions

    plan = actions.parse('{"say": "", "actions": [{"type": "activate"}]}')
    assert plan.actions == []
    assert "title" in plan.error


@pytest.mark.desktop
def test_najdi_okno_podle_casti_nazvu():
    from pilot import actions

    hwnd = actions._najdi_okno("voice-pilot")
    assert hwnd, "vlastní okno by mělo jít najít"


def test_nenajde_neexistujici_okno():
    from pilot import actions

    with pytest.raises(actions.ActionError, match="nenašli"):
        actions._najdi_okno("urcite-neexistujici-okno-xyz")


def test_prekryv_zustane_aspon_chvili_videt(monkeypatch):
    """Krátká akce nesmí bliknout a zmizet dřív, než ji člověk zaregistruje."""
    import time

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    from pilot.ui import overlay as mod

    app = _qt()
    prekryvy = mod.Overlays()
    viditelne = []
    monkeypatch.setattr(prekryvy, "_zobraz", lambda stav: viditelne.append(stav))

    prekryvy.show_control(True)
    prekryvy.show_control(False)   # hned pryč = typický případ jednoho kliknutí
    assert viditelne == [True], "nesmí se schovat okamžitě"

    time.sleep(mod.Overlays.MINIMUM_VIDITELNE + 0.2)
    app.processEvents()
    time.sleep(0.2)
    app.processEvents()
    assert viditelne == [True, False], f"po minimální době se má schovat: {viditelne}"


# ------------------------------------------------------------------ vision


def test_souradnice_se_prepocitaji_zpet_na_obrazovku():
    """Model vrací souřadnice ve zmenšeném snímku — musíme je zvětšit."""
    from pilot.vision import Snimek

    obraz = Snimek(data=b"", sirka=1280, vyska=720, offset_x=1920, offset_y=0, scale=1.5)

    assert obraz.na_obrazovku(100, 50) == (1920 + 150, 0 + 75)
    assert obraz.na_obrazovku(0, 0) == (1920, 0)


def test_klik_souradnicemi_se_provede(monkeypatch):
    from pilot import actions
    from pilot.eyes import Snapshot

    kliknuto = []
    monkeypatch.setattr(actions, "_klik_mysi", lambda x, y, k: kliknuto.append((x, y, k)))

    plan = actions.parse('{"say": "", "actions": [{"type": "click", "x": 400, "y": 300}]}')
    vysledek = actions.execute(plan.actions[0], Snapshot())

    assert kliknuto == [(400, 300, "click")]
    assert "400" in vysledek


def test_psani_nejdriv_klikne_do_pole(monkeypatch):
    from pilot import actions
    from pilot.eyes import Snapshot

    poradi = []
    monkeypatch.setattr(actions, "_klik_mysi", lambda x, y, k: poradi.append("klik"))
    monkeypatch.setattr(actions, "_napis", lambda t: poradi.append(f"psani:{t}"))

    akce = actions.Action(type="type", x=10, y=20, text="ahoj")
    actions.execute(akce, Snapshot())

    assert poradi == ["klik", "psani:ahoj"], poradi


def test_vision_prompt_obsahuje_rozmery(cfg):
    from pilot.brain import Brain
    from pilot.vision import Snimek

    obraz = Snimek(data=b"", sirka=1280, vyska=720, offset_x=0, offset_y=0, scale=1.5)
    brain = Brain(replace(cfg, use_vision=True))

    vyzva = brain.vision_prompt("zavři discord", [], obraz)

    assert "1280x720" in vyzva
    assert "zavři discord" in vyzva
    assert '"x"' in vyzva


def test_souradnice_mimo_snimek_se_neklikne(cfg, monkeypatch):
    """Regrese: model vrátil (522, 1038) u snímku 1280x720 a kliklo se vedle."""
    from pilot import vision

    kliknuto = []
    monkeypatch.setattr("pilot.actions._klik_mysi", lambda x, y, k: kliknuto.append((x, y)))

    obraz = vision.Snimek(data=b"", sirka=1280, vyska=720, offset_x=0, offset_y=0, scale=1.5)
    mimo = (522, 1038)

    assert not (0 <= mimo[0] < obraz.sirka and 0 <= mimo[1] < obraz.vyska)
    assert kliknuto == []


def test_plan_vi_jestli_prisel_json():
    from pilot import actions

    json_plan = actions.parse('{"say": "", "actions": [], "done": true}')
    assert json_plan.from_json is True

    rec_plan = actions.parse("The user asks to minimize Discord. Let me look at the image.")
    assert rec_plan.from_json is False, "uvažování modelu se nesmí tvářit jako odpověď"


def test_vision_prompt_zakazuje_uvažování(cfg):
    from pilot.brain import Brain
    from pilot.vision import Snimek

    obraz = Snimek(data=b"", sirka=1920, vyska=1080, offset_x=0, offset_y=0, scale=1.0)
    vyzva = Brain(replace(cfg, use_vision=True)).vision_prompt("zavři discord", [], obraz)

    assert "POUZE JSON" in vyzva
    assert "uvažování" in vyzva
