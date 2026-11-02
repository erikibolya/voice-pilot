"""Živá kontrola: projde celé kolo se skutečným mikrofonem.

Co ověří:
  mikrofon -> Whisper -> UI Automation -> OpenCode -> reproduktory

Co neověří: samotný stisk F9. Pynput záměrně ignoruje syntetické klávesy
(`if not injected`), aby aplikace nemohly spouštět tvoje hotkey. Klávesu
tedy musí zmáčknout člověk — vyzkoušej to jednou ručně přes `run.py`.

Použití:
    .venv\\Scripts\\python.exe live_check.py              # 5 s nahrávání
    .venv\\Scripts\\python.exe live_check.py --seconds 8
    .venv\\Scripts\\python.exe live_check.py --ticho       # bez mikrofonu, ticho
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--ticho", action="store_true", help="přeskočit mikrofon, poslat ticho")
    args = parser.parse_args()

    from pilot.app import Pilot
    from pilot.config import load

    cfg = load()
    pilot = Pilot(cfg)

    print("=" * 60)
    print(" živá kontrola voice-pilotu")
    print("=" * 60)

    # --- 1. mikrofon -------------------------------------------------------
    if args.ticho:
        import numpy as np

        audio = np.zeros(int(cfg.sample_rate * 1.5), dtype=np.float32)
        print("[1/3] mikrofon: přeskakuji, posílám 1,5 s ticha")
    else:
        print(f"[1/3] mikrofon: nahrávám {args.seconds:.0f} s — MLUV TEĎ")
        pilot.mic.start()
        time.sleep(args.seconds)
        audio = pilot.mic.stop()
        print(f"      nahráno {audio.size / cfg.sample_rate:.1f} s")

    # --- 2. přepis ---------------------------------------------------------
    print("[2/3] přepis (Whisper): ", end="", flush=True)
    t0 = time.monotonic()
    text = pilot.transcriber.transcribe(audio)
    dt = time.monotonic() - t0
    print(f"{dt:.1f} s  [{(pilot.transcriber.device_used or '?').upper()}]")

    if not text:
        print("\nVÝSLEDEK: řetěz prošel, ale nebylo co přepsat (ticho).")
        print("  Mikrofon funguje, Whisper nenašel řeč. Zkus to znovu a mluv.")
        return 2

    print(f'      "ty: {text}"')

    # --- 3+4. obrazovka, model, hlas --------------------------------------
    print("[3/3] obrazovka + model…")
    t0 = time.monotonic()
    pilot.handle(text)
    dt = time.monotonic() - t0
    print(f"      kolo se odehrálo za {dt:.1f} s (včetně přehrání hlasu)")

    print("\nVÝSLEDEK: celé kolo prošlo.")
    print("  Jediné, co ještě zbývá ručně: zmáčknout F9 v `python run.py`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
