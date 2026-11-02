"""Zajistí, že testy najdou balíček pilot i při spuštění odjinud."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
