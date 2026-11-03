"""Jádro asistenta bez uživatelského rozhraní.

`Engine` umí to samé, co dřív dělala smyčka v `app.py`, ale místo tisku
do terminálu vysílá události. Terminál i okno ho používají stejně, takže
logika kola (nahrát → přepsat → podívat se → odpovědět) existuje jednou.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

import sounddevice as sd

from . import actions, eyes
from .actions import Action
from .brain import Brain
from .stt import Mic, Transcriber
from .tts import Speaker

IDLE = "idle"
LISTENING = "listening"
THINKING = "thinking"
SPEAKING = "speaking"
ERROR = "error"


class Engine:
    """Všechno, co se děje mezi stiskem F9 a odpovědí.

    Události jsou slovníky s klíčem ``type``:
      state    {value, detail}
      heard    {text, seconds?}
      screen   {elements, window}
      answer   {text}
      log      {text, kind}
    """

    def __init__(self, cfg, on_event: Callable[[dict], None] | None = None):
        self.cfg = cfg
        self.on_event = on_event

        self.mic = Mic(cfg.sample_rate)
        self.transcriber = Transcriber(cfg)
        self.speaker = Speaker(cfg)
        self.brain = Brain(cfg)

        self.state = IDLE
        self._busy = False
        self._diktovani = None
        self.speak_replies = True
        self.on_level = None
        self._prerusit_ukol = False

        # Kdo potvrzuje akce. Výchozí je "ne" — bez obsluhy se nic neprovede.
        self.confirmer: Callable[[str, bool], bool] = lambda popis, nebezpecna: False

        # měření jednotlivých kroků pro diagnostiku
        self._cas_prepisu = 0.0
        self._cas_modelu = 0.0
        self._cas_hlasu = 0.0
        self._cas_prvni_zvuk = 0.0

    # ------------------------------------------------------------- stav

    def _emit(self, payload: dict) -> None:
        if self.on_event is not None:
            try:
                self.on_event(payload)
            except Exception:
                pass

    def _set_state(self, state: str, detail: str = "") -> None:
        self.state = state
        self._emit({"type": "state", "value": state, "detail": detail})

    def _log(self, text: str, kind: str = "info") -> None:
        self._emit({"type": "log", "text": text, "kind": kind})

    @property
    def is_recording(self) -> bool:
        return self.mic.is_recording

    @property
    def is_busy(self) -> bool:
        return self._busy

    # ------------------------------------------------------- ovládání

    def preflight(self) -> tuple[bool, str]:
        return self.brain.client.preflight()

    def toggle(self) -> None:
        """F9: zapne nebo vypne průběžné diktování."""
        if self._diktovani is not None:
            self.stop_dictation()
        else:
            self.start_dictation()

    def start_dictation(self) -> None:
        if self._diktovani is not None:
            return
        if self._busy:
            self._log("Počkej, ještě dodělávám předchozí dotaz.", "warn")
            return

        from .dictation import DictationSession

        self.speak_replies = False
        self._diktovani = DictationSession(
            self.cfg,
            on_utterance=self._on_utterance,
            on_level=self._uroven,
        )
        self._diktovani.start()
        self._emit({"type": "dictation", "on": True})
        self._set_state(LISTENING, "diktuji")

    def stop_dictation(self) -> None:
        if self._diktovani is None:
            return
        self._diktovani.stop()
        self._diktovani = None
        self.speak_replies = True
        self._emit({"type": "dictation", "on": False})
        self._set_state(IDLE)

    @property
    def diktuje(self) -> bool:
        return self._diktovani is not None

    def abort(self) -> None:
        """Přeruší běžící úkol: zastaví hlas, smyčku i překryv."""
        self._prerusit_ukol = True
        try:
            self.speaker.stop()
        except Exception:
            pass
        self._log("Přerušeno.", "warn")

        if not self._busy:
            # nic neběží, tak aspoň zhasni překryv
            self._emit({"type": "control", "on": False})
            self._set_state(LISTENING if self._diktovani else IDLE)

    def _uroven(self, hodnota: float) -> None:
        if self.on_level is not None:
            try:
                self.on_level(hodnota)
            except Exception:
                pass

    def _on_utterance(self, audio) -> None:
        """Jedna věta z průběžného diktování — přepiš a hned jednej."""
        if self._busy:
            return
        self._set_state(THINKING, "přepisuji")
        try:
            text = self.transcriber.transcribe(audio)
        except Exception as exc:
            self._log(f"Přepis selhal: {exc}", "error")
            return

        if not text:
            self._set_state(LISTENING, "diktuji")
            return

        self._podle_jazyka()
        self._emit({"type": "heard", "text": text})
        self._answer(text, None)

    def start_listening(self) -> None:
        if self._busy:
            self._log("Počkej, ještě dodělávám předchozí dotaz.", "warn")
            return
        self.speaker.stop()
        sd.stop()
        _beep(880)
        try:
            self.mic.start()
        except Exception as exc:
            self._fail(f"Mikrofon se nepodařilo otevřít: {exc}")
            return
        self._set_state(LISTENING)

    def stop_listening(self) -> None:
        if not self.mic.is_recording:
            return
        audio = self.mic.stop()
        _beep(620)
        self._set_state(THINKING, "přepisuji")
        threading.Thread(target=self._turn, args=(audio,), daemon=True).start()

    def ask(self, text: str, background: bool = True) -> None:
        """Dotaz bez mikrofonu (z okna, z terminálu, z testu)."""
        text = (text or "").strip()
        if not text:
            return
        self._emit({"type": "heard", "text": text})
        self._busy = True
        self._set_state(THINKING, "model")
        if background:
            threading.Thread(target=self._answer, args=(text,), daemon=True).start()
        else:
            self._answer(text)

    # ----------------------------------------------------------- kolo

    def _turn(self, audio) -> None:
        seconds = audio.size / self.cfg.sample_rate

        # Čtení obrazovky a přepis na sobě nezávisí — běží vedle sebe.
        # Ušetří to to, co by jinak trvalo dvakrát.
        obrazovka: dict = {}

        def nacti_obrazovku() -> None:
            try:
                snap = eyes.snapshot(self.cfg)
                self._emit(
                    {
                        "type": "screen",
                        "elements": len(snap.elements),
                        "window": snap.active_title,
                    }
                )
                # COM odkazy patří tomuhle vláknu — pusťme je tady, ne jinde
                eyes.release(snap)
                obrazovka["snap"] = snap
            except Exception as exc:
                obrazovka["error"] = exc

        vlakno = threading.Thread(target=nacti_obrazovku, daemon=True)
        vlakno.start()

        t0 = time.monotonic()
        try:
            text = self.transcriber.transcribe(audio)
        except Exception as exc:
            self._fail(f"Přepis selhal: {exc}")
            return
        self._cas_prepisu = time.monotonic() - t0
        self._podle_jazyka()
        vlakno.join(timeout=self.cfg.ui_budget_seconds + 2)

        if not text:
            self._log("Nic jsem neslyšel.", "warn")
            self._emit({"type": "heard", "text": ""})
            self._set_state(IDLE)
            return

        self._emit({"type": "heard", "text": text, "seconds": round(seconds, 1)})
        self._answer(text, obrazovka.get("snap"))

    def _answer(self, text: str, snap=None) -> None:
        self._busy = True
        t0_modelu = time.monotonic()
        try:
            if snap is None:
                snap = eyes.snapshot(self.cfg)
                self._emit(
                    {
                        "type": "screen",
                        "elements": len(snap.elements),
                        "window": snap.active_title,
                    }
                )
            reply = self.brain.look_and_answer(text, snap)
        except Exception as exc:
            self._fail(f"Model neodpověděl: {exc}")
            return
        self._cas_modelu = time.monotonic() - t0_modelu

        plan = reply.plan
        if plan.error:
            self._log(f"Plán neprošel: {plan.error}", "error")

        self._emit({"type": "answer", "text": reply.say})

        if not plan.actions:
            self._speak(reply.say)
            self._done()
            return

        self._run_plan(plan, snap, reply.say, text)

    def _run_plan(self, plan, snap, say: str, cil_ukolu: str = "") -> None:
        """Smyčka k cíli: proveď krok, podívej se znovu, rozhodni další.

        Model nedostane celý plán dopředu — obrazovka se mezi kroky změní.
        Po každém kroku se čte znovu a model rozhodne, co dál, dokud neřekne
        "done" nebo nedojde rozpočet kroků.
        """
        cil_ukolu = cil_ukolu or say
        provedene: list[str] = []
        posledni_say = ""
        posledni_popis = ""
        opakovani = 0
        self._prerusit_ukol = False

        self._emit({"type": "control", "on": True})

        for krok in range(1, self.cfg.max_steps + 1):
            if self._prerusit_ukol:
                self._log("Úkol přerušen.", "warn")
                break
            if not plan.actions:
                break

            popis = actions.describe(plan, snap)
            nebezpecna = actions.je_nebezpecny(plan, snap)

            opakovani = opakovani + 1 if popis == posledni_popis else 0
            if opakovani >= 2:
                self._log("Stejný krok se opakuje, končím.", "warn")
                break
            posledni_popis = popis

            self._emit(
                {
                    "type": "plan",
                    "say": plan.say,
                    "description": popis,
                    "destructive": nebezpecna,
                    "step": krok,
                }
            )

            if nebezpecna:
                self._set_state(THINKING, "čekám na potvrzení")
                self._speak(f"Pozor, tohle se nedá vzít zpět: {popis}. Potvrdit?")
                try:
                    potvrzeno = bool(self.confirmer(popis, True))
                except Exception as exc:
                    self._log(f"Potvrzení selhalo: {exc}", "error")
                    potvrzeno = False

                if not potvrzeno:
                    self._emit({"type": "executed", "results": [], "cancelled": True})
                    self._speak("Zrušeno.")
                    self._done()
                    return

            # Čerstvý snímek v TOMTO vlákně: COM objekty z vlákna, kde se
            # četla obrazovka pro model, už nemusí existovat.
            try:
                cerstvy = eyes.snapshot(self.cfg)
            except Exception as exc:
                self._log(f"Obrazovku už nejde přečíst: {exc}", "error")
                cerstvy = None

            vysledky: list[str] = []
            vsechno = True
            for akce in plan.actions:
                try:
                    cil = self._premapuj(akce, snap, cerstvy)
                    vysledek = actions.execute(cil, cerstvy or snap)
                    vysledky.append(vysledek)
                    provedene.append(vysledek)
                    time.sleep(0.15)
                except Exception as exc:
                    vysledky.append(f"chyba: {exc}")
                    vsechno = False
                    break

            if cerstvy is not None:
                eyes.release(cerstvy)

            self._emit(
                {
                    "type": "executed",
                    "results": vysledky,
                    "cancelled": False,
                    "ok": vsechno,
                }
            )

            if not vsechno or plan.done:
                break
            if self._prerusit_ukol:
                self._log("Úkol přerušen.", "warn")
                break
            if krok >= self.cfg.max_steps:
                self._log(f"Vyčerpán rozpočet {self.cfg.max_steps} kroků.", "warn")
                break

            # nový snímek a rozhodnutí, co dál
            try:
                snap = eyes.snapshot(self.cfg)
                plan = self.brain.next_step(cil_ukolu, provedene, snap)
            except Exception as exc:
                self._log(f"Další krok se nepovedl: {exc}", "error")
                break

            if plan.error:
                self._log(f"Plán neprošel: {plan.error}", "error")
                break

            # Mluvíme jen na konci. Mezitímní „klikl jsem, přešel jsem správně“
            # je šum — uživatel to nechce poslouchat u každého kroku.
            if plan.done and plan.say:
                posledni_say = plan.say
            eyes.release(snap)

        if posledni_say:
            self._speak(posledni_say)
        elif not provedene:
            self._speak("Nepovedlo se to.")
        self._done()

    def _premapuj(self, akce, stary, novy):
        """Přeloží číslo prvku ze starého snímku do nového (podle jména a místa)."""
        if novy is None or akce.target is None:
            return akce

        puvodni = stary.by_index(akce.target)
        if puvodni is None:
            return akce

        # u webu se text nemění, ale pozice při scrollování ano — párujeme podle textu
        if puvodni.source == "cdp":
            nalezeny = novy.find_by_name(puvodni.name, source="cdp")
        else:
            nalezeny = novy.find_like(puvodni)
        if nalezeny is None:
            raise actions.ActionError(f"„{puvodni.name}“ už na obrazovce není")

        return Action(
            type=akce.type,
            target=nalezeny.index,
            text=akce.text,
            keys=akce.keys,
            direction=akce.direction,
            amount=akce.amount,
        )

    def _podle_jazyka(self) -> None:
        """Whisper poznal jazyk — podle něj nastav odpověď i hlas."""
        jazyk = getattr(self.transcriber, "last_language", "cs") or "cs"
        self.brain.override_language = jazyk
        if getattr(self.cfg, "language", "auto") == "auto":
            self.speaker.voice_override = VOZBY.get(jazyk, VOZBY["cs"])

    def _speak(self, text: str) -> None:
        if not self.speak_replies:
            return
        self._set_state(SPEAKING)
        t0 = time.monotonic()
        zaznamenano = {"t": None}

        def prvni_zvuk() -> None:
            if zaznamenano["t"] is None:
                zaznamenano["t"] = time.monotonic() - t0

        self.speaker.on_first_audio = prvni_zvuk
        try:
            self.speaker.say(text)
        except Exception as exc:
            self._log(f"Hlas selhal: {exc}", "error")
        finally:
            self.speaker.on_first_audio = None
            self._cas_hlasu += time.monotonic() - t0
            if zaznamenano["t"] is not None:
                self._cas_prvni_zvuk += zaznamenano["t"]

    def _done(self) -> None:
        self._emit({"type": "control", "on": False})
        self._busy = False
        self._set_state(LISTENING if self._diktovani else IDLE)

        if self._cas_prepisu or self._cas_modelu:
            riadok = (
                f"  kolo: přepis {self._cas_prepisu:.1f} s"
                f" · model {self._cas_modelu:.1f} s"
                f" · první zvuk {self._cas_prvni_zvuk:.1f} s"
                f" · celkem do zvuku "
                f"{self._cas_prepisu + self._cas_modelu + self._cas_prvni_zvuk:.1f} s"
            )
            print(riadok, flush=True)
            self._log(
                f"do prvního zvuku "
                f"{self._cas_prepisu + self._cas_modelu + self._cas_prvni_zvuk:.1f} s"
            )
        self._cas_prepisu = self._cas_modelu = self._cas_hlasu = 0.0
        self._cas_prvni_zvuk = 0.0

    def _fail(self, message: str) -> None:
        self._busy = False
        self._log(message, "error")
        self._set_state(ERROR, message)

    # -------------------------------------------------------- ukončení

    def shutdown(self) -> None:
        if self._diktovani is not None:
            self._diktovani.stop()
            self._diktovani = None
        try:
            sd.stop()
        except Exception:
            pass
        if self.mic.is_recording:
            self.mic.stop()


VOZBY = {"cs": "cs-CZ-VlastaNeural", "en": "en-US-AriaNeural"}


def _beep(frequency: int = 800, duration_ms: int = 70) -> None:
    try:
        import winsound

        winsound.Beep(frequency, duration_ms)
    except Exception:
        pass
