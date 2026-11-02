"""Jádro asistenta bez uživatelského rozhraní.

`Engine` umí to samé, co dřív dělala smyčka v `app.py`, ale místo tisku
do terminálu vysílá události. Terminál i okno ho používají stejně, takže
logika kola (nahrát → přepsat → podívat se → odpovědět) existuje jednou.
"""

from __future__ import annotations

import threading
from typing import Callable

import sounddevice as sd

from . import eyes
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
        """F9: začni nebo dokonči nahrávání."""
        if self.mic.is_recording:
            self.stop_listening()
        else:
            self.start_listening()

    def start_listening(self) -> None:
        if self._busy:
            self._log("Počkej, ještě dodělávám předchozí dotaz.", "warn")
            return
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
                obrazovka["snap"] = snap
                self._emit(
                    {
                        "type": "screen",
                        "elements": len(snap.elements),
                        "window": snap.active_title,
                    }
                )
            except Exception as exc:
                obrazovka["error"] = exc

        vlakno = threading.Thread(target=nacti_obrazovku, daemon=True)
        vlakno.start()

        try:
            text = self.transcriber.transcribe(audio)
        except Exception as exc:
            self._fail(f"Přepis selhal: {exc}")
            return

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

        self._emit({"type": "answer", "text": reply.say})
        self._set_state(SPEAKING)
        try:
            self.speaker.say(reply.say)
        except Exception as exc:
            self._log(f"Hlas selhal: {exc}", "error")
        finally:
            self._busy = False
            self._set_state(IDLE)

    def _fail(self, message: str) -> None:
        self._busy = False
        self._log(message, "error")
        self._set_state(ERROR, message)

    # -------------------------------------------------------- ukončení

    def shutdown(self) -> None:
        try:
            sd.stop()
        except Exception:
            pass
        if self.mic.is_recording:
            self.mic.stop()


def _beep(frequency: int = 800, duration_ms: int = 70) -> None:
    try:
        import winsound

        winsound.Beep(frequency, duration_ms)
    except Exception:
        pass
