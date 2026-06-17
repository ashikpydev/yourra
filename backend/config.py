"""
Application configuration.

All values are read from environment variables (see .env.example).
Never hardcode secrets here.
"""
import os
from dotenv import load_dotenv

# override=True so the values in .env always win over any stale Windows
# environment variable of the same name (a common cause of "I changed .env
# but the app still uses the old key").
load_dotenv(override=True)


class Settings:
    # Supabase
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    # Gemini
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    GEMINI_MODEL_FLASH: str = os.getenv("GEMINI_MODEL_FLASH", "gemini-2.5-flash")
    GEMINI_MODEL_PRO: str = os.getenv("GEMINI_MODEL_PRO", "gemini-2.5-pro")

    # Cloudflare R2 (S3-compatible)
    R2_ACCOUNT_ID: str = os.getenv("R2_ACCOUNT_ID", "")
    R2_ACCESS_KEY_ID: str = os.getenv("R2_ACCESS_KEY_ID", "")
    R2_SECRET_ACCESS_KEY: str = os.getenv("R2_SECRET_ACCESS_KEY", "")
    R2_BUCKET_NAME: str = os.getenv("R2_BUCKET_NAME", "")
    R2_PUBLIC_URL: str = os.getenv("R2_PUBLIC_URL", "")

    @property
    def R2_ENDPOINT_URL(self) -> str:
        return f"https://{self.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

    # Admin panel (HTTP Basic Auth)
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")

    # App
    APP_SECRET_KEY: str = os.getenv("APP_SECRET_KEY", "change-me")
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "500"))
    BKASH_NUMBER: str = os.getenv("BKASH_NUMBER", "")
    WHATSAPP_NUMBER: str = os.getenv("WHATSAPP_NUMBER", "")

    # Session cookie security.
    # MUST be "false" for local http://localhost testing (browsers drop
    # Secure cookies sent over plain HTTP). Set COOKIE_SECURE=true in
    # production once the site is served over HTTPS.
    COOKIE_SECURE: bool = os.getenv("COOKIE_SECURE", "false").lower() == "true"

    # ---- Local development mode ----
    # When true, the app runs fully self-contained on your computer:
    #   * SQLite (./yourra_local.db) instead of Supabase
    #   * local disk (./local_storage) instead of Cloudflare R2
    #   * mock transcription if no real Gemini key is set
    # No external accounts are required. Set LOCAL_MODE=false in production
    # and provide real Supabase + R2 credentials.
    LOCAL_MODE: bool = os.getenv("LOCAL_MODE", "true").lower() == "true"
    LOCAL_DB_PATH: str = os.getenv("LOCAL_DB_PATH", "./yourra_local.db")
    LOCAL_STORAGE_DIR: str = os.getenv("LOCAL_STORAGE_DIR", "./local_storage")

    # Public base URL (used in emails). Set to your real domain in production.
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")

    # Redis job queue (optional). When set (production), transcription runs on a
    # separate worker process instead of in the web process — scales better and
    # survives deploys. Leave blank to run jobs in-process (local/simple).
    REDIS_URL: str = os.getenv("REDIS_URL", "")

    # Email (SMTP) — used to notify a user when an admin creates their account.
    # Leave SMTP_HOST blank to disable sending (the app logs the message instead).
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASS: str = os.getenv("SMTP_PASS", "")
    SMTP_FROM: str = os.getenv("SMTP_FROM", "")

    # Trial / chunking config
    TRIAL_MINUTES: int = int(os.getenv("TRIAL_MINUTES", "5"))
    CHUNK_TARGET_SECONDS: int = int(os.getenv("CHUNK_TARGET_SECONDS", "600"))  # 10 minutes
    CHUNK_HARD_MAX_SECONDS: int = int(os.getenv("CHUNK_HARD_MAX_SECONDS", "660"))  # up to 11 min to find silence
    SILENCE_THRESH_DBFS: int = int(os.getenv("SILENCE_THRESH_DBFS", "-40"))
    MIN_SILENCE_LEN_MS: int = int(os.getenv("MIN_SILENCE_LEN_MS", "500"))

    # Temp working directory for pipeline
    TMP_DIR: str = os.getenv("TMP_DIR", "/tmp/yourra")

    # R2 retention for original uploads (days)
    R2_RETENTION_DAYS: int = int(os.getenv("R2_RETENTION_DAYS", "7"))

    # Stuck-job recovery (watchdog). On free hosting the web dyno can restart or
    # sleep, dropping in-process queued jobs so they hang forever. These caps let
    # an opportunistic watchdog mark long-stalled jobs as "failed" so the user
    # can simply click Retry. Generous defaults so genuine long jobs aren't hit:
    #   * a job actively "processing" for this many minutes is treated as dead
    STUCK_JOB_MINUTES: int = int(os.getenv("STUCK_JOB_MINUTES", "60"))
    #   * a job still "pending" (never started) for this many minutes is failed
    STUCK_PENDING_MINUTES: int = int(os.getenv("STUCK_PENDING_MINUTES", "180"))


settings = Settings()
