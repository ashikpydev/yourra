# YourRA — Project Handoff & Continuity Document

_Last updated: 16 June 2026. Keep this file in the repo root. Drop it into any new chat (with the project folder connected) and the assistant can continue exactly where we left off._

---

## 1. What YourRA is

YourRA is a production Bangla qualitative-research transcription service (SaaS). A researcher uploads an interview recording (IDI, FGD, KII, or case study) and gets back:

- A faithful **Bangla verbatim** transcript with speaker labels (Moderator vs Respondents) and timestamps roughly every 2 minutes.
- A natural **English translation** aligned to the same structure.
- A ready-to-hand-over **Word (.docx) report** that opens with a respondent demographic table, with the YourRA logo in the page header and an AI-accuracy declaration in the footer.
- Plain-text exports (Bangla, English, combined).

The core promise is quality first: clear audio yields highly accurate output (declared as up to ~90–95% on clean recordings, not guaranteed, human review recommended).

**Live site:** https://web-production-d958a.up.railway.app
**GitHub repo:** the `yourra` repository (the original prototype lives in a separate `transcriber` repo and must not be overwritten).
**Working folder on this machine:** `C:\Users\Rony\Desktop\transcriber`

---

## 2. How it works (pipeline)

1. User uploads audio (MP3, WAV, M4A, OGG, MP4, up to 500 MB) and optionally fills survey + respondent demographics.
2. The file is stored (Cloudflare R2 in production, local disk in local mode).
3. The audio is split into **~10-minute chunks on silence boundaries** (pydub + ffmpeg).
4. Each chunk is transcribed **fully and sequentially** by **Gemini 2.5 Pro**, carrying a small continuity context between chunks. Chunks are **merged back losslessly** (no boundary re-stitching that could drop words). Absolute timestamps are reconstructed using per-chunk offsets.
5. Speaker roles (Moderator/Respondent) are detected; demographics spoken in the audio are extracted (this small extraction uses the cheaper Gemini 2.5 Flash).
6. The transcript text is saved to the database; the audio original is deleted from storage after a successful save.
7. The Word report and text files are generated on download.

**Credit rule (strict):** only the user's available minutes are transcribed. A longer file is trimmed to exactly the remaining credit (e.g., 20-minute file with 14 credits → exactly the first 14 minutes). This is enforced in chunking (`max_seconds`).

**Why chunk-and-merge:** this approach was chosen deliberately for accuracy and must never be removed. Sending multi-hour audio in one call drops content in the middle/end; the 10-minute chunk → full transcribe → lossless merge pattern fixed that.

---

## 3. Tech stack

- **Backend:** FastAPI (Python 3.12) + Jinja2 templates.
- **Frontend:** server-rendered HTML, Alpine.js (CDN) for interactivity, Tailwind (CDN) plus a custom design system in `backend/static/css/style.css`.
- **AI:** Google Gemini 2.5 Pro (transcription) and 2.5 Flash (demographics extraction) via `google-generativeai`.
- **Audio:** pydub + ffmpeg (ffmpeg installed in the Docker image).
- **Database / Auth:** Supabase (Postgres + Auth) in production.
- **Storage:** Cloudflare R2 (S3-compatible, via boto3) in production.
- **Docs:** python-docx for the Word report.
- **Queue (optional, for scale):** Redis + RQ worker (`worker.py`). Currently NOT enabled — jobs run in-process via FastAPI BackgroundTasks (see §8).
- **Deploy:** Docker on Railway (Dockerfile build), with `Procfile`, `railway.json`, and `run.py` (reads `$PORT`).

### Local mode (no external accounts)
Set `LOCAL_MODE=true` (the default) and the app runs entirely offline: a SQLite-backed shim (`backend/local_db.py`) mimics the Supabase client API, storage uses local disk, and Gemini falls back to a mock if no API key is set. This is how you develop/test without Supabase/R2.

---

## 4. Repository map

```
transcriber/                  (repo root)
├── backend/
│   ├── main.py               app + routes (landing, pricing, dashboard, trial, etc.)
│   ├── config.py             Settings (env vars; defaults)
│   ├── database.py           switches Supabase client vs LocalDB by LOCAL_MODE
│   ├── local_db.py           SQLite shim (Supabase-compatible) + local auth
│   ├── auth.py               auth helpers / current-user
│   ├── routers/
│   │   ├── auth_router.py     signup (name/org), login (JSON + cookie), logout
│   │   ├── transcription.py   bundles, custom top-up, upload, always-Pro engine
│   │   └── admin.py           users (add/pause/delete), payments, jobs, trials
│   ├── services/
│   │   ├── gemini.py          chunk transcription (Pro) + demographics (Flash)
│   │   ├── chunking.py        silence-aware 10-min chunking + credit cap
│   │   ├── pipeline.py        run_transcription_job / run_job_sync
│   │   ├── jobs.py            enqueue (Redis) or False → in-process fallback
│   │   ├── storage.py         local disk vs R2; deletes audio after save
│   │   └── docgen.py          Word report (logo header + accuracy footer)
│   ├── templates/            base, landing, pricing, dashboard, result,
│   │   │                      login, signup, trial, admin/*
│   └── static/
│       ├── css/style.css     design system (brand tokens, components)
│       └── img/              favicon.svg (logo), logo.png (report header)
├── run.py                    uvicorn entrypoint (reads $PORT in Python)
├── worker.py                 RQ worker (needs REDIS_URL; not currently run)
├── schema.sql                full idempotent Supabase schema
├── Dockerfile                python:3.12-slim + ffmpeg
├── Procfile                  web: python run.py / worker: python worker.py
├── railway.json              healthcheck /health
├── requirements.txt
├── .env.example              all env vars documented
├── README.md
├── DEPLOYMENT.md             production deploy guide
├── SETUP_AND_TESTING.md      local setup + test users
├── PROJECT_HANDOFF.md        ← this file
└── GO_LIVE_yourra_org_AND_COSTS.md   custom domain + scaling + costs
```

---

## 5. Pricing model (current)

- **Per-hour rate:** ৳399 per hour of audio. Always Gemini 2.5 Pro (quality first; never Flash for the transcript).
- **Bundles:** Mini 60 min / ৳399, Standard 180 min / ৳1199, Value 360 min / ৳2399, Pro Bundle 900 min / ৳5999. Credits never expire.
- **Custom hours:** buy any number of hours at ৳399/hour.
- **Savings story:** a human RA needs ~1 working day per hour of audio at ~৳700/hour; the pricing page has a transparent, step-by-step calculator showing the math (RA cost vs YourRA cost vs savings) that updates live.
- **Payment:** manual bKash "Send Money" to the business number, then the user submits the bKash Transaction ID from the dashboard; an admin reviews and grants credits.

**Cost reference (API):** Gemini cost is variable; the owner's observed cost has been roughly ৳150–200 per hour of audio, comfortably under the ৳399 price. Batch mode (half price) is a future optimization.

---

## 6. Decisions log (things to NOT undo)

- **Chunk → full transcribe → lossless merge.** Never replace with single-call transcription. This is the accuracy backbone.
- **Always Gemini 2.5 Pro for transcripts.** Flash only for the tiny demographics extraction.
- **Price is ৳399/hour** (settled after 499 → 300 → 399). Keep custom-hours option.
- **No automatic free trial.** Instead there is a "Request a trial" form; admins grant credits from the panel. (A leftover `TRIAL_MINUTES=5` still exists in config — see backlog.)
- **RA Services idea is hidden, not deleted** (conflict-of-interest with the owner's organization). Code kept for later.
- **Timestamps every ~2 minutes** and **Moderator/Respondent labels** in every transcript.
- **Deliverable is a ready-to-go Word report** starting with a demographic table.
- **Logo** is the abstract "converging voices" mark (two lines merging into one — multiple speakers becoming one transcript). It also reads as a "Y". Files: `backend/static/img/favicon.svg` and `logo.png`. Run a reverse-image / trademark check before formal registration.
- **Prototype must be preserved.** New code lives in the `yourra` repo; the `transcriber` GitHub repo holds the original prototype and must not be force-overwritten.

---

## 7. Environment variables (production, set in Railway — no quotes around values)

```
LOCAL_MODE=false
APP_BASE_URL=https://yourra.org          (after domain migration; else the railway URL)
APP_SECRET_KEY=<openssl rand -hex 32>
COOKIE_SECURE=true                        ← must be true in production
ADMIN_USERNAME=<your admin user>
ADMIN_PASSWORD=<strong password>
SUPABASE_URL=...
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...             ← server-side only, never in templates
GEMINI_API_KEY=<an AIza... key>
GEMINI_MODEL_PRO=gemini-2.5-pro
GEMINI_MODEL_FLASH=gemini-2.5-flash
R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BUCKET / R2_PUBLIC_URL
R2_RETENTION_DAYS=7
SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / SMTP_FROM   (for emails)
BKASH_NUMBER=01575522637
WHATSAPP_NUMBER=01772215084
REDIS_URL=                                (blank = in-process jobs; set when worker is enabled)
```

Two operational rules learned the hard way: **do not wrap values in quotes** in Railway, and the **web service must have every var set** (a missing var silently dropped the app into LOCAL_MODE and jobs got stuck "pending"). The start command must be `python run.py` (it reads `$PORT` in Python; passing `$PORT` to uvicorn's `--port` flag fails).

---

## 8. Current status

Working in production: signup/login, dashboard, upload, the full transcription pipeline (verified end-to-end: real transcript with Moderator/Respondent labels, 2-minute timestamps, accurate Bangla + English), credit enforcement, the Word report (now with logo header + accuracy footer), admin user management, bKash top-up submission + admin approval, the trial request form.

Recently added: professional UI polish (floating WhatsApp button, bKash copy buttons, fade-ins), the logo everywhere (favicon, nav, footer, admin, Word report), the AI-accuracy declaration (upload area, result page, report footer), and the transparent step-by-step savings calculator.

**Jobs currently run in-process** (FastAPI BackgroundTasks), because the Redis worker was removed on Railway. This works for moderate load but a redeploy or crash kills in-progress jobs (see backlog INFRA/Bug-3).

---

## 9. How to run & deploy

**Local:**
```
cd C:\Users\Rony\Desktop\transcriber
python -m venv venv && venv\Scripts\python -m pip install -r requirements.txt
venv\Scripts\python -m uvicorn backend.main:app --reload
```
LOCAL_MODE is on by default; no Supabase/R2 needed. Admin login uses ADMIN_USERNAME/ADMIN_PASSWORD.

**Deploy:** push to the `yourra` repo's main branch; Railway auto-builds from the Dockerfile and redeploys. Run `schema.sql` in the Supabase SQL editor when the schema changes (it is idempotent — safe to re-run).

---

## 10. Hardening & roadmap backlog

This merges an external audit with the actual current code. Items are corrected where the audit referenced an older snapshot (e.g., we already always use Pro and removed the auto free trial). Verify each against the code before acting.

### Fix before onboarding many users
1. **Confirm `COOKIE_SECURE=true`** is set in Railway (default in code is false).
2. **Confirm `APP_SECRET_KEY` and `ADMIN_PASSWORD` are strong** (not placeholders). Rotate the secret key if a placeholder was ever deployed.
3. **Job durability.** Add a reaper that marks jobs stuck in `processing` for >30 min as `failed` (with a friendly message) and does not deduct/▸refunds credits. Longer term, re-enable Redis + the `worker` service so jobs survive deploys.
4. **bKash duplicate protection.** Add `unique (bkash_trx_id)` on `pending_payments` and reject a Transaction ID that already exists (any status) with a 409.
5. **RLS review.** `transcription_jobs` has INSERT but verify only the service-role client updates job rows. Enable RLS on `trial_ips` / `trial_requests` (service-role only) — `trial_ips` holds IP addresses.
6. **Trial-by-IP false positives.** Institutions (BRAC, icddr,b, dRi) share one IP via CGNAT. Don't block trials by IP; gate on verified email instead. (Also resolve the leftover `TRIAL_MINUTES=5` vs request-form duplication — pick one model.)

### Security
- Rate-limit `/admin` (e.g., slowapi) and write the approving admin into `credit_transactions`.
- Ensure `SUPABASE_SERVICE_ROLE_KEY` never reaches a template or client response (`grep -ri service_role backend/templates/` should be empty).
- Verify R2 bucket is not publicly listable; keys are UUID-based.
- Raise Supabase password minimum to 8–10; add a confirm-password field; enable email confirmation.
- Add `/privacy` and `/terms` pages (you handle audio of potentially vulnerable research participants) and link them from signup + footer.
- Consider a dedicated business number instead of the personal bKash/WhatsApp numbers as volume grows.

### Reliability / infra
- Implement (or confirm) R2 cleanup; currently audio is deleted after a successful save, with `R2_RETENTION_DAYS=7` as the intended backstop — verify a sweep exists for failed/orphaned files.
- Pin-test `google-generativeai` against the `gemini-2.5-*` model names; upgrade if the pinned version is too old.
- For large uploads, prefer presigned R2 direct upload to avoid the platform request-body limit and reduce web memory pressure.

### High-leverage features (roughly in priority order)
1. **Downloadable sample report** on the homepage (one anonymized .docx). Biggest conversion win, no backend work.
2. **Privacy Policy + Terms** pages (also needed for institutional buyers).
3. **Email on job complete/fail** (SMTP already configured).
4. **Forgot-password** link (Supabase `resetPasswordForEmail`).
5. **`.srt` / `.vtt` subtitle export** (timestamps already exist).
6. **CSV/JSON export** for NVivo / ATLAS.ti / MAXQDA (`timestamp, speaker, bangla, english`).
7. **Custom glossary upload** (prepend terms to the Gemini prompt) for acronyms/place names.
8. **Admin notification** on new payment submission.
9. **Low-confidence highlighting** (count `[inaudible]`/`[unclear]` per job).
10. **Dialect hint dropdown** (Dhaka/Chittagonian/Sylheti) passed as a prompt note.
11. Confirm dashboard shows full job history with working re-download for old completed jobs.
12. Fix small copy issues: "1 hour" (not "1 hours"), name the unnamed "Most popular" bundle, ensure the calculator shows prefilled defaults on load, give each page a unique meta description, soften the "our team will set you up" CTA to "start transcribing today."

---

## 11. Quick reference

- **Owner:** Rony (rashikur504@gmail.com).
- **bKash:** 01575522637. **WhatsApp:** 01772215084 (links use `wa.me/8801772215084`).
- **Admin panel:** `/admin` (HTTP Basic with ADMIN_USERNAME/PASSWORD).
- **Health check:** `/health`.
- **Recurring dev note:** the Linux sandbox sometimes shows truncated copies of just-edited files — that is a mount artifact, not a real corruption; the files on disk are correct.
