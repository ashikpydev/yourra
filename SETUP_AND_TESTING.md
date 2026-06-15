# YourRA — Setup & Testing Guide

This is your step-by-step manual for running YourRA on your own computer, testing it
end-to-end (as a normal user **and** as the admin), and deploying it online. It is written
for someone who does not write code, so every command can be copy-pasted.

> **Two roles to understand**
> - **User**: signs up, gets a free trial, uploads audio, downloads transcripts, tops up credits.
> - **Admin (you)**: logs in at `/admin` to approve payments, grant credits, and see all jobs/users.

---

## ⭐ Local mode — everything works with NO accounts

The project ships with **`LOCAL_MODE=true`** already set in your `.env`. In this mode the whole
app runs entirely on your computer:

- **Accounts + database** → a local SQLite file (`yourra_local.db`) instead of Supabase
- **Audio storage** → a local folder (`local_storage/`) instead of Cloudflare R2
- **Transcription** → **mock sample text** if you haven't added a Gemini key yet

So you can sign up, log in, get the free trial, upload audio, watch it process, download a
(sample) transcript, and use the full admin panel — **without creating a single online account.**
Just install and run:

```cmd
cd C:\Users\Rony\Desktop\transcriber
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python -m uvicorn backend.main:app --reload
```

Then open http://127.0.0.1:8000 and go through the full test in **section 6**.

**Two optional upgrades (still in local mode):**
- **Real transcription instead of mock text** → put a real Gemini key in `.env`
  (`GOOGLE_API_KEY=AIza...`, see section 3). Mock is used automatically whenever the key
  doesn't start with `AIza`.
- **Going live for real users** → set `LOCAL_MODE=false` and fill in Supabase + R2
  (sections 2 & 4). Do this only when you deploy (section 7).

> Sections 0, 2, and 4 below are **only needed for production** (`LOCAL_MODE=false`). For local
> testing you can skip straight to section 6.

---

## 0. What you need for PRODUCTION (one-time accounts)

*(Skip this for local testing.)* All of these have free tiers.

| Service | What it does | Sign up at |
|---|---|---|
| **Supabase** | User accounts + database | supabase.com |
| **Google AI Studio** | Gemini API key (the transcription engine) | aistudio.google.com |
| **Cloudflare R2** | Stores uploaded audio files | dash.cloudflare.com |
| **FFmpeg** | Splits audio into chunks (installed on your PC) | see step 1 |

You will collect a handful of keys from these services and paste them into one file called `.env`.

---

## 1. Run it locally (fix for the errors you saw)

The errors you hit earlier were **not** code bugs — they came from using the wrong Python.
When you typed `uvicorn ...`, Windows ran a *different* Python than the one your packages
were installed into. The fix is to always call the virtual environment's own Python directly.

### 1a. Install FFmpeg (needed for audio chunking)
Open **PowerShell** and run:
```powershell
winget install Gyan.FFmpeg
```
Close and reopen PowerShell afterward, then confirm:
```powershell
ffmpeg -version
```
If you see version text, you're good. (If `winget` isn't available, download FFmpeg from
gyan.dev, unzip it, and add its `bin` folder to your PATH.)

### 1b. Set up the project (run each block once)
```cmd
cd C:\Users\Rony\Desktop\transcriber
python -m venv venv
venv\Scripts\python -m pip install --upgrade pip
venv\Scripts\pip install -r requirements.txt
```
> `requirements.txt` already includes `audioop-lts`, which fixes the `No module named
> 'pyaudioop'` error on Python 3.13.

### 1c. Start the server (always use this exact command)
```cmd
venv\Scripts\python -m uvicorn backend.main:app --reload
```
Then open **http://127.0.0.1:8000** in your browser.

**The marketing pages (Home, Pricing, RA Services) work immediately** — even before Supabase
is set up. Signup, login, upload, and admin need the keys in steps 2–4.

> **Important for local testing:** in your `.env`, keep `COOKIE_SECURE=false`. Browsers reject
> "secure" cookies over plain `http://localhost`, so login would silently fail otherwise. This
> is already set for you. Switch it to `true` only when you deploy with HTTPS (step 7).

---

## 2. Set up Supabase (accounts + database)

1. Create a project at supabase.com (pick any region close to Bangladesh, e.g. Singapore).
2. In the left menu go to **SQL Editor → New query**, open the file `schema.sql` from this
   project, copy its entire contents, paste, and click **Run**. This creates all your tables.
3. Go to **Project Settings → API** and copy these three values into your `.env`:
   - `Project URL` → `SUPABASE_URL`
   - `anon public` key → `SUPABASE_ANON_KEY`
   - `service_role` key → `SUPABASE_SERVICE_ROLE_KEY`  *(keep this one secret)*
4. Go to **Authentication → Sign In / Providers → Email** and **for now turn OFF "Confirm
   email"**. This lets you log in immediately after signing up while testing. (Turn it back on
   before going live so real users must verify their address.)

---

## 3. Get a Gemini API key

1. Go to aistudio.google.com → **Get API key → Create API key**.
2. Copy it into `.env` as `GOOGLE_API_KEY`.
3. Leave the model names as they are: `gemini-2.5-flash` (trial) and `gemini-2.5-pro` (paid).

---

## 4. Set up Cloudflare R2 (audio storage)

1. In the Cloudflare dashboard go to **R2 → Create bucket** (name it e.g. `yourra-audio`).
2. Go to **R2 → Manage API Tokens → Create API Token** with **Object Read & Write** permission.
3. Fill these into `.env`:
   - Account ID (shown on the R2 overview page) → `R2_ACCOUNT_ID`
   - Access Key ID → `R2_ACCESS_KEY_ID`
   - Secret Access Key → `R2_SECRET_ACCESS_KEY`
   - Your bucket name → `R2_BUCKET_NAME`
4. Leave `R2_PUBLIC_URL` blank (not needed for the MVP).

---

## 5. Fill in `.env` and set your admin password

Open `C:\Users\Rony\Desktop\transcriber\.env` and complete every value. The important ones:

```
ADMIN_USERNAME=admin
ADMIN_PASSWORD=pick-a-strong-password-here   ← this is YOUR admin login
BKASH_NUMBER=01XXXXXXXXX                      ← your personal bKash number (shown to users)
WHATSAPP_NUMBER=+8801XXXXXXXXX                ← optional, shown to users
COOKIE_SECURE=false                           ← keep false for local; true in production
```

Save the file, then restart the server (Ctrl+C in PowerShell, then run the command from 1c again).

---

## 6. Full end-to-end test

### 6a. Test as a USER
1. Open http://127.0.0.1:8000 → click **Start free** → create an account
   (e.g. `you+test@gmail.com`, password ≥ 6 chars).
2. Log in. You should land on the **Dashboard** showing **5 minutes** of free credit
   (the free trial is granted automatically on first login).
3. Upload a short audio file (under 5 minutes for the trial). The job appears in
   **Your transcriptions** and the progress bar updates automatically.
4. When it reaches **Completed**, click **View** → you'll see Bangla + English side by side
   and three **Download** buttons.

> In local mode without a real Gemini key, the transcript will be **sample/mock text** — that's
> expected and confirms the whole pipeline works. Add a real `GOOGLE_API_KEY` (starts with
> `AIza`) to your `.env` and restart to get actual Bangla transcription.
>
> If the job shows **Failed**, it's almost always because **FFmpeg isn't installed** (it's
> still required to split the audio, even in local mode) — see step 1a. Other causes are in the
> Troubleshooting table below.

### 6b. Test as the ADMIN (you)
1. Go to **http://127.0.0.1:8000/admin**.
2. Your browser will pop up a login box — enter the `ADMIN_USERNAME` and `ADMIN_PASSWORD`
   from your `.env`.
3. You'll see the admin dashboard with **Users, Payments, Jobs, Service Requests**.

### 6c. Test the payment → credit flow
1. As the **user**, go to Dashboard → **Top up credits**, pick a bundle, enter any text as the
   bKash Transaction ID, and submit. (In real life they'd send you money first.)
2. As the **admin**, open **/admin/payments** → you'll see the pending request → click
   **Approve**. The minutes are added to that user's balance instantly.
3. Back as the user, the credit bar refreshes within a few seconds.

> You can also grant credits directly: **/admin** → *Manually activate credits* → enter the
> user's email + minutes. Use this for institutional clients or to fix a balance.

---

## 7. Deploy online (Railway)

When local testing works, put it on the internet:

1. Push this folder to a GitHub repo (you already have one).
2. At railway.app → **New Project → Deploy from GitHub repo** → pick your repo.
3. In Railway → **Variables**, add **every line** from your `.env` — but change these for production:
   ```
   LOCAL_MODE=false          ← use real Supabase + R2 (SQLite/local disk are wiped on every redeploy)
   COOKIE_SECURE=true         ← Railway serves over HTTPS, so secure cookies work and are safer
   ```
   With `LOCAL_MODE=false` you **must** also fill in the real Supabase keys (section 2) and
   Cloudflare R2 keys (section 4), plus a real `GOOGLE_API_KEY`, or those features won't work.
4. Railway auto-detects the `Procfile` and installs FFmpeg automatically. It will give you a
   public URL like `https://yourra.up.railway.app`.
5. In Supabase, turn **"Confirm email" back ON** so real users verify their address.
6. (Optional) Point a custom domain (e.g. `yourra.com`) at the Railway URL.

---

## 8. Troubleshooting (the exact errors you may see)

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'dotenv'` | You ran the system `uvicorn`, not the venv's | Always start with `venv\Scripts\python -m uvicorn backend.main:app --reload` |
| `No module named 'pyaudioop'` | Python 3.13 removed `audioop` | Already fixed — `audioop-lts` is in `requirements.txt`; just reinstall: `venv\Scripts\pip install -r requirements.txt` |
| `SupabaseException: Invalid API key` | Supabase keys missing/placeholder | Paste the real `SUPABASE_URL`, `anon`, and `service_role` keys (step 2) |
| Login seems to do nothing / kicks you back to login | Secure cookie blocked on http | Set `COOKIE_SECURE=false` for local (already set) |
| Signup says "check your email" but you can't log in | Email confirmation is on | For testing, turn off "Confirm email" in Supabase (step 2.4) |
| Job status goes to **Failed** with an FFmpeg error | FFmpeg not installed/on PATH | Install FFmpeg (step 1a) and restart PowerShell |
| Job **Failed** mentioning the model or API key | Gemini key wrong/quota | Recheck `GOOGLE_API_KEY`; confirm the key works in AI Studio |
| Upload rejected as "no credits" | Trial used up / balance is 0 | Approve a top-up or use admin *Manually activate credits* |

---

## 9. Quick reference

| Thing | Where |
|---|---|
| Local site | http://127.0.0.1:8000 |
| Admin panel | http://127.0.0.1:8000/admin |
| Start server | `venv\Scripts\python -m uvicorn backend.main:app --reload` |
| Database schema | `schema.sql` (run in Supabase SQL editor) |
| All settings | `.env` |
| Credit bundles & prices | edit `BUNDLES` in `backend/routers/transcription.py` |
| Free-trial length | `TRIAL_MINUTES` in `.env` (currently 5) |
| Local vs production | `LOCAL_MODE` in `.env` (`true` = local SQLite/disk; `false` = Supabase/R2) |
| Local database file | `yourra_local.db` — delete it to reset all local users/jobs |
| Local audio files | `local_storage/` folder — safe to delete to free space |
| Reset everything locally | stop server, delete `yourra_local.db` and `local_storage/`, restart |

> **Housekeeping:** the files `app.py`, `templates/index.html`, `tempCodeRunnerFile.py`, and the
> `temp_transcriptions/` folder are leftovers from your original local prototype. The new app
> lives entirely under `backend/`. You can safely delete those leftovers once you're confident
> the new version works — they are not used by `backend.main:app`.
