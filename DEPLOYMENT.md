# YourRA — Production Deployment Guide

This sets up YourRA to handle real, growing traffic. It uses managed services so
nothing is lost on restarts and the app can scale. Written for a non-developer —
follow the steps and I can guide every screen.

---

## Architecture (production)

| Piece | Service | Why |
|---|---|---|
| Web app | Railway (Docker) | Serves the site and API |
| Database + Auth | **Supabase** | Managed Postgres + user accounts, scalable, backed up |
| Audio + file storage | **Cloudflare R2** | Cheap, unlimited object storage |
| Transcription worker | Railway (2nd service) | Does the heavy work off the web app |
| Job queue | **Redis** (Railway/Upstash) | Spreads jobs to the worker, survives deploys |
| AI | Google Gemini Pro | Your existing API key |

The app runs with **`LOCAL_MODE=false`**, so it uses Supabase and R2 instead of
local files. Transcription jobs go onto the Redis queue and are processed by a
separate **worker** service — so the website stays fast no matter how many
uploads are running, and a deploy never loses a job.

> You can launch without Redis (jobs run inside the web app) and add the worker
> later by setting `REDIS_URL` and starting a worker service — no code change.
> But for "lots of users" I recommend setting up the worker from day one.

---

## What you need to provide

1. **Supabase account** (supabase.com) — free tier to start, ~$25/mo "Pro" as you grow.
2. **Cloudflare account** with **R2** enabled (R2 has a generous free tier).
3. **Railway account** (railway.app) — ~$5/mo per service (web + worker = ~$10) plus Redis.
4. Your **Gemini API key** (the working `AIza…` one).
5. Choices: **admin password**, **app secret**, **bKash number**, **WhatsApp number**.
6. (Optional) **SMTP** details to email new users, and a **custom domain**.

I can walk you through each dashboard, but creating accounts and pressing the
final buttons needs your own logins.

---

## Step 1 — Supabase (database + auth)

1. Create a project at supabase.com (region: Singapore is closest to Bangladesh).
2. **SQL Editor → New query** → paste the entire contents of `schema.sql` → **Run**.
   This creates all tables, including the `is_active` and `respondent_meta` columns.
3. **Authentication → Sign In / Providers → Email**:
   - Keep **"Confirm email" ON** for people who sign up themselves (security).
   - (Users you create from the admin panel are auto-confirmed, so they can log
     in immediately.)
4. **Authentication → Sessions / JWT**: set the **JWT expiry** to something long,
   e.g. **604800 (7 days)**, so users aren't logged out every hour.
5. **Project Settings → API**, copy these into Railway later:
   - Project URL → `SUPABASE_URL`
   - `anon public` key → `SUPABASE_ANON_KEY`
   - `service_role` key → `SUPABASE_SERVICE_ROLE_KEY` (secret)

## Step 2 — Cloudflare R2 (storage)

1. Cloudflare dashboard → **R2 → Create bucket** (e.g. `yourra-audio`).
2. **R2 → Manage API Tokens → Create** with **Object Read & Write**.
3. Note: Account ID, Access Key ID, Secret Access Key, bucket name.

## Step 3 — Push code to GitHub

```cmd
cd C:\Users\Rony\Desktop\transcriber
git add .
git commit -m "Production: Supabase + R2 + queue worker"
git push
```
Check `git status` — `.env` must NOT be listed (it's git-ignored).

## Step 4 — Railway: web service

1. railway.app → **New Project → Deploy from GitHub repo** → `transcriber`.
2. Railway builds the `Dockerfile` (installs FFmpeg + dependencies automatically).
3. **Settings → Networking → Generate Domain** to get your public URL.

## Step 5 — Railway: Redis + worker service

1. In the same project: **New → Database → Add Redis**. Copy its connection URL.
2. **New → GitHub Repo → same `transcriber` repo** to create a **second service**.
3. In that second service, **Settings → Deploy → Start Command**: set it to
   ```
   python worker.py
   ```
   (Same image, but it runs the worker instead of the web server.)

## Step 6 — Environment variables (set on BOTH services)

| Variable | Value |
|---|---|
| `LOCAL_MODE` | `false` |
| `COOKIE_SECURE` | `true` |
| `SUPABASE_URL` | from Supabase |
| `SUPABASE_ANON_KEY` | from Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | from Supabase (secret) |
| `R2_ACCOUNT_ID` | from Cloudflare |
| `R2_ACCESS_KEY_ID` | from Cloudflare |
| `R2_SECRET_ACCESS_KEY` | from Cloudflare (secret) |
| `R2_BUCKET_NAME` | your bucket name |
| `REDIS_URL` | from Railway Redis |
| `GOOGLE_API_KEY` | your `AIza…` key |
| `ADMIN_USERNAME` | `admin` (or your choice) |
| `ADMIN_PASSWORD` | a strong password |
| `APP_SECRET_KEY` | a long random string |
| `BKASH_NUMBER` | your bKash number |
| `WHATSAPP_NUMBER` | your WhatsApp number |
| `APP_BASE_URL` | your public URL |
| `MAX_UPLOAD_MB` | `500` |

Optional (email new users automatically):
`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`.

> Tip: in Railway you can set variables once and share them between the web and
> worker services so they always match.

## Step 7 — Go live

1. Both services redeploy after you save variables.
2. Visit your URL, then `/admin` (log in with `ADMIN_USERNAME` / `ADMIN_PASSWORD`).
3. **Admin → Users → Add a user** to onboard people (auto-confirmed + emailed).
4. Upload a real audio file and confirm a transcript comes back with timestamps
   and speaker labels, and the Word report downloads.

---

## Scaling, reliability, cost

- **Scales horizontally:** add more **worker** instances in Railway to process
  more transcriptions at once; add web instances for more visitors. Supabase and
  R2 handle the shared data.
- **Durability:** queued jobs survive deploys/restarts (they're in Redis, run by
  the worker). The web app never blocks on transcription.
- **Gemini limits:** very high concurrency can hit Google's rate limits; your
  paid (Tier 1) account has high limits, and the queue naturally smooths bursts.
- **Memory:** the worker loads each audio file to split it; give the worker
  service ~1–2 GB RAM. Scale up for very long files.
- **Backups:** Supabase provides managed backups (Pro plan). R2 keeps your audio.
- **Rough monthly cost:** Railway web + worker (~$10) + Redis (a few $) +
  Supabase (free → $25) + R2 (cents to a few $) + Gemini usage (~৳185/hour of
  audio). Starts low, grows with usage.

---

## Simpler alternative (if you prefer to start smaller)

You can also deploy the single-server version (LOCAL_MODE=true + a persistent
volume, no Supabase/R2/Redis). It's cheaper and simpler but runs on one machine.
Ask me and I'll give you those exact steps — the code supports both.
