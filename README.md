# YourRA — Research Assistance Platform

YourRA is a production webapp that started as an automated Bangla IDI/FGD/case-study
transcription tool and has been extended into a full research-assistance services platform:
automated transcription (Bangla verbatim + English translation), plus quote-based RA services
(SurveyCTO setup, data processing, data analysis, manuscript writing).

## Stack

- **Backend**: FastAPI (async Python)
- **Frontend**: Jinja2 templates + Tailwind (CDN) + Alpine.js (CDN) — single deployment, no separate frontend build
- **Database / Auth**: Supabase (Postgres + Auth, Row Level Security)
- **Storage**: Cloudflare R2 (S3-compatible, via boto3)
- **Transcription**: Google Gemini (2.5 Flash for trial users, 2.5 Pro for paid users)
- **Audio processing**: pydub + FFmpeg, silence-based chunking + parallel transcription + boundary stitching
- **Background jobs**: FastAPI BackgroundTasks (no Celery/Redis needed at this scale)
- **Payments**: Manual bKash — user submits a Transaction ID, admin approves in `/admin`

## How transcription works

1. User uploads audio (mp3/wav/m4a/ogg/mp4, up to `MAX_UPLOAD_MB`).
2. File is uploaded to Cloudflare R2 and a `transcription_jobs` row is created (`status=pending`).
3. A background task downloads the file, splits it into ~8-minute chunks on silence
   (`backend/services/chunking.py`), and transcribes every chunk **in parallel** via Gemini
   (`backend/services/gemini.py`).
4. Adjacent chunk boundaries are stitched together with a follow-up Gemini call so sentences
   split across chunks read naturally.
5. The job is marked `completed`, credits are deducted based on actual audio duration
   (rounded up to the nearest minute), and the user can download Bangla / English / combined
   transcripts as `.txt` files.

Progress is exposed via `GET /api/status/{job_id}` and polled from the dashboard/result pages.

## Credits & free trial

- Each user has a `credits_minutes` balance (`user_profiles.credits_minutes`).
- New users get `TRIAL_MINUTES` (default 5) free minutes on first login, limited to one trial
  per email **and** per IP address (`trial_ips` table). Disposable email domains are blocked
  via the mailcheck.p.ninja API (fails open if that service is down).
- Trial users transcribe with Gemini Flash; paid users get Gemini Pro.
- Credits are deducted only after a job completes successfully.

## Payments (manual bKash, Phase 1)

1. User picks a bundle on the dashboard and sends the listed amount via bKash to `BKASH_NUMBER`.
2. User submits the bKash Transaction ID via `POST /api/topup` → creates a row in
   `pending_payments` (`status=pending`).
3. Admin reviews pending payments at `/admin/payments` and clicks **Approve** — this credits
   the user's `credits_minutes`, logs a `credit_transactions` row, and marks the payment
   `approved` (or **Reject** with a note).
4. `/admin` also has a manual "Activate Credits" form for one-off/institutional arrangements.

This is intentionally manual because automated payment gateways (e.g. SSLCommerz) require a
trade license and business bank account. Once that paperwork exists, Phase 2 can add automated
checkout without changing the credit/job model.

## RA services (quote-based)

`/services` lets visitors submit a request (SurveyCTO setup, data processing, analysis,
manuscript writing) with an optional file attachment. Requests land in `service_requests` and
are managed from `/admin/requests`, where the admin can update status and quoted price.

## Setup

### Prerequisites
- Python 3.11+
- A Supabase project (Postgres + Auth)
- A Cloudflare R2 bucket
- A Google Gemini API key
- FFmpeg available on the host (Railway's nixpacks installs this automatically; for local dev,
  install it via your OS package manager)

### Steps

1. **Clone and install**
   ```bash
   git clone https://github.com/ashikpydev/transcriber.git
   cd transcriber
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Set up the database**
   - Create a Supabase project.
   - Open the SQL editor and run the entire contents of `schema.sql`.

3. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   Fill in:
   - `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
   - `GOOGLE_API_KEY` (Gemini)
   - `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_PUBLIC_URL`
   - `ADMIN_USERNAME`, `ADMIN_PASSWORD` (HTTP Basic Auth for `/admin/*`)
   - `BKASH_NUMBER`, `WHATSAPP_NUMBER` (shown to users on the pricing/dashboard pages)
   - Optionally tune `TRIAL_MINUTES`, `CHUNK_TARGET_SECONDS`, `CHUNK_HARD_MAX_SECONDS`,
     `SILENCE_THRESH_DBFS`, `MIN_SILENCE_LEN_MS`, `MAX_UPLOAD_MB`

4. **Run locally**
   ```bash
   uvicorn backend.main:app --reload
   ```
   Visit `http://127.0.0.1:8000`.

5. **Admin panel**
   Visit `/admin` and log in with `ADMIN_USERNAME` / `ADMIN_PASSWORD` (HTTP Basic Auth).

## Deployment (Railway)

This repo includes a `Procfile`:
```
web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```
Railway's nixpacks builder auto-installs FFmpeg, so audio chunking works out of the box. Set all
env vars from `.env.example` in the Railway project settings.

## Project structure

```
backend/
  main.py              # FastAPI app, page routes
  config.py            # env-based settings
  database.py          # Supabase clients
  auth.py              # JWT auth + admin basic auth
  routers/
    auth_router.py      # signup / login / logout
    profile.py           # /api/profile, /api/jobs
    transcription.py     # /api/upload, /api/status, /api/result, /api/download, /api/topup
    admin.py              # /admin/* (HTTP Basic Auth)
  services/
    storage.py            # Cloudflare R2 helpers
    chunking.py           # silence-based audio chunking
    gemini.py             # Gemini transcription + boundary stitching
    pipeline.py           # job orchestrator (chunk -> transcribe -> stitch -> credit)
    trial.py              # free trial + disposable email checks
  templates/             # Jinja2 templates (landing, auth, dashboard, result, pricing, services, admin/*)
schema.sql              # Supabase schema + RLS policies
requirements.txt
Procfile
.env.example
```

## Roadmap (Phase 2+)

- Automated payments (SSLCommerz) once trade license / business bank account are available
- Per-bundle "plan" field for stricter Flash/Pro model assignment (currently heuristic)
- Scheduled cleanup of R2 originals after `R2_RETENTION_DAYS`
- Self-serve scoping/pricing for SurveyCTO, data processing, analysis, and manuscript services

## Limitations

- AI transcripts are a strong first draft, not perfect — accuracy depends on audio quality.
- Optimized for Bangla audio; other languages are untested.
