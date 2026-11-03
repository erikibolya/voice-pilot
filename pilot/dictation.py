"""Průběžné diktování: mikrofon zůstane otevřený, věty se oddělují tichem.

Uživatel zmáčkne F9, mluví, a jakmile na chvíli přestane, věta se přepíše
a provede. Nemusí mačkat nic dalšího. Druhá F9 režim vypne.
"""

from __future__ import annotations

import queue
import threading
from typing import Callable

import numpy as np
import sounddevice as sd


class DictationSession:
    """Poslouchá pořád a krájí řeč na věty podle ticha."""

    def __init__(
        self,
        cfg,
        on_utterance: Callable[[np.ndarray], None],
        on_level: Callable[[float], None] | None = None,
    ):
        self.cfg = cfg
        self.on_utterance = on_utterance
        self.on_level = on_level

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def bezi(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.bezi:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._smycka, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    # ------------------------------------------------------------ smyčka

    def _smycka(self) -> None:
        bloky: queue.Queue = queue.Queue()

        def zachyt(indata, frames, time_info, status) -> None:  # noqa: ARG001
            bloky.put(indata.copy())

        sirka = 1.0 / 60  # přibližná délka jednoho bloku

        try:
            with sd.InputStream(
                samplerate=self.cfg.sample_rate,
                channels=1,
                dtype="float32",
                callback=zachyt,
            ):
                utrzek: list[np.ndarray] = []
                ticho = 0.0
                receno = 0.0

                while not self._stop.is_set():
                    try:
                        blok = bloky.get(timeout=0.15)
                    except queue.Empty:
                        continue

                    delka = blok.shape[0] / self.cfg.sample_rate
                    uroven = float(np.sqrt(np.mean(blok**2)))

                    if self.on_level is not None:
                        try:
                            self.on_level(min(1.0, uroven * 6.0))
                        except Exception:
                            pass

                    if uroven > self.cfg.vad_threshold:
                        utrzek.append(blok)
                        receno += delka
                        ticho = 0.0
                        continue

                    if not utrzek:
                        continue

                    utrzek.append(blok)
                    ticho += delka

                    if ticho >= self.cfg.vad_silence_seconds and receno >= self.cfg.min_speech_seconds:
                        audio = np.concatenate(utrzek).flatten()
                        utrzek, ticho, receno = [], 0.0, 0.0
                        try:
                            self.on_utterance(audio)
                        except Exception:
                            pass
        except Exception:
            return


def energia(audio: np.ndarray) -> float:
    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(audio**2)))
