#!/usr/bin/env python
"""voice-pilot — hlasový asistent, který kouká na obrazovku a mluví.

Použití:
    python run.py                 # hlavní smyčka (klávesa F9)
    python run.py --text          # bez mikrofonu, piš do terminálu
    python run.py --look          # co je právě na obrazovce
    python run.py --say "text"    # vyzkoušet hlas
    python run.py --mic           # nahrát jednu větu a vypsat přepis
    python run.py --devices       # seznam mikrofonů
    python run.py --setup-piper   # stáhnout offline hlas
"""

from __future__ import annotations

import argparse
import sys

from pilot import config
from pilot.app import _configure_console, listen_once, text_mode


def main() -> int:
    _configure_console()

    parser = argparse.ArgumentParser(add_help=True, description="voice-pilot")
    parser.add_argument("--text", action="store_true", help="textový režim bez mikrofonu")
    parser.add_argument("--look", action="store_true", help="popsat obrazovku")
    parser.add_argument("--say", metavar="TEXT", help="přečíst text nahlas")
    parser.add_argument("--mic", action="store_true", help="nahrát jednu větu")
    parser.add_argument("--devices", action="store_true", help="seznam mikrofonů")
    parser.add_argument("--setup-piper", action="store_true", help="nainstalovat offline hlas")
    parser.add_argument("--model", help="přepsat model, např. deepseek-v4-pro")
    args = parser.parse_args()

    cfg = config.load()
    if args.model:
        cfg.model_id = args.model
        cfg.save()

    if args.devices:
        from pilot.stt import list_devices

        print("mikrofony:")
        print(list_devices())
        return 0

    if args.setup_piper:
        from pilot.tts import setup_piper

        setup_piper()
        return 0

    if args.say:
        from pilot.tts import Speaker

        Speaker(cfg).say(args.say)
        return 0

    if args.look:
        from pilot.brain import Brain

        reply = Brain(cfg).describe_screen()
        print(f'pilot: "{reply.say}"')
        return 0

    if args.mic:
        listen_once(cfg)
        return 0

    if args.text:
        text_mode(cfg)
        return 0

    from pilot.app import Pilot

    Pilot(cfg).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
