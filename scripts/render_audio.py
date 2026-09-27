"""Render every kiosk audio prompt to content/audio/{hi,en}/<key>.wav with macOS `say` + ffmpeg.

Keys (CONTRACTS.md §9.7): every question id, every triage red-flag slot, and the system phrases below.
Unchanged texts are skipped via content/audio/.hashes.json; files for keys that no longer exist are removed.

Usage:  python3 scripts/render_audio.py            (voices: HI_VOICE=Lekha, EN_VOICE=Rishi by default)
List Indian voices:  say -v '?' | grep -E 'hi_IN|en_IN'
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"
AUDIO = CONTENT / "audio"
HASHES = AUDIO / ".hashes.json"
VOICES = {"hi": os.environ.get("HI_VOICE", "Lekha"), "en": os.environ.get("EN_VOICE", "Rishi")}

# Everyday language; these play on kiosk screens (§9.7 system phrases).
SYSTEM_PHRASES: dict[str, dict[str, str]] = {
    "sys_welcome": {
        "en": "Welcome. Please choose your language.",
        "hi": "नमस्ते। कृपया अपनी भाषा चुनिए।",
    },
    "sys_consent": {
        "en": "We will keep your answers and photos of your old reports so that your doctor at this hospital "
              "can read them before seeing you. You can say no to any part. Your information stays in this hospital.",
        "hi": "आपके जवाब और पुरानी रिपोर्ट की फ़ोटो इस अस्पताल के डॉक्टर के लिए रखी जाएँगी, ताकि वे आपसे मिलने "
              "से पहले उन्हें पढ़ सकें। आप किसी भी हिस्से के लिए मना कर सकते हैं। आपकी जानकारी इसी अस्पताल में रहेगी।",
    },
    "sys_help_coming": {
        "en": "Help is coming. Please stay here.",
        "hi": "मदद आ रही है। कृपया यहीं रहिए।",
    },
    "sys_still_there": {
        "en": "Are you still there? Please touch the screen to continue.",
        "hi": "क्या आप अभी भी यहाँ हैं? आगे बढ़ने के लिए स्क्रीन छुइए।",
    },
    "sys_thanks": {
        "en": "Thank you. Please wait for your token number to be called.",
        "hi": "धन्यवाद। कृपया अपना टोकन नंबर बुलाए जाने तक इंतज़ार कीजिए।",
    },
    "sys_readback_intro": {
        "en": "I will now repeat what you told me. For each one, tap yes, no, or not sure.",
        "hi": "अब मैं आपकी बताई बातें दोहराऊँगी। हर बात पर हाँ, नहीं, या पता नहीं दबाइए।",
    },
    "sys_did_you_mean": {
        "en": "Sorry, I did not understand. Did you mean one of these?",
        "hi": "माफ़ कीजिए, मैं समझ नहीं पाई। क्या आपका मतलब इनमें से कोई है?",
    },
}


def collect() -> dict[str, dict[str, str]]:
    """{key: {"hi": text, "en": text}} for every prompt the kiosk can play."""
    texts: dict[str, dict[str, str]] = {}
    for path in sorted((CONTENT / "questions").glob("*.yaml")):
        for q in (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("questions") or []:
            texts[q["id"]] = {"hi": q["text_hi"], "en": q["text_en"]}
    triage = yaml.safe_load((CONTENT / "triage.yaml").read_text(encoding="utf-8"))
    for q in triage["redflag_questions"]:
        texts[q["slot"]] = {"hi": q["hi"], "en": q["en"]}
    texts.update(SYSTEM_PHRASES)
    return texts


def digest(voice: str, text: str) -> str:
    return hashlib.sha256(f"{voice}\n{text}".encode()).hexdigest()


def render(lang: str, key: str, text: str) -> str:
    out = AUDIO / lang / f"{key}.wav"
    with tempfile.TemporaryDirectory() as tmp:
        aiff = Path(tmp) / "prompt.aiff"
        subprocess.run(["say", "-v", VOICES[lang], "-o", str(aiff), text], check=True, capture_output=True,
                       timeout=60)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(aiff), "-ar", "22050", "-ac", "1",
                        "-sample_fmt", "s16", str(out)], check=True, capture_output=True, timeout=60)
    return f"{lang}/{key}"


def check_tools() -> None:
    for tool in ("say", "ffmpeg"):
        if shutil.which(tool) is None:
            sys.exit(f"{tool} not found — this script needs macOS `say` and ffmpeg (brew install ffmpeg).")
    voices = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, check=True).stdout
    names = {line.split()[0] for line in voices.splitlines() if line.strip()}
    missing = [v for v in VOICES.values() if v not in names]
    if missing:
        sys.exit(f"Voice(s) not installed: {missing}. List Indian voices with: say -v '?' | grep -E 'hi_IN|en_IN' "
                 "and set HI_VOICE / EN_VOICE, or add voices in System Settings → Accessibility → Spoken Content.")


def main() -> int:
    check_tools()
    texts = collect()
    old = json.loads(HASHES.read_text()) if HASHES.exists() else {}
    new: dict[str, str] = {}
    jobs: list[tuple[str, str, str]] = []
    for lang in ("hi", "en"):
        (AUDIO / lang).mkdir(parents=True, exist_ok=True)
        for key, by_lang in texts.items():
            h = digest(VOICES[lang], by_lang[lang])
            new[f"{lang}/{key}"] = h
            if old.get(f"{lang}/{key}") != h or not (AUDIO / lang / f"{key}.wav").exists():
                jobs.append((lang, key, by_lang[lang]))
    with ThreadPoolExecutor(max_workers=6) as pool:
        for done in pool.map(lambda j: render(*j), jobs):
            print(f"  rendered {done}")
    removed = 0
    for lang in ("hi", "en"):
        for wav in (AUDIO / lang).glob("*.wav"):
            if f"{lang}/{wav.stem}" not in new:
                wav.unlink()
                removed += 1
    HASHES.write_text(json.dumps(new, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"{len(jobs)} rendered, {len(new) - len(jobs)} unchanged, {removed} stale removed "
          f"({len(texts)} keys × 2 languages; voices hi={VOICES['hi']}, en={VOICES['en']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
