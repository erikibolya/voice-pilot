"""Hlas: text -> řeč. Primárně edge-tts (přirozená čeština), záloha Piper."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import sounddevice as sd

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache" / "tts"


class TTSError(RuntimeError):
    pass


class Speaker:
    def __init__(self, cfg):
        self.cfg = cfg
        CACHE.mkdir(parents=True, exist_ok=True)
        self._engine_used = ""

    @property
    def engine_used(self) -> str:
        return self._engine_used

    # ---------- veřejné ----------

    def say(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return

        order = ["edge", "piper"] if self.cfg.tts_engine == "auto" else [self.cfg.tts_engine]
        errors: list[str] = []

        for engine in order:
            try:
                if engine == "edge":
                    path = self._edge(text)
                elif engine == "piper":
                    path = self._piper(text)
                else:
                    raise TTSError(f"neznámý engine {engine!r}")
                self._engine_used = engine
                self._play(path)
                return
            except Exception as exc:
                errors.append(f"{engine}: {exc}")
                if self.cfg.tts_engine != "auto":
                    raise

        raise TTSError("hlas nefungoval → " + "; ".join(errors))

    # ---------- edge-tts ----------

    def _edge(self, text: str) -> Path:
        import edge_tts

        out = CACHE / "speech.mp3"
        communicate = edge_tts.Communicate(text, self.cfg.voice, rate=self.cfg.speech_rate)
        asyncio.run(communicate.save(str(out)))
        if not out.exists() or out.stat().st_size < 1000:
            raise TTSError("edge-tts vrátil prázdný soubor")
        return out

    # ---------- piper ----------

    def _piper(self, text: str) -> Path:
        model = Path(self.cfg.piper_model) if self.cfg.piper_model else _default_piper()
        if not model.exists():
            raise TTSError(
                f"Piper model nenalezen ({model}). Spusť: python run.py --setup-piper"
            )

        out = CACHE / "speech.wav"
        exe = shutil.which("piper")
        if exe:
            cmd = [exe, "-m", str(model), "-f", str(out)]
            proc = subprocess.run(cmd, input=text.encode("utf-8"), capture_output=True)
            if proc.returncode != 0:
                raise TTSError(proc.stderr.decode("utf-8", "replace")[:200])
            return out

        # python API balíčku piper-tts
        from piper import PiperVoice

        voice = PiperVoice.load(str(model))
        with open(out, "wb") as fh:
            voice.synthesize_wav(text, fh)
        return out

    # ---------- přehrání ----------

    def _play(self, path: Path) -> None:
        # Soubor čteme po bajtech, ne cestou: knihovny psané v C na Windows
        # nezvládnou cestu s českou diakritikou (project je "Výchozí projekt").
        raw = path.read_bytes()

        if path.suffix.lower() == ".wav":
            import io
            import wave

            with wave.open(io.BytesIO(raw), "rb") as wf:
                rate = wf.getframerate()
                audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        else:
            import miniaudio

            decoded = miniaudio.decode(
                raw,
                output_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=1,
            )
            rate = decoded.sample_rate
            audio = np.frombuffer(decoded.samples, dtype=np.int16)

        sd.play(audio, rate)
        sd.wait()


def _default_piper() -> Path:
    return ROOT / "models" / "cs_CZ-jirka-medium.onnx"


def setup_piper() -> None:
    """Stáhne český hlas pro Piper a nainstaluje balíček. Jen na vyžádání."""
    import urllib.request

    target = _default_piper()
    target.parent.mkdir(parents=True, exist_ok=True)

    base = (
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
        "cs/cs_CZ/jirka/medium/"
    )
    for filename in ("cs_CZ-jirka-medium.onnx", "cs_CZ-jirka-medium.onnx.json"):
        dest = target.parent / filename
        if dest.exists():
            print(f"  už existuje: {filename}")
            continue
        print(f"  stahuji {filename} ...")
        urllib.request.urlretrieve(base + filename, dest)

    print("  instaluji piper-tts ...")
    subprocess.run(
        [str(Path(__file__).resolve().parent.parent / ".venv" / "Scripts" / "python.exe"),
         "-m", "pip", "install", "-q", "piper-tts"],
        check=False,
    )
    print("  hotovo.")
