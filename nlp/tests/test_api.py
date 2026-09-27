import httpx
import pytest
import respx

from app import asr
from tests.conftest import HAS_FFMPEG, make_engine


def test_health_shape(client) -> None:
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url__regex=r".*/api/tags").mock(return_value=httpx.Response(200, json={"models": []}))
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"asr_loaded": False, "ocr_loaded": False, "ollama": True}


def test_health_ollama_down(client) -> None:
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url__regex=r".*/api/tags").mock(side_effect=httpx.ConnectError("down"))
        body = client.get("/health").json()
    assert body["ollama"] is False and all(isinstance(v, bool) for v in body.values())


def test_asr_503_while_loading(client) -> None:
    r = client.post("/asr", files={"audio": ("a.wav", b"x", "audio/wav")}, data={"language": "hi"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "model_loading"


def test_asr_503_names_load_failure(client, monkeypatch: pytest.MonkeyPatch) -> None:
    def gated() -> None:
        raise OSError("401 Client Error: gated repo ai4bharat/indic-conformer-600m-multilingual")

    make_engine(monkeypatch, gated)
    assert client.get("/health").json()["asr_loaded"] is False
    r = client.post("/asr", files={"audio": ("a.wav", b"x", "audio/wav")}, data={"language": "hi"})
    assert r.status_code == 503
    err = r.json()["error"]
    assert err["code"] == "model_loading" and "failed to load" in err["message"] and "401" in err["message"]


def test_asr_bad_language(client) -> None:
    r = client.post("/asr", files={"audio": ("a.wav", b"x", "audio/wav")}, data={"language": "ta"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg missing")
def test_asr_with_fake_model(client, monkeypatch: pytest.MonkeyPatch, say_clip) -> None:
    calls: list[tuple] = []

    def fake_model(wav, lang, mode):
        calls.append((tuple(wav.shape), lang, mode))
        return "मेरे घुटने में दर्द है"

    make_engine(monkeypatch, lambda: fake_model)
    r = client.post("/asr", files={"audio": ("k.m4a", say_clip.read_bytes(), "audio/mp4")}, data={"language": "hi"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["text"] == "मेरे घुटने में दर्द है" and body["duration_sec"] > 0
    assert body["confidence"] == asr.confidence(body["text"], body["duration_sec"], "hi")
    assert calls[0][0][0] == 1 and calls[0][1:] == ("hi", "ctc")


def test_asr_english_is_unsupported(client, monkeypatch: pytest.MonkeyPatch, say_clip) -> None:
    """IndicConformer has no English: 422 unsupported_language, and the model is never called."""
    calls: list[str] = []
    make_engine(monkeypatch, lambda: lambda *a: calls.append("called") or "x")
    r = client.post("/asr", files={"audio": ("k.m4a", say_clip.read_bytes(), "audio/mp4")}, data={"language": "en"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unsupported_language" and calls == []


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg missing")
def test_asr_invalid_audio(client, monkeypatch: pytest.MonkeyPatch) -> None:
    make_engine(monkeypatch, lambda: lambda *a: "x")
    r = client.post("/asr", files={"audio": ("a.wav", b"garbage", "audio/wav")}, data={"language": "hi"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_audio"


def test_engine_load_failure_never_raises() -> None:
    engine = asr.AsrEngine(loader=lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    engine._load()
    assert not engine.loaded and engine.error == "RuntimeError: boom"
