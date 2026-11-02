"""Smyčka: držíš klávesu / mluvíš / on odpovídá."""

from __future__ import annotations

import queue
import sys
import threading
import time

import sounddevice as sd
from pynput import keyboard

from . import eyes
from .brain import Brain
from .oc import OpenCodeError
from .stt import Mic, Transcriber
from .tts import Speaker, TTSError

BANNER = r"""
  voice-pilot  ·  kouká a mluví (milník 1)
  ---------------------------------------
"""


class Pilot:
    def __init__(self, cfg):
        self.cfg = cfg
        self.transcriber = Transcriber(cfg)
        self.speaker = Speaker(cfg)
        self.brain = Brain(cfg)
        self.mic = Mic(cfg.sample_rate)
        self.events: queue.Queue[str] = queue.Queue()
        self._last_toggle = 0.0

    # ---------- běh ----------

    def run(self) -> None:
        print(BANNER)
        self._say("Pilot je připravený. Podrž nebo zmáčkni F9 a mluv.")

        hotkey = self.cfg.hotkey if self.cfg.hotkey.startswith("<") else f"<{self.cfg.hotkey}>"
        print(f"  klávesa: {self.cfg.hotkey}   ukončení: Ctrl+C\n")

        listener = keyboard.GlobalHotKeys({hotkey: self._on_hotkey})
        listener.start()

        try:
            while True:
                try:
                    self.events.get(timeout=0.5)
                except queue.Empty:
                    continue
                if self.mic.is_recording:
                    self._finish_recording()
                else:
                    self._begin_recording()
        except KeyboardInterrupt:
            pass
        finally:
            if self.mic.is_recording:
                self.mic.stop()
            listener.stop()
            print("\n  takhle někdy příště.")

    def _on_hotkey(self) -> None:
        now = time.monotonic()
        if now - self._last_toggle < 0.35:
            return
        self._last_toggle = now
        self.events.put("toggle")

    def _begin_recording(self) -> None:
        sd.stop()
        self.mic.start()
        print("  ● poslouchám…  (znovu F9 ukončí nahrávku)", end="\r", flush=True)

    def _finish_recording(self) -> None:
        audio = self.mic.stop()
        seconds = audio.size / self.cfg.sample_rate
        print(f"  ● nahráno {seconds:.1f} s, přepisuju…        ")

        text = self.transcriber.transcribe(audio)
        if not text:
            print("  (nic jsem neslyšel)\n")
            return

        print(f'  ty: "{text}"')
        self.handle(text)

    # ---------- jedna otázka ----------

    def handle(self, text: str) -> None:
        try:
            snap = eyes.snapshot(self.cfg)
            print(f'  (vidím {len(snap.elements)} prvků v okně "{snap.active_title}")')

            reply = self.brain.look_and_answer(text, snap)
        except OpenCodeError as exc:
            print(f"  chyba modelu: {exc}\n")
            self._say("Mozek mi neodpovídá. Zkontroluj, jestli běží OpenCode.")
            return
        except Exception as exc:
            print(f"  chyba: {exc}\n")
            return

        print(f'  pilot: "{reply.say}"\n')
        self._say(reply.say)

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
