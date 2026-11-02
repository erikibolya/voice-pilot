"""Terminálový režim: držíš F9, mluvíš, on odpovídá."""

from __future__ import annotations

import sys
import time

from .engine import Engine
from .hotkey import HotkeyWatcher
from .stt import Mic, Transcriber
from .tts import TTSError

BANNER = r"""
  voice-pilot  ·  kouká a mluví (milník 1)
  ---------------------------------------
"""

STATE_TEXT = {
    "listening": "● poslouchám…",
    "thinking": "… přemýšlím",
    "speaking": "♪ mluvím",
}


class Pilot:
    """Tenká slupka nad `Engine` pro terminál. Okno používá Engine přímo."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.engine = Engine(cfg, on_event=self._on_event)
        self.engine.confirmer = self._potvrd
        self.mic = self.engine.mic
        self.transcriber = self.engine.transcriber
        self.speaker = self.engine.speaker
        self.brain = self.engine.brain
        self.last_answer = ""

    def _potvrd(self, popis: str, nebezpecna: bool) -> bool:
        print("")
        print(f"  akce: {popis}")
        if nebezpecna:
            print("  !! tohle se nedá vzít zpět")
        try:
            odpoved = input("  provést? [a/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return odpoved in ("a", "ano", "y", "yes")

    # --------------------------------------------------- události

    def _on_event(self, payload: dict) -> None:
        kind = payload["type"]

        if kind == "state":
            state = payload["value"]
            if state in STATE_TEXT:
                print(f"  {STATE_TEXT[state]}          ", end="\r", flush=True)

        elif kind == "heard":
            text = payload.get("text", "")
            seconds = payload.get("seconds")
            if text:
                suffix = f" ({seconds} s)" if seconds else ""
                print(f'  ty{suffix}: "{text}"')
            else:
                print("  (nic jsem neslyšel)\n")

        elif kind == "screen":
            print(f'  (vidím {payload["elements"]} prvků v okně "{payload["window"]}")')

        elif kind == "answer":
            self.last_answer = payload["text"]
            print(f'  pilot: "{payload["text"]}"')

        elif kind == "log":
            print(f"  {payload['text']}")

    # ------------------------------------------------------ běh

    def run(self) -> None:
        print(BANNER)

        ok, detail = self.engine.preflight()
        if not ok:
            print("  !! " + detail.replace("\n", "\n  ") + "\n")
            self._say("Nemůžu se spojit s OpenCode. Bez něj neumím myslet.")
            raise SystemExit(1)
        print(f"  mozek: {detail}")

        self._say("Pilot je připravený. Drž klávesu, mluv, a až domluvíš, pusť ji.")

        print(f"  klávesa: {self.cfg.hotkey} (držet)   ukončení: Ctrl+C\n")

        watcher = HotkeyWatcher(
            self.cfg.hotkey, self.engine.start_listening, self.engine.stop_listening
        )
        if not watcher.start():
            print("  !! globální klávesu se nepodařilo zaregistrovat\n")

        try:
            while True:
                time.sleep(0.3)
        except KeyboardInterrupt:
            pass
        finally:
            watcher.stop()
            self.engine.shutdown()
            print("\n  takhle někdy příště.")

    def handle(self, text: str) -> None:
        """Jeden dotaz, počká na odpověď. Používá se v testech a v textovém režimu."""
        self.last_answer = ""
        self.engine.ask(text, background=False)

    def _say(self, text: str) -> None:
        try:
            self.speaker.say(text)
        except TTSError as exc:
            print(f"  (hlas selhal: {exc})")


def text_mode(cfg) -> None:
    """Bez mikrofonu: piš otázky do terminálu. Na testování."""
    pilot = Pilot(cfg)
    print(BANNER)
    print("  textový režim — piš otázky, prázdný řádek ukončí\n")
    while True:
        try:
            line = input("  ty: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            break
        pilot.handle(line)


def listen_once(cfg) -> None:
    """Nahraje jednu větu a vypíše přepis. Na kalibraci mikrofonu."""
    print("  mluv… (Enter ukončí nahrávku)")
    mic = Mic(cfg.sample_rate)
    mic.start()
    input()
    audio = mic.stop()
    print(f"  nahráno {audio.size / cfg.sample_rate:.1f} s, přepisuju…")
    print(f'  přepis: "{Transcriber(cfg).transcribe(audio)}"')


def _configure_console() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
