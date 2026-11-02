"""Měření odezvy: kolik času spolkne který krok.

Spuštění:  .venv\\Scripts\\python.exe bench.py
Nepotřebuje mikrofon — nahrávku si vyrobí z TTS a pošle ji do přepisu.
Hlas se nepřehrává, měří se jen jeho výroba.
"""

from __future__ import annotations

import asyncio
import statistics
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from pilot import eyes
from pilot.config import load
from pilot.oc import OpenCode
from pilot.stt import Transcriber
from pilot.tts import Speaker

VETA = "Otevři mi prosím složku s fakturami a řekni, kolik tam je souborů."
OPAKOVANI = 3


def make_audio(cfg, text: str):
    import miniaudio
    import numpy as np

    out = Path("cache/tts/bench.mp3")
    out.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(__import__("edge_tts").Communicate(text, cfg.voice).save(str(out)))
    decoded = miniaudio.decode(
        out.read_bytes(),
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,
        sample_rate=cfg.sample_rate,
    )
    pcm = np.frombuffer(decoded.samples, dtype=np.int16)
    return (pcm.astype(np.float32) / 32768.0).copy()


def razitko(fn, *args, **kwargs):
    t0 = time.monotonic()
    vysledek = fn(*args, **kwargs)
    return time.monotonic() - t0, vysledek


def main() -> int:
    cfg = load()
    print("=" * 62)
    print(" voice-pilot — měření odezvy")
    print("=" * 62)

    # --- 1. přepis ------------------------------------------------------
    print("\n[1] Přepis řeči (Whisper)")
    audio = make_audio(cfg, VETA)
    tr = Transcriber(cfg)
    tr._load()
    print(f"    nahrávka: {audio.size / cfg.sample_rate:.1f} s, zařízení: {tr.device_used.upper()}")

    casy = []
    for _ in range(OPAKOVANI):
        dt, text = razitko(tr.transcribe, audio)
        casy.append(dt)
    print(f"    {statistics.mean(casy):.2f} s  (min {min(casy):.2f}, max {max(casy):.2f})")
    print(f"    přepis: {text[:60]}…")

    # --- 2. čtení obrazovky --------------------------------------------
    print("\n[2] Čtení obrazovky (UI Automation)")
    casy_eyes = {}
    for limit in (20, 40, 70, 120):
        cfg.max_elements = limit
        dt, snap = razitko(eyes.snapshot, cfg)
        casy_eyes[limit] = dt
        print(f"    max_elements={limit:3d} → {dt:.2f} s, přečteno {len(snap.elements)} prvků")
    cfg.max_elements = 70
    dt, snap = razitko(eyes.snapshot, cfg)
    t_eyes = dt

    # --- 3. model -------------------------------------------------------
    print("\n[3] Model")
    client = OpenCode(cfg.service_url, cfg.service_password_file, cfg.provider_id, cfg.model_id)
    from pilot.brain import Brain

    brain = Brain(cfg, client)
    prompt = brain._build_prompt("Co je na obrazovce?", snap)
    znaku = len(prompt)
    dt_model, odpoved = razitko(client.generate, prompt)
    print(f"    prompt: {znaku} znaků, odpověď: {len(odpoved)} znaků")
    print(f"    {dt_model:.2f} s")

    # --- 4. hlas --------------------------------------------------------
    print("\n[4] Hlas (edge-tts)")
    from pilot.tts import split_sentences

    speaker = Speaker(cfg)
    vety = split_sentences(odpoved)
    print(f"    odpověď se dělí na {len(vety)} částí")

    dt_prvni, cesta = razitko(speaker._edge, vety[0], 0)
    print(f"    do prvního zvuku: {dt_prvni:.2f} s   ← tohle uživatel slyší")

    dt_plny, _ = razitko(speaker._edge, odpoved, 1)
    print(f"    celá odpověď:     {dt_plny:.2f} s   (zbytek se kryje s mluvením)")

    dt, (zvuk, rate) = razitko(speaker._decode, cesta)
    print(f"    dekódování:       {dt:.3f} s ({zvuk.size / rate:.1f} s zvuku)")

    # --- souhrn ---------------------------------------------------------
    t_stt = statistics.mean(casy)

    pred = t_stt + t_eyes + dt_model + dt_plny
    po = max(t_stt, t_eyes) + dt_model + dt_prvni

    print("\n" + "=" * 62)
    print(" Jak dlouho čekáš, než začne mluvit")
    print("=" * 62)
    print(f"    přepis a obrazovka   {max(t_stt, t_eyes):5.2f} s  (souběžně)")
    print(f"    model                {dt_model:5.2f} s")
    print(f"    hlas do prvního zvuku {dt_prvni:5.2f} s")
    print(f"    {'─' * 40}")
    print(f"    teď                  {po:5.2f} s")
    print(f"    před úpravou         {pred:5.2f} s   (čekalo se na celý hlas)")
    print(f"    úspora              {pred - po:5.2f} s  ({(1 - po / pred) * 100:.0f} %)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
