"""
Auth helpers.

- get_current_user: FastAPI dependency that validates the Supabase JWT
  passed either as an httpOnly cookie ("sb_access_token") or an
  Authorization: Bearer header, and returns the user's profile row.
- require_admin: HTTP Basic Auth dependency for /admin/* routes.
"""
import secrets

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from backend.config import settings
from backend.database import supabase_admin, supabase_auth

basic_auth = HTTPBasic()


def _extract_token(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1]
    return request.cookies.get("sb_access_token")


async def get_current_user(request: Request) -> dict:
    """
    Validate the Supabase JWT and return the user's profile row
    (from user_profiles), creating it on first login if missing.
    """
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        # Verify on the dedicated auth client so the service-role data client
        # (supabase_admin) is never re-authed/downgraded to this user.
        user_resp = supabase_auth.auth.get_user(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    user = getattr(user_resp, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    # Ensure a user_profiles row exists (created on first authenticated request
    # after email verification).
    existing = (
        supabase_admin.table("user_profiles")
        .select("*")
        .eq("id", user.id)
        .execute()
    )

    if existing.data:
        profile = existing.data[0]
        if profile.get("is_active") == 0:
            raise HTTPException(status_code=403, detail="Your account is paused. Please contact support.")
    else:
        new_profile = {
            "id": user.id,
            "email": user.email,
            "credits_minutes": 0,
            "trial_used": False,
        }
        inserted = supabase_admin.table("user_profiles").insert(new_profile).execute()
        profile = inserted.data[0]

    profile["_auth_user_id"] = user.id
    profile["_access_token"] = token
    return profile


def require_admin(credentials: HTTPBasicCredentials = Depends(basic_auth)) -> str:
    """HTTP Basic Auth gate for /admin/* routes."""
    correct_username = secrets.compare_digest(credentials.username, settings.ADMIN_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, settings.ADMIN_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
