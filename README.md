# MediKiosk

Offline-first AI patient case-taking for Indian hospital OPDs (SIH26047): patients give their history by voice or touch, in Hindi or English, before the consultation.
The doctor opens a structured, trust-labelled summary and verifies it in one tap.

## Run

```bash
docker compose up -d postgres          # database
ollama serve & ollama pull qwen2.5:3b-instruct-q4_K_M
make server    # uvicorn server on 0.0.0.0:8000
make nlp       # nlp service on 0.0.0.0:8001
make relay     # alarm relay on :8003
make his       # mock HIS on :8002
make web       # vite dev server on :5173
python scripts/seed.py
```

Android: set the server URL (Mac's hotspot IP) in the hidden settings screen (long-press the logo 3 s).
