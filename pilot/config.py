"""Konfigurace voice-pilotu. Ukládá se do config.json vedle projektu."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"


@dataclass
class Config:
    # --- OpenCode jako mozek ---
    service_url: str = "http://127.0.0.1:28894"
    service_password_file: str = str(Path.home() / ".config" / "opencode" / "service.json")
    provider_id: str = "deepseek"
    model_id: str = "deepseek-flash"

    # --- Uši: Whisper ---
    whisper_model: str = "large-v3"
    whisper_device: str = "cuda"
    whisper_compute: str = "float16"
    language: str = "cs"
    sample_rate: int = 16000
    # pod tuto délku zvuku se nahrávka zahodí (mlasknutí apod.)
    min_speech_seconds: float = 0.4

    # --- Hlas: TTS ---
    tts_engine: str = "auto"  # auto | edge | piper
    voice: str = "cs-CZ-VlastaNeural"
    piper_model: str = ""  # cesta k .onnx, když je prázdná, použije se výchozí
    speech_rate: str = "+8%"

    # --- Oči: UI Automation ---
    max_elements: int = 70
    max_depth: int = 7
    ui_budget_seconds: float = 3.0
    include_all_windows: bool = True

    # --- Ovládání ---
    hotkey: str = "f9"

    def save(self) -> None:
        CONFIG_PATH.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def load() -> Config:
    if not CONFIG_PATH.exists():
        cfg = Config()
        cfg.save()
        return cfg

    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    known = {f.name for f in fields(Config)}
    return Config(**{k: v for k, v in raw.items() if k in known})
