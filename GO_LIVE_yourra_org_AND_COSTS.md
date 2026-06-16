# YourRA — Going Live on yourra.org + Scaling + Total Costs

_Last updated: 16 June 2026. Prices verified June 2026; treat them as estimates — providers change pricing. USD→BDT converted at ~৳120/USD._

This guide has three parts: (A) move the site to your own domain `yourra.org`, (B) make it scalable for heavy traffic, and (C) the full cost breakdown.

---

## A. Put the site on yourra.org

### Step 1 — Buy the domain
Register `yourra.org` at a registrar that sells at cost:
- **Cloudflare Registrar** — ~$10.44/year, no markup. Best choice because you already use Cloudflare for R2, so DNS and domain live in one place.
- Alternatives: Spaceship/Namecheap (~$9.98/year renewal, often $4.99 first year).

First check that `yourra.org` is available. If `.org` is taken, consider `.com` (slightly higher, ~$10–11/yr at Cloudflare) or `.io`/`.ai` (much pricier).

### Step 2 — Add the custom domain in Railway
In Railway → your **web** service → Settings → Networking → Custom Domain, add both:
- `yourra.org`
- `www.yourra.org`

Railway will show you a **CNAME target** (something like `xxxx.up.railway.app`) for each. Copy these.

### Step 3 — Point DNS (in Cloudflare)
In the Cloudflare dashboard for `yourra.org` → DNS:
- Add a **CNAME** record: name `www` → value = Railway's target. 
- Add a **CNAME** record for the root: name `@` (yourra.org) → Railway's target. Cloudflare supports "CNAME flattening" at the root, so this works for the apex domain.
- Set both records to **DNS only (grey cloud)** at first, so Railway can issue its TLS certificate cleanly. Once the site loads over HTTPS, you can switch the proxy **on (orange cloud)** and set Cloudflare SSL/TLS mode to **Full (strict)** to get Cloudflare's CDN/DDoS protection in front of Railway.

### Step 4 — Wait for TLS
Railway provisions a free Let's Encrypt certificate automatically once DNS resolves — usually a few minutes, up to ~1 hour. The custom domain shows "Active" when ready.

### Step 5 — Update app + Supabase settings (important)
- In Railway env: set `APP_BASE_URL=https://yourra.org` and confirm `COOKIE_SECURE=true`.
- In **Supabase → Authentication → URL Configuration**: set **Site URL** to `https://yourra.org` and add it to **Redirect URLs**. This is required so email confirmation and password-reset links point to your domain, not the railway URL.
- Optional: in Cloudflare, enable **Always Use HTTPS** and **Automatic HTTPS Rewrites**.
- Optional: redirect the old `*.up.railway.app` URL to `https://yourra.org` so old links forward.

### Step 6 — Verify
Open `https://yourra.org`, sign up with a test email, confirm the email link points to yourra.org, log in, and run a short transcription. Done.

There is **no downtime** to your current Railway URL during this — it keeps working until you switch over.

---

## B. Make it scalable ("tons of users")

The app is already built for concurrency (blocking work is offloaded to threads so one instance handles many simultaneous jobs). To go from "works" to "scales reliably," do these, roughly in order:

1. **Move to Railway Pro** ($20/mo) — better resources, no sleeping, and the ability to run **multiple replicas** of the web service. Set 2–3 replicas; the `/health` check already exists.
2. **Re-enable the background worker.** Add a **Redis** instance on Railway, set `REDIS_URL`, and run `worker.py` as a **second Railway service** in the same project (`python worker.py`). This moves transcription off the web process so deploys/crashes don't kill jobs, and the queue absorbs spikes. (Code is already written for this; it was just disabled.)
3. **Add a stuck-job reaper** (see handoff backlog) so any job that dies is marked failed and credits are protected — never an infinite spinner.
4. **Upgrade Supabase to Pro** ($25/mo) — the free tier pauses after a week of inactivity and has small limits; Pro removes pausing, adds daily backups, more database/storage, and connection pooling (Supavisor) for many concurrent connections.
5. **Presigned R2 direct uploads** for large audio files — uploads go straight to R2, bypassing the web server's request-body limit and memory.
6. **Set spend caps & alerts** everywhere: a Railway usage limit, a Supabase spend cap, Cloudflare R2 is mostly free (no egress fees), and a **Gemini API budget alert** in Google AI Studio / Cloud so a runaway loop can't surprise you.
7. **Monitoring:** Railway metrics + logs, Supabase logs, and an uptime check (e.g., a free pinger) on `https://yourra.org/health`.

R2 storage stays tiny because audio is deleted after each transcript is saved, so storage cost is effectively nil regardless of scale.

---

## C. Total cost

### One-time / setup
Effectively **৳0**. Everything is self-serve. The only unavoidable spend is the domain (below). Optional later: a dedicated business phone number, and logo trademark registration if you choose to register.

### Recurring — two tiers

**Tier 1 — Lean / validation (good for the first users):**

| Item | Plan | USD/mo | ৳/mo (~) |
|---|---|---|---|
| Railway | Hobby ($5, includes $5 usage) | $5 | ৳600 |
| Supabase | Free | $0 | ৳0 |
| Cloudflare R2 | Free tier (10 GB, audio auto-deleted) | $0 | ৳0 |
| Domain (yourra.org) | ~$10.44/yr amortized | ~$0.9 | ৳105 |
| Email (SMTP) | Free tier (e.g., Resend/Brevo) | $0 | ৳0 |
| **Fixed subtotal** | | **~$6** | **~৳700/mo** |

Plus Gemini API usage (variable — see below). No Redis at this tier (jobs run in-process).

**Tier 2 — Scalable / production (recommended once you have steady users):**

| Item | Plan | USD/mo | ৳/mo (~) |
|---|---|---|---|
| Railway | Pro ($20, includes $20 usage) + extra replicas | $20–30 | ৳2,400–3,600 |
| Railway Redis | small instance for the worker queue | ~$5 | ৳600 |
| Supabase | Pro | $25 | ৳3,000 |
| Cloudflare R2 | Free tier (likely still free) | $0 | ৳0 |
| Domain | amortized | ~$0.9 | ৳105 |
| Email (SMTP) | Free or low tier | $0–5 | ৳0–600 |
| **Fixed subtotal** | | **~$51–66** | **~৳6,100–7,900/mo** |

Plus Gemini API usage (variable).

### Gemini API (the variable cost — passed through by your pricing)
Gemini 2.5 Pro is **$1.25 / 1M input tokens** and **$10 / 1M output tokens** (batch mode is half price). In practice your observed cost has been roughly **৳150–200 per hour of audio** transcribed. Since you charge **৳399/hour**, each hour leaves roughly **৳200–250 gross margin** before fixed costs.

### What this means for break-even
At the scalable tier (~৳7,000/mo fixed) and ~৳200 margin per hour of audio, you cover all fixed costs at roughly **35 hours of audio per month** (~9 customers buying the 1-hour Mini, or 2 customers buying the Pro Bundle). Everything above that is profit, minus the API cost which is already inside the ৳399 price.

At the lean tier (~৳700/mo fixed) you break even at well under **5 hours/month**.

### Recommendation
Start on **Tier 1** to keep burn near zero while you get your first paying institutions. The moment you have steady jobs (or before a big institutional pilot), move to **Tier 2** and enable the Redis worker + a second web replica — that's the configuration that comfortably handles "tons of users" without losing jobs on deploys.

---

## Sources (prices, June 2026)
- Railway pricing: https://costbench.com/software/developer-tools/railway/ , https://www.saasworthy.com/product/railway-app/pricing
- Supabase pricing: https://uibakery.io/blog/supabase-pricing , https://www.saaspricepulse.com/tools/supabase
- Cloudflare R2 pricing: https://www.cloudflare.com/products/r2/ , https://egresscost.com/cloudflare/
- .org domain pricing: https://tldprice.org/registrar/cloudflare , https://domaindetails.com/registrars/cheapest
- Gemini 2.5 Pro API pricing: https://www.tldl.io/resources/google-gemini-api-pricing , https://pricepertoken.com/pricing-page/model/google-gemini-2.5-pro
