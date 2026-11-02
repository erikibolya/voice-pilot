"""Uši: mikrofon a přepis přes Whisper (běží lokálně na GPU)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

import sounddevice as sd


class Mic:
    """Nahrává z mikrofonu, dokud se nezavolá stop()."""

    def __init__(self, sample_rate: int = 16000, device: int | None = None):
        self.sample_rate = sample_rate
        self.device = device
        self._stream: sd.InputStream | None = None
        self._chunks: list[np.ndarray] = []

    def start(self) -> None:
        self._chunks = []
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            device=self.device,
            callback=self._callback,
        )
        self._stream.start()

    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ARG002
        self._chunks.append(indata.copy())

    def stop(self) -> np.ndarray:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if not self._chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._chunks, axis=0).flatten()

    @property
    def is_recording(self) -> bool:
        return self._stream is not None


class Transcriber:
    """Drží Whisper model v paměti, aby se nenačítal při každé větě."""

    def __init__(self, cfg):
        self.cfg = cfg
        self._model = None
        self.device_used = ""

    def _load(self):
        if self._model is not None:
            return self._model

        from faster_whisper import WhisperModel

        print(f"  načítám Whisper {self.cfg.whisper_model}…", end=" ", flush=True)

        if self.cfg.whisper_device == "cuda":
            try:
                _enable_cuda_dlls()
                self._model = WhisperModel(
                    self.cfg.whisper_model,
                    device="cuda",
                    compute_type=self.cfg.whisper_compute,
                )
                self.device_used = "gpu"
                print("běží na GPU")
                return self._model
            except Exception as exc:
                print(f"GPU nedostupná ({exc}) — přepínám na CPU, bude to pomalejší")
                print("  načítám znovu na CPU…", end=" ", flush=True)

        self._model = WhisperModel(
            self.cfg.whisper_model,
            device="cpu",
            compute_type="int8",
        )
        self.device_used = "cpu"
        print("běží na CPU")
        return self._model

    def transcribe(self, audio: np.ndarray) -> str:
        audio = trim_silence(audio)
        if audio.size == 0:
            return ""

        if audio.size / self.cfg.sample_rate < self.cfg.min_speech_seconds:
            return ""

        # Whisper je trénovaný na normální hlasitosti. Slabý mikrofon nebo
        # tichý mluvčí jinak ztrácí přesnost, takže nahrávku srovnáme.
        audio = normalize(audio)

        segments, _info = self._load().transcribe(
            audio,
            language=self.cfg.language,
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=False,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()


def _enable_cuda_dlls() -> None:
    """Zpřístupní cuBLAS a cuDNN z pip balíčků (Windows je sám nenajde)."""
    import os
    import sysconfig

    site = Path(sysconfig.get_paths()["purelib"])
    found: list[str] = []
    for package in ("cublas", "cudnn", "cuda_nvrtc"):
        for candidate in (
            site / "nvidia" / package / "bin",
            site / "nvidia" / package / "lib",
        ):
            if candidate.exists():
                try:
                    os.add_dll_directory(str(candidate))
                except Exception:
                    pass
                found.append(str(candidate))

    if found:
        os.environ["PATH"] = os.pathsep.join(found) + os.pathsep + os.environ.get("PATH", "")


def normalize(audio: np.ndarray, target: float = 0.9) -> np.ndarray:
    """Srovná hlasitost na rozumnou úroveň, ať je mikrofon jakkoli tichý."""
    if audio.size == 0:
        return audio
    peak = float(np.abs(audio).max())
    if peak <= 1e-6:
        return audio
    return (audio * (target / peak)).astype(np.float32)


def trim_silence(audio: np.ndarray, threshold: float = 0.012, pad: int = 1600) -> np.ndarray:
    """Odřízne ticho na začátku a konci nahrávky."""
    if audio.size == 0:
        return audio

    loud = np.abs(audio) > threshold
    if not loud.any():
        return np.zeros(0, dtype=np.float32)

    start = max(0, int(np.argmax(loud)) - pad)
    end = min(audio.size, len(audio) - int(np.argmax(loud[::-1])) + pad)
    return audio[start:end]


def list_devices() -> str:
    lines = []
    for i, dev in enumerate(sd.query_devices()):
        mark = " *" if i == sd.default.device[0] else ""
        if dev["max_input_channels"] > 0:
            lines.append(f"  [{i}] {dev['name']} ({dev['max_input_channels']} kan.){mark}")
    return "\n".join(lines) if lines else "  (žádný mikrofon nenalezen)"
