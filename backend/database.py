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

    def get_supabase_for_token(access_token: str):
        # RLS doesn't apply locally; the same client is used everywhere.
        return supabase_admin

else:
    from supabase import create_client, Client

    supabase_admin: "Client" = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY,
    )

    def get_supabase_for_token(access_token: str) -> "Client":
        """Return a Supabase client that acts as the given user (RLS applies)."""
        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
        client.postgrest.auth(access_token)
        return client
