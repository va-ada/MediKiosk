from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import httpx
from fastapi import FastAPI, File, Form, UploadFile
from pydantic import BaseModel

from app import asr, document, extract, summarize
from app.config import settings
from app.errors import ApiError, register_error_handlers


class HealthOut(BaseModel):
    asr_loaded: bool
    ocr_loaded: bool
    ollama: bool


class AsrOut(BaseModel):
    text: str
    confidence: float
    duration_sec: float


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    asr.engine.start_loading()  # background thread; the service is usable (503 on /asr) while it loads
    yield


app = FastAPI(title="MediKiosk NLP", lifespan=lifespan)
register_error_handlers(app)


async def _ollama_up() -> bool:
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            return (await client.get(f"{settings.ollama_url.rstrip('/')}/api/tags")).status_code == 200
    except httpx.HTTPError:
        return False


@app.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    return HealthOut(asr_loaded=asr.engine.loaded, ocr_loaded=document.engine.loaded, ollama=await _ollama_up())


@app.post("/asr", response_model=AsrOut)
def transcribe(audio: Annotated[UploadFile, File()], language: Annotated[Literal["hi", "en"], Form()]) -> AsrOut:
    engine = asr.engine
    if not engine.loaded:
        raise ApiError(503, "model_loading", engine.status_message())
    try:
        wav, duration = asr.wav_to_samples(asr.to_wav_16k_mono(audio.file.read()))
    except asr.AudioError as exc:
        raise ApiError(422, "invalid_audio", str(exc)) from exc
    text = engine.transcribe(wav, language) if duration > 0 else ""
    return AsrOut(text=text, confidence=asr.confidence(text, duration, language), duration_sec=round(duration, 2))


@app.post("/extract", response_model=extract.ExtractOut)
async def extract_slots(body: extract.ExtractIn) -> extract.ExtractOut:
    return await extract.extract(body)


@app.post("/summarize", response_model=summarize.SummarizeOut)
async def summarize_facts(body: summarize.SummarizeIn) -> summarize.SummarizeOut:
    return await summarize.summarize(body)


@app.post("/document", response_model=document.DocumentOut)
def read_document(image: Annotated[UploadFile, File()]) -> document.DocumentOut:
    if not document.engine.ensure_loaded():  # lazy: first call loads RapidOCR (~1 s)
        raise ApiError(503, "model_loading", f"OCR engine failed to load ({document.engine.error})")
    try:
        return document.process(image.file.read())
    except document.ImageError as exc:
        raise ApiError(422, "invalid_image", str(exc)) from exc
