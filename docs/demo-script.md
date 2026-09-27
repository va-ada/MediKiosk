# MediKiosk — 6-minute live demo

> **Status:** web, server and NLP parts are built and verified. The Android kiosk / patient app (tasks A1–A15) is
> **not built yet** — every kiosk beat below has a **Fallback** that works today (assisted desk page or a one-line
> API call). Re-read this script once the Android app exists and delete the fallbacks you no longer need.

## Cast

| Role | Who | Device |
|---|---|---|
| Narrator | talks to the judges, drives the timing | — |
| "Patient" (Kamla Devi, 62) | speaks Hindi to the kiosk | Android phone #1 — kiosk (`KIOSK`) |
| Kiosk operator / second patient | presses the emergency button | Android phone #2 / Z Fold (`PATIENT_APP` or `HALL`) |
| Doctor (Dr. Mehta, Ayurveda, Room 1) | verifies and closes the visit | Mac browser tab `/doctor` |
| Nurse screen | shown on a second monitor or tab | Mac browser tab `/triage` |
| Display board | projector / TV | Mac browser tab `/display` (Ayurveda) |
| Admin | flips island mode, shows the HIS | Mac browser tabs `/admin` and `http://localhost:8002/` |

## Setup (do this 30 minutes before)

1. **Hotspot on** on the Mac (this is the "hospital LAN"). Note the Mac's IP (`ipconfig getifaddr en0` or the hotspot bridge IP).
2. Start everything from the repo root, each in its own terminal:
   ```bash
   docker compose up -d postgres
   ollama serve            # if not already running; model qwen2.5:3b-instruct-q4_K_M must be pulled
   make server             # :8000
   make nlp                # :8001 (first start loads OCR/ASR; wait for /health)
   make his                # :8002 — mock hospital system
   make relay              # :8003 — alarm relay
   make web                # :5173
   make demo-reset         # DESTRUCTIVE: fresh DB with Kamla A-001, Rahul A-002, Sita A-003 (recheck)
   ```
3. Check: `cd server && uv run python ../scripts/smoke.py` → `RESULT: PASS` (then run `make demo-reset` again so the boards are clean).
4. Browser tabs (Chrome, sound allowed):
   - `http://localhost:5173/login` → **D1 / 1111** → `/doctor`
   - second window `…/login` → **N1 / 3333** → `/triage` (click once so the page may beep)
   - `…/display` → pick **Ayurveda** → click **Enable sound**
   - `…/login` → **A1 / 5555** → `/admin` (island mode must be **OFF**)
   - `http://localhost:8002/` (mock HIS inbox)
5. Phones: long-press the MediKiosk logo 3 s → server `http://<MAC_IP>:8000`, relay `http://<MAC_IP>:8003`, device ids
   `KIOSK-01` / `APP-FOLD`, **Test connection** is green. Kiosk phone: screen pinning ON, volume up, handset mode OFF.
6. Charge both phones; keep a backup video of the whole demo on the Mac desktop.

## The demo (6 minutes)

| Time | Beat | Who does what | Say |
|---|---|---|---|
| 0:00 | **Problem** | Narrator | "An Ayurveda OPD doctor gets 2–5 minutes per patient. No time for history, and old reports go unread." |
| 0:30 | **Hindi intake on the kiosk** | Patient taps **हिंदी**, "मेरे पास ABHA है", ABHA `12345678901234`, OTP `123456`, "Myself", consent (answers the check question), complaint **जोड़ों का दर्द**, body map **knee**, 5 red-flag questions all ✗ → **token A-004** appears. Display board shows A-004 in "Next". | "Kamla Devi identifies with ABHA, hears the consent in Hindi, and gets a token in under two minutes." |
| | *Fallback (no Android yet)* | Desk tab: log in **K1 / 4444** → `/desk`, register Kamla-style walk-in, complaint Joint pain, all red flags No → big token + QR | "At a busy counter, staff can do the same in under a minute." |
| 1:30 | **History by voice** | Patient holds the mic: "तीन महीने से घुटने में दर्द है" → next question; taps the rest; photographs the CBC printout (`content/samples/lab_report_cbc.png` printed) → read-back → Yes/No → Done; screen wipes to Start. | "Every question is voice **or** tap. The AI only understands answers — questions come from clinician-reviewed files." |
| | *Fallback* | Use demo patient **Kamla A-001** (already has full history + CBC from `make demo-reset`). | |
| 2:30 | **Red-flag emergency** | Second phone: tap the red **Emergency** button → "Chest pain" → phone flashes and beeps. `/triage` beeps within 2 s; nurse clicks **On my way**, then **Confirm emergency**. | "Red flags are rules, not a model. The alarm goes to the server *and* straight to a separate relay." |
| | *Fallback* | `curl -X POST localhost:8000/api/alerts/emergency -H 'X-Kiosk-Id: KIOSK-02' -H 'content-type: application/json' -d '{"id":"'$(uuidgen)'","kiosk_id":"KIOSK-02","reason_code":"chest_pain"}'` | |
| 3:00 | **Doctor verifies** | `/doctor`: Sita's **priority recheck** sits on top (reserved for Dr. Mehta). Click **In** on Kamla → patient view: red **allergy banner (Penicillin — rash)**, critical strip with **Haemoglobin 10.2 LOW**, AI-drafted HPI labelled "verify". Open **HPI** → **Approve** (chips turn green). Click **View source** on Haemoglobin → the report opens with the value highlighted. AYUSH tab → Nadi *vata*, Pramana 158 cm / 64 kg (BMI appears) → Save. Diagnosis: search "sandhi" → **Sandhigata Vata** (SAMPLE code) → Save. | "Every fact is labelled: patient said, from report, doctor verified. Allergies are always shown. The doctor verifies in one tap per section." |
| 4:15 | **Close the visit** | Outcome bar → **Out** → confirm. `/admin` outbox shows the bundle **sent**; `localhost:8002` lists a FHIR bundle for Kamla Devi. | "The visit becomes a FHIR record and leaves only through the outbox, after re-checking consent." |
| 4:45 | **Unplug the internet — island mode** | `/admin` → **Island mode ON** → confirm. Register another patient (desk or kiosk) and close the visit: the outbox row stays **pending**; everything else keeps working. | "If the hospital loses its uplink, nothing inside stops, and nothing leaves." |
| 5:15 | **Stop the API server** | In the `make server` terminal press **Ctrl-C**. Second phone: Emergency → Seizure. `/triage` still shows the alarm with the badge **"via relay — server not confirmed"** and beeps. | "Even with the main server down, the emergency path works." |
| | *Fallback* | `curl -X POST localhost:8003/alarm -H 'content-type: application/json' -d '{"id":"'$(uuidgen)'","kiosk_id":"KIOSK-02","reason_code":"seizure","created_at":"2026-10-12T05:00:00Z"}'` | |
| 5:40 | **Restart → outbox drains** | `make server` again; `/admin` → **Island mode OFF** → within ~5 s the pending bundle turns **sent** and appears at `localhost:8002`. **Verify chain** → ✓ valid. | "Every action is in a hash-chained audit log — tamper with one row and verification points at it." |

## Recovery plan

| Problem | Do this |
|---|---|
| Voice not understood | Tap the answer — every question has tap choices; "Did you mean…?" appears automatically. |
| NLP down (`/admin` tile red) | Keep going: tap answers; the HPI shows "Patient answers joined (no AI narrative)". |
| Phone can't reach server | Check hotspot + IP in the hidden settings; otherwise switch to the `/desk` fallback. |
| A board looks wrong | `make demo-reset` (≈5 s) and restart from the doctor beat with Kamla A-001. |
| Anything worse | Play the backup video; keep narrating. |

## Pre-demo checklist

- [ ] Hotspot on; Mac IP written down; both phones on the hotspot with IPs set and **Test connection** green
- [ ] `make server nlp his relay web` all running; `/admin` tiles all green (relay + HIS included)
- [ ] `make demo-reset` run **after** the smoke test
- [ ] Island mode **OFF**
- [ ] Browser sound allowed on `/triage` and `/display` (clicked once / "Enable sound")
- [ ] Phones charged, volume up, screen pinning ON on the kiosk
- [ ] Printed `lab_report_cbc.png` on the table for the camera beat
- [ ] Backup video on the desktop
- [ ] Say it clearly: content marked **DRAFT — clinician review required**; codes are **SAMPLE** placeholders; ABHA/OTP are mocked
