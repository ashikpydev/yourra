"""
Database client setup.

- In LOCAL_MODE (default): `supabase_admin` is a self-contained SQLite-backed
  LocalDB that mimics the Supabase client API — no external services needed.
- In production (LOCAL_MODE=false): `supabase_admin` is the real Supabase
  service-role client (bypasses RLS; only use after verifying the user's JWT).
"""
from backend.config import settings

if settings.LOCAL_MODE:
    from backend.local_db import LocalDB

    supabase_admin = LocalDB()
    # Locally the same shim handles auth + data; no RLS to worry about.
    supabase_auth = supabase_admin

    def get_supabase_for_token(access_token: str):
        # RLS doesn't apply locally; the same client is used everywhere.
        return supabase_admin

else:
    from supabase import create_client, Client

    def _diagnose_service_role_key() -> None:
        """Log (without exposing the secret) whether SUPABASE_SERVICE_ROLE_KEY
        actually resolves to the service_role. A non-service role means RLS will
        silently block writes (job status, credits) and reject inserts."""
        import base64
        import json as _json
        import os as _os

        raw = _os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        key = settings.SUPABASE_SERVICE_ROLE_KEY
        issues = []
        if raw != raw.strip():
            issues.append("leading/trailing whitespace")
        if len(raw) >= 2 and raw[0] in "\"'" and raw[-1] in "\"'":
            issues.append("wrapped in quotes")

        role = "unknown"
        if key.startswith("eyJ"):
            try:
                payload = key.split(".")[1]
                payload += "=" * (-len(payload) % 4)
                role = _json.loads(base64.urlsafe_b64decode(payload)).get("role", "unknown")
            except Exception:
                role = "undecodable-JWT"
        elif key.startswith("sb_secret_"):
            role = "service_role(new-secret)"
        elif key.startswith("sb_publishable_"):
            role = "anon(PUBLISHABLE-key)"

        print(f"[startup] supabase service key: role={role} len={len(key)} issues={issues or 'none'}", flush=True)
        if role not in ("service_role", "service_role(new-secret)") or issues:
            print("[startup] *** WARNING: this is NOT a clean service_role key. RLS will block "
                  "status/credit writes and admin actions. Fix SUPABASE_SERVICE_ROLE_KEY. ***", flush=True)

    try:
        _diagnose_service_role_key()
    except Exception:
        pass

    # PRIVILEGED data client — must stay service_role forever. NEVER call
    # .auth.get_user()/sign_in() on this client: doing so re-auths the shared
    # client as that user and silently drops service_role (which then gets
    # blocked by RLS on writes that have no user policy).
    supabase_admin: "Client" = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY,
    )

    # SEPARATE client used ONLY to verify user login tokens. It can be safely
    # re-authed by get_user() because we never use it for table operations.
    supabase_auth: "Client" = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_ANON_KEY,
    )

    def get_supabase_for_token(access_token: str) -> "Client":
        """Return a Supabase client that acts as the given user (RLS applies)."""
        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
        client.postgrest.auth(access_token)
        return client
