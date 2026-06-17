"""
Auth helpers.

- get_current_user: FastAPI dependency that validates the Supabase JWT passed
  as an httpOnly cookie ("sb_access_token") or an Authorization: Bearer header,
  and returns the user's profile row. If the access token has expired but a
  valid refresh token cookie ("sb_refresh_token") is present, it transparently
  refreshes the session and stashes the new tokens on request.state so a
  middleware can re-set the cookies — keeping users logged in for the full
  cookie lifetime instead of just the ~1 hour access-token window.
- require_admin: HTTP Basic Auth dependency for /admin/* routes.
"""
import secrets
import time

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from backend.config import settings
from backend.database import supabase_admin, supabase_auth

basic_auth = HTTPBasic()

ACCESS_COOKIE = "sb_access_token"
REFRESH_COOKIE = "sb_refresh_token"
ADMIN_COOKIE = "ya_admin_session"

# In-memory admin sessions {token: expiry_unix}
_admin_sessions: dict[str, float] = {}
_ADMIN_SESSION_TTL = 8 * 3600  # 8 hours


def create_admin_session() -> str:
    token = secrets.token_urlsafe(32)
    now = time.time()
    _admin_sessions[token] = now + _ADMIN_SESSION_TTL
    # Prune expired entries
    expired = [k for k, v in list(_admin_sessions.items()) if v < now]
    for k in expired:
        _admin_sessions.pop(k, None)
    return token


def verify_admin_session(token: str | None) -> bool:
    if not token:
        return False
    expiry = _admin_sessions.get(token)
    if not expiry or expiry < time.time():
        _admin_sessions.pop(token, None)
        return False
    return True


def revoke_admin_session(token: str | None):
    if token:
        _admin_sessions.pop(token, None)


def _extract_token(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1]
    return request.cookies.get(ACCESS_COOKIE)


def _verify_token(token: str | None):
    """Return the auth user for a valid access token, else None."""
    if not token:
        return None
    try:
        resp = supabase_auth.auth.get_user(token)
        return getattr(resp, "user", None)
    except Exception:
        return None


def _try_refresh(request: Request):
    """If the access token is dead but a refresh token cookie is valid, mint a
    new session. Returns (user, access_token, refresh_token) or None.

    Skipped in LOCAL_MODE (the local shim's tokens don't expire) and guarded so
    any failure simply means 'not authenticated' rather than a crash."""
    if settings.LOCAL_MODE:
        return None
    refresh = request.cookies.get(REFRESH_COOKIE)
    if not refresh:
        return None
    try:
        res = supabase_auth.auth.refresh_session(refresh)
        session = getattr(res, "session", None)
        user = getattr(res, "user", None) or (getattr(session, "user", None) if session else None)
        if session and user and getattr(session, "access_token", None):
            return user, session.access_token, session.refresh_token
    except Exception:
        return None
    return None


async def get_current_user(request: Request) -> dict:
    """
    Validate the session and return the user's profile row (from user_profiles),
    creating it on first login if missing. Refreshes an expired access token
    when possible.
    """
    token = _extract_token(request)
    user = _verify_token(token)
    access_token = token

    if user is None:
        refreshed = _try_refresh(request)
        if refreshed:
            user, access_token, new_refresh = refreshed
            # Hand the new tokens to the cookie-refresh middleware (main.py).
            request.state.refreshed_tokens = (access_token, new_refresh)
        else:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired session" if token else "Not authenticated",
            )

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
    profile["_access_token"] = access_token
    return profile


async def require_admin(request: Request):
    """Session-cookie gate for /admin/* routes. Redirects to /admin/login if not authenticated."""
    if not settings.ADMIN_PASSWORD or not settings.ADMIN_USERNAME:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin panel is not configured. Set ADMIN_USERNAME and ADMIN_PASSWORD.",
        )
    token = request.cookies.get(ADMIN_COOKIE)
    if not verify_admin_session(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin login required")
