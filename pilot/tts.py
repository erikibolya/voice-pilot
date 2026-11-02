"""Hlas: text -> řeč. Primárně edge-tts (přirozená čeština), záloha Piper."""

from __future__ import annotations

import asyncio
import queue
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache" / "tts"


def split_sentences(text: str, limit: int = 180) -> list[str]:
    """Rozdělí text na kousky, které jde vyrábět po částech.

    Krátká odpověď zůstane jedním kusem. Dlouhá se dělí po větách; když je
    i věta moc dlouhá, řeže se u čárky nebo mezery.
    """
    text = " ".join((text or "").split())
    if not text:
        return []

    parts = re.split(r"(?<=[.!?…])\s+", text)
    out: list[str] = []

    for part in parts:
        part = part.strip()
        while len(part) > limit:
            cut = part.rfind(",", 0, limit)
            if cut < limit // 3:
                cut = part.rfind(" ", 0, limit)
            if cut <= 0:
                cut = limit
            out.append(part[: cut + 1].strip())
            part = part[cut + 1 :].strip()
        if part:
            out.append(part)

    return out or [text]


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
        """Přečte text. U delších odpovědí mluví dřív, než je celá hotová.

        Generování hlasu trvá u delší věty přes dvě sekundy a dřív se čekalo
        na celý soubor. Teď se text rozdělí na věty, první se vyrobí hned a
        zbytek se připravuje, zatímco už mluvíme.
        """
        text = (text or "").strip()
        if not text:
            return

        sentences = split_sentences(text)
        errors: list[str] = []

        if len(sentences) <= 1:
            path, error = self._render(text, 0)
            if path is None:
                raise TTSError(error)
            self._play(path)
            return

        prepared: queue.Queue = queue.Queue()

        def produce() -> None:
            for index, sentence in enumerate(sentences):
                prepared.put(self._render(sentence, index))
            prepared.put(None)

        threading.Thread(target=produce, daemon=True).start()

        while True:
            item = prepared.get()
            if item is None:
                break
            path, error = item
            if path is None:
                errors.append(error)
                continue
            self._play(path)

        if errors and len(errors) == len(sentences):
            raise TTSError("hlas nefungoval → " + "; ".join(errors))

    # ---------- výroba jednoho souboru ----------

    def _render(self, text: str, index: int) -> tuple[Path | None, str]:
        order = ["edge", "piper"] if self.cfg.tts_engine == "auto" else [self.cfg.tts_engine]
        errors: list[str] = []

        for engine in order:
            try:
                if engine == "edge":
                    path = self._edge(text, index)
                elif engine == "piper":
                    path = self._piper(text)
                else:
                    raise TTSError(f"neznámý engine {engine!r}")
                self._engine_used = engine
                return path, ""
            except Exception as exc:
                errors.append(f"{engine}: {exc}")
                if self.cfg.tts_engine != "auto":
                    break

        return None, "; ".join(errors)

    # ---------- edge-tts ----------

    def _edge(self, text: str, index: int = 0) -> Path:
        import edge_tts

        out = CACHE / f"speech-{index}.mp3"
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

    def _decode(self, path: Path) -> tuple[np.ndarray, int]:
        """Přečte soubor na zvuk. Cesta se nikdy nepředává nativní knihovně.

        Knihovny psané v C na Windows nezvládnou cestu s českou diakritikou
        (projekt může být ve složce „Výchozí projekt“), takže se soubor
        načte po bajtech a dekóduje z paměti.
        """
        raw = path.read_bytes()

        if path.suffix.lower() == ".wav":
            import io
            import wave

            with wave.open(io.BytesIO(raw), "rb") as wf:
                rate = wf.getframerate()
                audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
            return audio, rate

        import miniaudio

        decoded = miniaudio.decode(
            raw,
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=1,
        )
        return np.frombuffer(decoded.samples, dtype=np.int16), decoded.sample_rate

    def _play(self, path: Path) -> None:
        audio, rate = self._decode(path)
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
