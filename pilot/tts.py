"""Hlas: text -> řeč. Primárně edge-tts (přirozená čeština), záloha Piper."""

from __future__ import annotations

import asyncio
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import wave
from pathlib import Path

from typing import Callable

import numpy as np
import sounddevice as sd

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache" / "tts"

_PIPER_VOICES: dict[str, object] = {}


def _je_ascii(text: str) -> bool:
    return all(ord(ch) < 128 for ch in text)


def espeak_data_root() -> Path | None:
    """Najde data pro výslovnost, kterou Piper potřebuje.

    `espeak-ng` je knihovna v C a na Windows nezvládne cestu s diakritikou
    („Výchozí projekt“). Když balíček leží na takové cestě, data se jednou
    zkopírují do %LOCALAPPDATA%, kde je cesta čistě ASCII.
    """
    try:
        import piper
    except Exception:
        return None

    balicek = Path(piper.__file__).resolve().parent
    data = balicek / "espeak-ng-data"
    if not (data / "phontab").exists():
        return None

    if _je_ascii(str(balicek)):
        return balicek

    cil = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "voice-pilot" / "espeak"
    if not (cil / "espeak-ng-data" / "phontab").exists():
        cil.mkdir(parents=True, exist_ok=True)
        shutil.copytree(data, cil / "espeak-ng-data", dirs_exist_ok=True)
    return cil


def _piper_voice(model: Path):
    key = str(model)
    if key not in _PIPER_VOICES:
        from piper import PiperVoice

        _PIPER_VOICES[key] = PiperVoice.load(str(model))
    return _PIPER_VOICES[key]


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


class _NicNeprehrano(Exception):
    """Streamování selhalo dřív, než zazněl jediný tón — lze zkusit jinou cestu."""


class Speaker:
    def __init__(self, cfg):
        self.cfg = cfg
        CACHE.mkdir(parents=True, exist_ok=True)
        self._engine_used = ""
        self._prerusit = False
        self._vystup = None
        self.on_first_audio: Callable[[], None] | None = None
        self._prvni_zvuk = False

    def _oznam_prvni_zvuk(self) -> None:
        if self._prvni_zvuk:
            return
        self._prvni_zvuk = True
        if self.on_first_audio is not None:
            try:
                self.on_first_audio()
            except Exception:
                pass

    @property
    def engine_used(self) -> str:
        return self._engine_used

    # ---------- veřejné ----------

    def say(self, text: str) -> None:
        """Přečte text.

        U edge-tts se přehrává už během stahování — první zvuk je slyšet
        po pár desetinách sekundy místo po celé větě. Když to nevyjde,
        spadne se zpátky na dělení po větách.
        """
        text = (text or "").strip()
        if not text:
            return

        # nový výrok ruší předchozí přerušení
        self._prerusit = False
        self._prvni_zvuk = False

        if self.cfg.tts_engine in ("auto", "edge") and not self._prerusit:
            try:
                self._edge_stream(text)
                self._engine_used = "edge"
                return
            except _NicNeprehrano:
                pass

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

    # ---------- streamované přehrávání ----------

    def _edge_stream(self, text: str) -> None:
        """Stahuje zvuk z edge-tts a hraje ho za pochodu."""
        import edge_tts
        import miniaudio

        fronta: queue.Queue = queue.Queue()
        konec = object()

        def producent() -> None:
            async def bez() -> None:
                komunikace = edge_tts.Communicate(
                    text, self.cfg.voice, rate=self.cfg.speech_rate
                )
                async for kus in komunikace.stream():
                    if kus.get("type") == "audio":
                        fronta.put(kus["data"])

            try:
                asyncio.run(bez())
                fronta.put(konec)
            except Exception as exc:
                fronta.put(exc)

        threading.Thread(target=producent, daemon=True).start()

        buffer = bytearray()
        prehrano = 0
        vystup = None
        self._prerusit = False

        def predej(konec_streamu: bool) -> None:
            nonlocal prehrano, vystup
            if not buffer:
                return
            # Menší práh = dřívější první zvuk. 1200 B je zhruba 0,2 s řeči;
            # dekódování zvládne i buffer uříznutý uprostřed rámce.
            if not konec_streamu and len(buffer) < 1200:
                return
            try:
                dek = miniaudio.decode(
                    bytes(buffer),
                    output_format=miniaudio.SampleFormat.SIGNED16,
                    nchannels=1,
                )
            except Exception:
                return

            audio = np.frombuffer(dek.samples, dtype=np.int16)
            if vystup is None:
                vystup = sd.OutputStream(
                    samplerate=dek.sample_rate, channels=1, dtype="int16"
                )
                vystup.start()
                self._vystup = vystup

            nove = audio[prehrano:]
            if nove.size:
                vystup.write(nove)
                prehrano = audio.size
                self._oznam_prvni_zvuk()

        try:
            while True:
                if self._prerusit:
                    return
                polozka = fronta.get()

                if polozka is konec:
                    predej(True)
                    break

                if isinstance(polozka, Exception):
                    if vystup is None:
                        raise _NicNeprehrano(str(polozka))
                    break

                buffer.extend(polozka)
                predej(False)

            if vystup is None:
                raise _NicNeprehrano("edge-tts nevrátil zvuk")
        finally:
            self._vystup = None
            if vystup is not None:
                try:
                    vystup.stop()
                    vystup.close()
                except Exception:
                    pass

    def stop(self) -> None:
        """Přeruší právě hrající hlas (uživatel začal mluvit)."""
        self._prerusit = True
        vystup = self._vystup
        if vystup is not None:
            try:
                vystup.abort()
            except Exception:
                pass

    def prewarm(self) -> None:
        """Načte model Piperu na pozadí, aby první odpověď nečekala 3,7 s."""
        if self.cfg.tts_engine not in ("piper", "auto"):
            return

        def nacti() -> None:
            try:
                model = Path(self.cfg.piper_model) if self.cfg.piper_model else _default_piper()
                if not model.exists():
                    return
                root = espeak_data_root()
                if root is not None:
                    os.environ["ESPEAK_DATA_PATH"] = str(root)
                _piper_voice(model)
            except Exception:
                pass

        threading.Thread(target=nacti, daemon=True).start()

    # ---------- výroba jednoho souboru ----------

    def _render(self, text: str, index: int) -> tuple[Path | None, str]:
        order = ["edge", "piper"] if self.cfg.tts_engine == "auto" else [self.cfg.tts_engine]
        errors: list[str] = []

        for engine in order:
            try:
                if engine == "edge":
                    path = self._edge(text, index)
                elif engine == "piper":
                    path = self._piper(text, index)
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

    def _piper(self, text: str, index: int = 0) -> Path:
        model = Path(self.cfg.piper_model) if self.cfg.piper_model else _default_piper()
        if not model.exists():
            raise TTSError(
                f"Piper model nenalezen ({model}). Spusť: python run.py --setup-piper"
            )

        if self.cfg.language == "en" and "cs_CZ" in model.name:
            raise TTSError(
                "Piper má stažený jen český hlas. Pro angličtinu přepni na "
                "edge-tts, nebo si stáhni anglický model Piperu."
            )

        root = espeak_data_root()
        if root is not None:
            os.environ["ESPEAK_DATA_PATH"] = str(root)

        # Vlastní soubor pro každou část — jinak druhá věta přepíše první
        # dřív, než se stihne přečíst, a přehrávač dostane prázdno.
        out = CACHE / f"speech-{index}.wav"

        try:
            voice = _piper_voice(model)
        except ImportError:
            voice = None

        if voice is not None:
            with wave.open(str(out), "wb") as wf:
                voice.synthesize_wav(text, wf)
        else:
            exe = shutil.which("piper")
            if not exe:
                raise TTSError("Piper není nainstalovaný. Spusť: python run.py --setup-piper")

            proc = subprocess.run(
                [exe, "-m", str(model), "-f", str(out)],
                input=text.encode("utf-8"),
                capture_output=True,
            )
            if proc.returncode != 0:
                raise TTSError(proc.stderr.decode("utf-8", "replace")[:200])

        if not out.exists() or out.stat().st_size < 2000:
            raise TTSError("Piper vyrobil prázdný soubor")

        return out

    # ---------- přehrání ----------

    def _decode(self, path: Path) -> tuple[np.ndarray, int]:
        """Přečte soubor na zvuk. Cesta se nikdy nepředává nativní knihovně.

        Knihovny psané v C na Windows nezvládnou cestu s českou diakritikou
        (projekt může být ve složce „Výchozí projekt“), takže se soubor
        načte po bajtech a dekóduje z paměti.
        """
        raw = path.read_bytes()
        if len(raw) < 44:
            raise TTSError(f"Zvukový soubor je prázdný ({path.name})")

        if path.suffix.lower() == ".wav":
            import io
            import wave

            try:
                with wave.open(io.BytesIO(raw), "rb") as wf:
                    rate = wf.getframerate()
                    audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
            except Exception as exc:
                raise TTSError(f"WAV se nepodařilo přečíst ({path.name}): {exc}") from exc
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
        self._oznam_prvni_zvuk()
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
    import sys

    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "piper-tts"],
        check=False,
    )
    print("  hotovo.")
