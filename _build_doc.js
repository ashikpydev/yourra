const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun,
  AlignmentType, LevelFormat, HeadingLevel, BorderStyle, WidthType, ShadingType,
  TableOfContents, PageBreak, ExternalHyperlink
} = require('/tmp/node_modules/docx');

const INK = "0F172A", MUT = "64748B", BRAND = "4F46E5", AMBER = "B45309";
const CW = 9360;

const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const H3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(t)] });
const P = (t, opts={}) => new Paragraph({ spacing: { after: 140 }, children: [new TextRun({ text: t, ...opts })] });
const RUNS = (runs) => new Paragraph({ spacing: { after: 140 }, children: runs });
const bullet = (t) => new Paragraph({ numbering: { reference: "b", level: 0 }, spacing: { after: 60 }, children: Array.isArray(t) ? t : [new TextRun(t)] });
const num = (t) => new Paragraph({ numbering: { reference: "n", level: 0 }, spacing: { after: 60 }, children: Array.isArray(t) ? t : [new TextRun(t)] });
const mono = (t) => new Paragraph({ spacing: { after: 0 }, shading: { fill: "F1F5F9", type: ShadingType.CLEAR },
  children: [new TextRun({ text: t, font: "Consolas", size: 17 })] });

const cell = (text, w, head) => new TableCell({
  width: { size: w, type: WidthType.DXA },
  shading: { fill: head ? "EEF2FF" : "FFFFFF", type: ShadingType.CLEAR },
  margins: { top: 70, bottom: 70, left: 120, right: 120 },
  borders: { top:{style:BorderStyle.SINGLE,size:1,color:"CBD5E1"}, bottom:{style:BorderStyle.SINGLE,size:1,color:"CBD5E1"},
             left:{style:BorderStyle.SINGLE,size:1,color:"CBD5E1"}, right:{style:BorderStyle.SINGLE,size:1,color:"CBD5E1"} },
  children: [new Paragraph({ children: [new TextRun({ text: text, bold: !!head, size: 19, color: head?BRAND:INK })] })]
});
function makeTable(widths, data) {
  return new Table({
    width: { size: CW, type: WidthType.DXA }, columnWidths: widths,
    rows: data.map((row, ri) => new TableRow({ tableHeader: ri === 0,
      children: row.map((txt, ci) => cell(txt, widths[ci], ri === 0)) }))
  });
}

const logoPath = "/sessions/pensive-inspiring-allen/mnt/transcriber/backend/static/img/logo.png";
const hasLogo = fs.existsSync(logoPath);
const children = [];

if (hasLogo) children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 1600, after: 200 },
  children: [new ImageRun({ type: "png", data: fs.readFileSync(logoPath), transformation: { width: 90, height: 90 },
    altText: { title: "YourRA", description: "YourRA logo", name: "logo" } })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, children: [new TextRun({ text: "YourRA", bold: true, size: 56, color: BRAND, font: "Arial" })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 }, children: [new TextRun({ text: "Master Project Document", bold: true, size: 30 })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 40 }, children: [new TextRun({ text: "Bangla qualitative-research transcription — Bangla verbatim + English translation", italics: true, size: 20, color: MUT })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 }, children: [new TextRun({ text: "Updated 16 June 2026", size: 18, color: MUT })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 }, children: [new TextRun({ text: "Purpose: hand this document to any new chat (with the project folder connected) so the assistant can continue from exactly where we left off — our thinking, decisions, architecture, and roadmap.", size: 18, color: MUT })] }));
children.push(new Paragraph({ children: [new PageBreak()] }));

children.push(H1("Contents"));
children.push(new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-2" }));
children.push(new Paragraph({ children: [new PageBreak()] }));

children.push(H1("1. What YourRA is"));
children.push(P("YourRA is a production web service that turns recorded qualitative-research interviews (IDI, FGD, KII, case study) into a clean, ready-to-hand-over deliverable. A researcher uploads an audio file and receives:"));
children.push(bullet("A faithful Bangla verbatim transcript with speaker labels (Moderator vs Respondents) and timestamps."));
children.push(bullet("A natural English translation aligned line-for-line with the Bangla."));
children.push(bullet("A polished Word (.docx) report that opens with a respondent demographic table, branded with the YourRA logo, carrying an AI-accuracy declaration."));
children.push(bullet("Plain-text exports (Bangla, English, combined)."));
children.push(P("The core promise is quality first. A human research assistant typically needs about one working day to transcribe one hour of audio; YourRA delivers it in minutes, at a fraction of the cost, while giving the researcher tools to verify and perfect the result."));
children.push(RUNS([ new TextRun({ text: "Live site: ", bold: true }),
  new ExternalHyperlink({ children: [new TextRun({ text: "web-production-d958a.up.railway.app", style: "Hyperlink" })], link: "https://web-production-d958a.up.railway.app" }),
  new TextRun("   •   Target domain: yourra.org   •   Owner: Rony (rashikur504@gmail.com)") ]));

children.push(H1("2. Our thinking (decisions to preserve)"));
children.push(P("These are deliberate product/engineering decisions reached through real testing or business reasoning. Do not reverse without good reason."));
children.push(bullet("Quality over everything — the transcript must be trustworthy for research analysis."));
children.push(bullet("Chunk → full transcribe → lossless merge. ~10-minute silence-aware chunks, each transcribed in full, concatenated with no boundary re-stitching. Fixed dropped content in long files; never replace with a single-call approach."));
children.push(bullet("Always Gemini 2.5 Pro for the transcript; the cheaper Flash only for the small demographic extraction."));
children.push(bullet("Price ৳399 per hour of audio; bundles + custom-hours; credits never expire."));
children.push(bullet("No automatic free trial — a 'Request a trial' form; an admin grants credits."));
children.push(bullet("Verify on the web, deliver clean — timestamps and confidence flags live on the website; the downloaded Word is clean."));
children.push(bullet("Preserve the original prototype — new code lives in the 'yourra' repo; the prototype repo must not be overwritten."));

children.push(H1("3. How it works (pipeline)"));
children.push(num("User uploads audio (MP3/WAV/M4A/OGG/MP4, up to 500 MB) and optionally enters survey + respondent demographics."));
children.push(num("The file is stored (Cloudflare R2 in production; local disk in local mode)."));
children.push(num("It is split into ~10-minute chunks on natural silence boundaries (pydub + ffmpeg)."));
children.push(num("Each chunk is transcribed fully and sequentially by Gemini 2.5 Pro with a short continuity context; chunks merge losslessly with absolute timestamps from per-chunk offsets."));
children.push(num("Speaker roles are detected; spoken demographics auto-extracted to pre-fill the table; guessed words are flagged."));
children.push(num("The transcript is saved; audio is kept for a 7-day review window for playback, then auto-deleted."));
children.push(num("The researcher reviews/edits on the site, then downloads the clean Word report and text files."));
children.push(RUNS([new TextRun({ text: "Strict credit rule: ", bold: true }), new TextRun("only the user's available minutes are transcribed; a longer file is trimmed to exactly the remaining credit (20-min file with 14 credits → exactly the first 14 minutes).")]));

children.push(H1("4. The review & editing experience"));
children.push(P("This differentiates YourRA — a fast, fantastic path to a perfect final transcript."));
children.push(H3("Listen & verify (click-to-play)"));
children.push(bullet("Every line carries a timestamp; click it to play the audio from that exact moment."));
children.push(bullet("The line currently playing highlights in yellow (karaoke-style); optional auto-scroll keeps it in view."));
children.push(bullet("Shortcuts: Space = play/pause, ← / → = seek ±5s, N = next flagged spot (paused while editing)."));
children.push(H3("Inline editing"));
children.push(bullet("Click any Bangla or English line to fix it in place; speaker labels are editable too."));
children.push(bullet("A save bar appears only when there are unsaved edits; the browser warns before leaving with unsaved changes."));
children.push(bullet("Edits preserve the hidden timestamps, so click-to-play keeps working."));
children.push(H3("Confidence flagging (the lifesaver)"));
children.push(bullet("When the AI guesses on noisy/overlapping audio, it marks the guess; the editor highlights those words in amber with an amber rail on the line."));
children.push(bullet("A counter shows how many spots need checking; 'Next flagged' (or N) jumps through them."));
children.push(bullet("Fixing a flagged word clears its highlight; markers never reach the downloads."));
children.push(H3("Clean final Word"));
children.push(bullet("The .docx has the logo header, demographic table, accuracy footer, and NO timestamps or flags — hand-over ready."));

children.push(H1("5. Tech stack & architecture"));
children.push(makeTable([2600, 6760], [
  ["Layer", "Choice"],
  ["Backend", "FastAPI (Python 3.12) + Jinja2 templates"],
  ["Frontend", "Server-rendered HTML, Alpine.js (CDN), Tailwind (CDN), custom design system (static/css/style.css)"],
  ["AI", "Gemini 2.5 Pro (transcription) + 2.5 Flash (demographics) via google-generativeai"],
  ["Audio", "pydub + ffmpeg (ffmpeg in the Docker image)"],
  ["Database / Auth", "Supabase (Postgres + Auth) in production"],
  ["Storage", "Cloudflare R2 (S3-compatible, via boto3)"],
  ["Documents", "python-docx for the Word report"],
  ["Queue (optional)", "Redis + RQ worker (built; off by default — jobs run in-process)"],
  ["Deploy", "Docker on Railway (Dockerfile, Procfile, railway.json, run.py reads $PORT)"],
]));
children.push(RUNS([new TextRun({ text: "Local mode: ", bold: true }), new TextRun("LOCAL_MODE=true (default) runs fully offline — SQLite shim, local-disk storage, mock transcription if no key.")]));

children.push(H1("6. Repository map"));
[ "transcriber/                 (repo root, GitHub: 'yourra')",
  "  backend/",
  "    main.py                  app + page routes (dashboard, result, pricing, trial)",
  "    config.py                Settings (env vars + defaults)",
  "    database.py              service-role client + SEPARATE auth client",
  "    local_db.py              SQLite shim (Supabase-compatible) + local auth",
  "    auth.py                  token verification, current-user, admin gate",
  "    routers/  auth_router.py, transcription.py, admin.py",
  "    services/ gemini.py, chunking.py, pipeline.py, jobs.py, storage.py, docgen.py",
  "    templates/ base, landing, pricing, dashboard, result, login, signup, trial, admin/*",
  "    static/  css/style.css, img/favicon.svg, img/logo.png",
  "  run.py, worker.py, schema.sql, Dockerfile, Procfile, railway.json",
  "  requirements.txt, .env.example, README.md, DEPLOYMENT.md, SETUP_AND_TESTING.md",
  "  PROJECT_HANDOFF.md, GO_LIVE_yourra_org_AND_COSTS.md, YourRA_Master_Document.docx",
].forEach(l => children.push(mono(l)));
children.push(P(""));

children.push(H1("7. Pricing model"));
children.push(makeTable([3120, 3120, 3120], [
  ["Plan", "Includes", "Price"],
  ["Mini", "1 hour (60 min)", "৳399"],
  ["Standard", "3 hours (180 min)", "৳1,199"],
  ["Value", "6 hours (360 min)", "৳2,399"],
  ["Pro Bundle", "15 hours (900 min)", "৳5,999"],
  ["Custom", "Any number of hours", "৳399 / hour"],
]));
children.push(P("Payment is manual bKash 'Send Money'; the user submits the Transaction ID, an admin reviews and grants credits. The pricing page has a transparent step-by-step savings calculator. API cost is ~৳150–200 of Gemini per hour of audio, well under the ৳399 price."));

children.push(H1("8. Environment variables (Railway — no quotes around values)"));
children.push(makeTable([3600, 5760], [
  ["Variable", "Notes"],
  ["LOCAL_MODE", "false in production"],
  ["APP_BASE_URL", "https://yourra.org after migration (else the railway URL)"],
  ["APP_SECRET_KEY", "strong random (openssl rand -hex 32)"],
  ["COOKIE_SECURE", "true in production (HTTPS)"],
  ["ADMIN_USERNAME / ADMIN_PASSWORD", "admin panel login (HTTP Basic)"],
  ["SUPABASE_URL / SUPABASE_ANON_KEY", "project URL + anon (publishable) key"],
  ["SUPABASE_SERVICE_ROLE_KEY", "the service_role SECRET key (must decode to role=service_role)"],
  ["GEMINI_API_KEY", "an AIza... key"],
  ["GEMINI_MODEL_PRO / _FLASH", "gemini-2.5-pro / gemini-2.5-flash"],
  ["R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BUCKET_NAME", "Cloudflare R2 credentials"],
  ["R2_RETENTION_DAYS", "7 (audio review window before auto-delete)"],
  ["BKASH_NUMBER / WHATSAPP_NUMBER", "01575522637 / 01772215084"],
  ["REDIS_URL", "blank = in-process jobs; set only when running the worker"],
]));
children.push(RUNS([new TextRun({ text: "Two hard-won rules: ", bold: true }), new TextRun("never wrap values in quotes in Railway, and the web service must have every variable set (a missing one silently dropped the app into local mode and stranded jobs).")]));

children.push(H1("9. Deployment & the critical RLS lesson"));
children.push(P("Push to the 'yourra' repo main branch; Railway auto-builds from the Dockerfile. Run schema.sql in Supabase when the schema changes (idempotent). Start command is 'python run.py'."));
children.push(RUNS([new TextRun({ text: "Critical lesson (Row-Level Security): ", bold: true, color: AMBER }),
  new TextRun("the backend MUST act as the Supabase service_role to bypass RLS. The bug we hit: one Supabase client was used for BOTH login verification and data writes — and calling .auth.sign_in / get_user on a client downgrades it from service_role to the user's permissions. Once schema.sql turned RLS on, job-status updates silently failed (jobs stuck 'Queued') and admin credit writes threw 42501.")]));
children.push(RUNS([new TextRun({ text: "The fix (in place): ", bold: true }),
  new TextRun("two separate clients — supabase_admin (service_role) only for DB reads/writes and never for auth, and supabase_auth (anon) only for login verification. A startup log reports the resolved key role so it cannot silently regress.")]));

children.push(H1("10. Going live on yourra.org & scaling"));
children.push(H3("Domain migration"));
children.push(num("Register yourra.org (Cloudflare Registrar, at-cost ~$10.44/yr, ideal since R2 is on Cloudflare)."));
children.push(num("Railway → web service → Networking → add yourra.org and www.yourra.org; copy the CNAME targets."));
children.push(num("Cloudflare DNS → CNAME @ and www to the Railway targets (DNS-only first); after HTTPS works, optionally enable the proxy with SSL Full (strict)."));
children.push(num("Set APP_BASE_URL=https://yourra.org and COOKIE_SECURE=true; in Supabase → Auth → URL Configuration set Site URL + redirect URLs to https://yourra.org."));
children.push(num("Verify: sign up, confirm the email link points to yourra.org, run a short transcription."));
children.push(H3("Scaling for heavy traffic"));
children.push(bullet("Railway Pro + 2–3 web replicas (the /health check exists)."));
children.push(bullet("Re-enable the worker: add Redis, set REDIS_URL, run worker.py as a second service."));
children.push(bullet("Add a stuck-job reaper; Supabase Pro (no pausing, backups, pooling); presigned R2 direct uploads for big files."));
children.push(bullet("Set spend caps/alerts on Railway, Supabase, and the Gemini API budget."));

children.push(H1("11. Total cost (June 2026 estimates, ~৳120/USD)"));
children.push(H3("Tier 1 — Lean / validation"));
children.push(makeTable([4680, 2340, 2340], [
  ["Item", "USD/mo", "Tk/mo"],
  ["Railway Hobby ($5, incl. $5 usage)", "$5", "600"],
  ["Supabase Free", "$0", "0"],
  ["Cloudflare R2 (free tier; audio auto-deleted)", "$0", "0"],
  ["Domain (yourra.org, amortized)", "~$0.9", "105"],
  ["Fixed subtotal", "~$6", "~700"],
]));
children.push(H3("Tier 2 — Scalable / production"));
children.push(makeTable([4680, 2340, 2340], [
  ["Item", "USD/mo", "Tk/mo"],
  ["Railway Pro + replicas", "$20-30", "2,400-3,600"],
  ["Railway Redis (worker queue)", "~$5", "600"],
  ["Supabase Pro", "$25", "3,000"],
  ["Cloudflare R2 (likely still free)", "$0", "0"],
  ["Domain (amortized)", "~$0.9", "105"],
  ["Fixed subtotal", "~$51-66", "~6,100-7,900"],
]));
children.push(RUNS([new TextRun({ text: "Plus Gemini API usage ", bold: true }), new TextRun("(~৳150–200 per hour of audio), covered by the ৳399/hour price. Break-even: ~35 hours/month (production) or under 5 hours/month (lean). Setup cost ≈ ৳0.")]));

children.push(H1("12. Hardening & roadmap backlog"));
children.push(H3("Do before onboarding many users"));
children.push(bullet("Confirm COOKIE_SECURE=true; APP_SECRET_KEY / ADMIN_PASSWORD are strong (not placeholders)."));
children.push(bullet("Job durability: reaper for stuck 'processing' jobs (fail + don't charge); re-enable Redis + worker for scale."));
children.push(bullet("UNIQUE constraint on bkash_trx_id + reject duplicate transaction IDs."));
children.push(bullet("Review RLS; enable it on trial_ips / trial_requests (service-role only). Don't block trials by IP (institutions share one IP)."));
children.push(H3("Security & trust"));
children.push(bullet("Rate-limit /admin; record the approving admin per credit transaction."));
children.push(bullet("Write /privacy and /terms (participant audio stored up to 7 days); link from signup + footer."));
children.push(bullet("Raise password minimum to 8–10, add confirm-password, enable email confirmation, add 'Forgot password?'."));
children.push(bullet("Move from personal bKash/WhatsApp numbers to a business number as volume grows."));
children.push(H3("High-leverage features"));
children.push(bullet("Downloadable sample report on the homepage (biggest conversion win)."));
children.push(bullet("Email the user when a job completes/fails."));
children.push(bullet(".srt / .vtt subtitle export; CSV/JSON export for NVivo / ATLAS.ti / MAXQDA."));
children.push(bullet("Custom glossary upload + dialect hint dropdown fed into the prompt."));
children.push(bullet("Admin notification on new payment submission."));

children.push(H1("13. Quick reference"));
children.push(makeTable([3120, 6240], [
  ["Item", "Value"],
  ["Owner", "Rony — rashikur504@gmail.com"],
  ["bKash", "01575522637"],
  ["WhatsApp", "01772215084 (links use wa.me/8801772215084)"],
  ["Admin panel", "/admin (HTTP Basic, ADMIN_USERNAME / ADMIN_PASSWORD)"],
  ["Health check", "/health"],
  ["Logo", "abstract converging-voices mark (also reads as 'Y'); favicon.svg + logo.png"],
  ["Dev note", "the Linux sandbox sometimes shows truncated copies of just-edited files — a mount artifact, not real corruption"],
]));

children.push(H1("14. How to use this document in a new chat"));
children.push(P("Connect the project folder and share this document. Tell the assistant: 'This is the YourRA master document — read it, then continue.' It captures the vision, the decisions to preserve, the architecture, the deployment lessons (especially the service-role/RLS fix), the domain + cost plan, and the roadmap. Pair it with the live code and PROJECT_HANDOFF.md for the fullest picture."));

const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 21 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 30, bold: true, font: "Arial", color: BRAND }, paragraph: { spacing: { before: 300, after: 160 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial", color: INK }, paragraph: { spacing: { before: 220, after: 120 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 21, bold: true, font: "Arial", color: BRAND }, paragraph: { spacing: { before: 160, after: 80 }, outlineLevel: 2 } },
    ]
  },
  numbering: { config: [
    { reference: "b", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 280 } } } }] },
    { reference: "n", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 280 } } } }] },
  ] },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    children
  }]
});

Packer.toBuffer(doc).then(buf => { fs.writeFileSync("/tmp/YourRA_Master_Document.docx", buf); console.log("written:", buf.length, "bytes"); });
