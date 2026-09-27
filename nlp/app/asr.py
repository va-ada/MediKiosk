"""Speech recognition: IndicConformer loaded in a background thread, ffmpeg audio conversion, confidence heuristic."""

import io
import logging
import re
import subprocess
import threading
import time
import wave
from collections.abc import Callable
from typing import Any

from app.config import settings

log = logging.getLogger("nlp.asr")

SAMPLE_RATE = 16_000

# Letters of the script we expect the transcript to be written in, per language (CONTRACTS §1: hi, en).
_SCRIPT_LETTERS: dict[str, re.Pattern[str]] = {
    "hi": re.compile(r"[ऀ-ॿ]"),  # Devanagari block
    "en": re.compile(r"[A-Za-z]"),
}


class AudioError(Exception):
    """The upload could not be decoded to audio."""


# --------------------------------------------------------------------------------------------------------------------
# Confidence heuristic (pure function)
# --------------------------------------------------------------------------------------------------------------------


def confidence(text: str, duration_sec: float, language: str) -> float:
    """Heuristic confidence for a transcript (the CTC output has no calibrated score we can use).

    - 0.0  if the text is empty (or whitespace only).
    - 0.4  if the speaking rate (words per second = words / duration) is outside 0.5–5 (inclusive range is OK),
           i.e. suspiciously slow (mostly silence / noise) or impossibly fast (hallucinated text);
           a zero or negative duration counts as outside the range.
    - 0.4  if the text contains no letters of the expected script (Devanagari for `hi`, Latin for `en`),
           i.e. the model probably decoded the wrong language.
    - 0.85 otherwise.
    """
    words = text.split()
    if not words:
        return 0.0
    wps = len(words) / duration_sec if duration_sec > 0 else float("inf")
    if not 0.5 <= wps <= 5:
        return 0.4
    script = _SCRIPT_LETTERS.get(language)
    if script is None or not script.search(text):
        return 0.4
    return 0.85


# --------------------------------------------------------------------------------------------------------------------
# Audio conversion
# --------------------------------------------------------------------------------------------------------------------


def to_wav_16k_mono(data: bytes, timeout: float | None = None) -> bytes:
    """Convert any ffmpeg-readable upload (webm/ogg/m4a/mp4/wav) to 16 kHz mono 16-bit PCM WAV bytes."""
    if not data:
        raise AudioError("Empty audio upload")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
           "-ac", "1", "-ar", str(SAMPLE_RATE), "-sample_fmt", "s16", "-f", "wav", "pipe:1"]  # fmt: skip
    try:
        proc = subprocess.run(
            cmd, input=data, capture_output=True, timeout=timeout or settings.ffmpeg_timeout_sec, check=False
        )
    except FileNotFoundError as exc:
        raise AudioError("ffmpeg is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise AudioError("Audio conversion timed out") from exc
    if proc.returncode != 0 or not proc.stdout:
        msg = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise AudioError(f"Could not decode audio: {msg[-1] if msg else 'ffmpeg failed'}")
    return proc.stdout


def wav_to_samples(wav_bytes: bytes) -> tuple[Any, float]:
    """Read 16-bit mono WAV bytes → (float32 torch tensor shaped [1, n] in [-1, 1], duration_sec)."""
    import numpy as np
    import torch

    # ffmpeg writes a streaming header (data size may be 0xFFFFFFFF), so parse frames ourselves when needed.
    with wave.open(io.BytesIO(wav_bytes)) as w:
        rate, width, channels = w.getframerate(), w.getsampwidth(), w.getnchannels()
        frames = w.readframes(w.getnframes())
    if rate != SAMPLE_RATE or width != 2 or channels != 1:
        raise AudioError(f"Unexpected WAV format {rate} Hz / {width * 8} bit / {channels} ch")
    pcm = np.frombuffer(frames[: len(frames) - len(frames) % 2], dtype=np.int16).astype(np.float32) / 32768.0
    return torch.from_numpy(pcm).unsqueeze(0), len(pcm) / SAMPLE_RATE


# --------------------------------------------------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------------------------------------------------


def _load_indic_conformer() -> Any:
    from transformers import AutoModel

    model = AutoModel.from_pretrained(settings.asr_model, trust_remote_code=True)
    if settings.asr_device != "cpu" and hasattr(model, "to"):
        model = model.to(settings.asr_device)
    return model


class AsrEngine:
    """Holds the ASR model. Loading happens once, in a daemon thread, and never raises into the service:
    on failure `error` names the cause and `/asr` keeps answering 503 `model_loading`."""

    def __init__(self, loader: Callable[[], Any] = _load_indic_conformer) -> None:
        self._loader = loader
        self.model: Any = None
        self.error: str | None = None
        self.load_seconds: float | None = None
        self._started = False
        self._infer_lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self.model is not None

    def start_loading(self) -> None:
        if self._started:
            return
        self._started = True
        threading.Thread(target=self._load, name="asr-loader", daemon=True).start()

    def _load(self) -> None:
        t0 = time.monotonic()
        try:
            self.model = self._loader()
            self.load_seconds = time.monotonic() - t0
            log.info("ASR model loaded in %.1f s", self.load_seconds)
        except BaseException as exc:  # noqa: BLE001 — any failure (401 gated, OOM, remote code) must not kill the service
            self.error = f"{type(exc).__name__}: {str(exc).strip().splitlines()[0] if str(exc).strip() else ''}"
            log.error("ASR model failed to load: %s", self.error)

    def status_message(self) -> str:
        if self.error:
            return f"ASR model failed to load ({self.error})"
        return "ASR model is still loading, try again shortly"

    def transcribe(self, wav: Any, language: str) -> str:
        """Run CTC decoding on a [1, n] float32 16 kHz mono tensor."""
        # VERIFY against model card once gated access works: signature `model(wav, lang, "ctc")`,
        # input = torch float tensor [1, n] at 16 kHz mono, output = transcript str.
        with self._infer_lock:
            if settings.asr_device != "cpu" and hasattr(wav, "to"):
                wav = wav.to(settings.asr_device)
            out = self.model(wav, language, "ctc")
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return str(out).strip()


engine = AsrEngine()
