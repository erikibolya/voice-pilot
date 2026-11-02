"""Smyčka TTS -> STT: vyrobí českou nahrávku a nechá Whisper přepsat.

Ověřuje obě strany audio řetězu bez mikrofonu, takže se dá pustit kdykoli.
"""

from __future__ import annotations

import asyncio
import io
import sys
import time

import miniaudio
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

from pilot.config import load
from pilot.stt import Transcriber

VETA = "Otevři mi prosím složku s fakturami a podívej se, kolik je tam souborů."


def make_audio(text: str, sample_rate: int) -> np.ndarray:
    import edge_tts

    out = "cache/tts/stt_probe.mp3"
    asyncio.run(edge_tts.Communicate(text, "cs-CZ-VlastaNeural").save(out))

    decoded = miniaudio.decode(
        open(out, "rb").read(),
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,
        sample_rate=sample_rate,
    )
    pcm = np.frombuffer(decoded.samples, dtype=np.int16)
    return (pcm.astype(np.float32) / 32768.0).copy()


def main() -> int:
    cfg = load()
    print(f"zdrojová věta: {VETA}")

    print("  vyrábím nahrávku…", end=" ", flush=True)
    audio = make_audio(VETA, cfg.sample_rate)
    print(f"{audio.size / cfg.sample_rate:.1f} s")

    print("  načítám Whisper…", end=" ", flush=True)
    t0 = time.monotonic()
    tr = Transcriber(cfg)
    tr._load()
    print(f"{time.monotonic() - t0:.1f} s")

    t0 = time.monotonic()
    text = tr.transcribe(audio)
    elapsed = time.monotonic() - t0
    print(f'  přepis ({elapsed:.1f} s): "{text}"')

    words_src = set(VETA.lower().replace(",", "").split())
    words_out = set(text.lower().replace(",", "").split())
    hit = len(words_src & words_out) / len(words_src)
    print(f"  shoda slov: {hit:.0%}")

    return 0 if hit >= 0.8 else 1


if __name__ == "__main__":
    sys.exit(main())
