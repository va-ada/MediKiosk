import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import asr
from app.main import app

HAS_FFMPEG = shutil.which("ffmpeg") is not None
HAS_SAY = shutil.which("say") is not None


def make_engine(monkeypatch: pytest.MonkeyPatch, loader) -> asr.AsrEngine:
    """Swap in an engine with a fake loader (never downloads the real model) and load it synchronously."""
    engine = asr.AsrEngine(loader=loader)
    engine._started = True
    engine._load()
    monkeypatch.setattr(asr, "engine", engine)
    return engine


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    """TestClient whose startup does NOT start loading the real model (engine starts unloaded)."""
    engine = asr.AsrEngine(loader=lambda: None)
    engine._started = True
    monkeypatch.setattr(asr, "engine", engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def say_clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not (HAS_FFMPEG and HAS_SAY):
        pytest.skip("needs macOS `say` and ffmpeg")
    d = tmp_path_factory.mktemp("audio")
    aiff, m4a = d / "clip.aiff", d / "clip.m4a"
    subprocess.run(["say", "-o", str(aiff), "my knee hurts"], check=True, timeout=30)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(aiff), str(m4a)], check=True, timeout=30)
    return m4a
