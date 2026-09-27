import pytest

from app import asr
from tests.conftest import HAS_FFMPEG


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg missing")
def test_convert_say_clip_to_16k_mono(say_clip) -> None:
    wav = asr.to_wav_16k_mono(say_clip.read_bytes())
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    samples, duration = asr.wav_to_samples(wav)
    assert samples.shape[0] == 1 and samples.shape[1] > 0
    assert 0.3 < duration < 5
    assert float(samples.abs().max()) <= 1.0


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg missing")
def test_garbage_is_audio_error() -> None:
    with pytest.raises(asr.AudioError):
        asr.to_wav_16k_mono(b"definitely not audio")


def test_empty_is_audio_error() -> None:
    with pytest.raises(asr.AudioError):
        asr.to_wav_16k_mono(b"")
