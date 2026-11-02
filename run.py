#!/usr/bin/env python
"""voice-pilot — hlasový asistent, který kouká na obrazovku a mluví.

Použití:
    python run.py                 # okno s ikonou v liště (výchozí)
    python run.py --cli           # terminálová smyčka
    python run.py --text          # bez mikrofonu, piš do terminálu
    python run.py --look          # co je právě na obrazovce
    python run.py --say "text"    # vyzkoušet hlas
    python run.py --mic           # nahrát jednu větu a vypsat přepis
    python run.py --devices       # seznam mikrofonů
    python run.py --check-update  # zeptat se GitHubu na novou verzi
    python run.py --setup-piper   # stáhnout offline hlas
"""

from __future__ import annotations

import argparse
import sys

from pilot import __version__, config
from pilot.app import _configure_console, listen_once, text_mode


def main() -> int:
    _configure_console()

    parser = argparse.ArgumentParser(add_help=True, description="voice-pilot")
    parser.add_argument("--gui", action="store_true", help="okno (výchozí)")
    parser.add_argument("--cli", action="store_true", help="terminálová smyčka")
    parser.add_argument("--text", action="store_true", help="textový režim bez mikrofonu")
    parser.add_argument("--look", action="store_true", help="popsat obrazovku")
    parser.add_argument("--say", metavar="TEXT", help="přečíst text nahlas")
    parser.add_argument("--mic", action="store_true", help="nahrát jednu větu")
    parser.add_argument("--devices", action="store_true", help="seznam mikrofonů")
    parser.add_argument("--check-update", action="store_true", help="zkontrolovat aktualizace")
    parser.add_argument("--setup-piper", action="store_true", help="nainstalovat offline hlas")
    parser.add_argument("--model", help="přepsat model, např. deepseek-v4-pro")
    parser.add_argument("--version", action="version", version=f"voice-pilot {__version__}")
    parser.add_argument("--render", metavar="PNG", help="vykreslit okno do souboru (bez zobrazení)")
    parser.add_argument("--theme", choices=["dark", "light"], default="dark")
    args = parser.parse_args()

    cfg = config.load()
    if args.model:
        cfg.model_id = args.model
        cfg.save()

    if args.render:
        from pilot.ui.app import render_png

        path = render_png(args.render, cfg, theme=args.theme)
        print(f"snímek: {path}")
        return 0
    if args.devices:
        from pilot.stt import list_devices

        print("mikrofony:")
        print(list_devices())
        return 0

    if args.setup_piper:
        from pilot.tts import setup_piper

        setup_piper()
        return 0

    if args.check_update:
        from pilot import updater

        update, message = updater.check()
        print(message)
        if update:
            print(f"  ke stažení: {update.url}")
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

    if args.cli:
        from pilot.app import Pilot

        Pilot(cfg).run()
        return 0

    from pilot.ui.app import run as run_gui

    return run_gui(cfg)


if __name__ == "__main__":
    sys.exit(main())
