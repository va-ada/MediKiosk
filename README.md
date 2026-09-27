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

### Android kiosk: screen pinning
In device mode `KIOSK` the app pins itself (`startLockTask`) so patients cannot leave it.
On a normal (non device-owner) phone first enable **Settings → Security → App pinning** (a.k.a. *Screen pinning*);
the app then asks "App is pinned" on start — tap **Got it**. Staff unpin by holding **Back + Overview**
(gesture navigation: swipe up and hold). Switching the device mode to `HALL` or `PATIENT_APP` in the hidden
settings (long-press the logo 3 s) unpins automatically.
