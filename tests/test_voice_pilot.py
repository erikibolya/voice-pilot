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


# ---------------------------------------------------------------- milník 2


def _snap_pro_akce():
    from pilot.eyes import Element, Snapshot

    return Snapshot(
        active_title="Faktury – Průzkumník souborů",
        active_class="CabinetWClass",
        elements=[
            Element(index=1, kind="tlačítko", name="Přejmenovat", x=10, y=10, w=40, h=20),
            Element(index=2, kind="tlačítko", name="Smazat", x=60, y=10, w=40, h=20),
        ],
    )


def _reply_s_akci(target: int = 1):
    from pilot.actions import Action, Plan
    from pilot.brain import Reply

    plan = Plan(say="Jdu na to.", actions=[Action(type="click", target=target)])
    return Reply(say="Jdu na to.", plan=plan)


def _engine_pro_akce(cfg, monkeypatch, confirmer, target: int = 1):
    from pilot import actions as act

    provedeno: list = []
    monkeypatch.setattr(act, "execute", lambda a, s: provedeno.append(a) or "kliknuto")
    monkeypatch.setattr("pilot.engine.eyes.snapshot", lambda c: _snap_pro_akce())

    from pilot.engine import Engine

    engine = Engine(cfg, on_event=lambda e: None)
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

    engine = Engine(cfg, on_event=lambda e: None)
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

    engine = Engine(cfg, on_event=lambda e: None)
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

    engine = Engine(cfg, on_event=lambda e: None)
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
