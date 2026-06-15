"""
Free trial enforcement + disposable email blocking.
"""
import httpx

from backend.config import settings
from backend.database import supabase_admin


async def is_disposable_email(email: str) -> bool:
    """Check an email against the disposable-email blocklist API.
    Fails OPEN (returns False) if the check service is unreachable,
    so signups are never blocked by a third-party outage."""
    if settings.LOCAL_MODE:
        # No external calls in local mode (and avoids an offline timeout).
        return False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                "https://mailcheck.p.ninja/api/v1/check",
                params={"email": email},
            )
            data = resp.json()
            return bool(data.get("disposable", False))
    except Exception:
        return False


def trial_available(profile: dict, ip: str) -> bool:
    """Return True if this user/IP combination can still claim the free trial."""
    if profile.get("trial_used"):
        return False

    existing_ip = (
        supabase_admin.table("trial_ips").select("ip").eq("ip", ip).execute()
    )
    if existing_ip.data:
        return False

    return True


def grant_trial(user_id: str, email: str, ip: str):
    """Mark the trial as used for this user and record the IP."""
    supabase_admin.table("user_profiles").update(
        {"trial_used": True, "trial_ip": ip, "credits_minutes": settings.TRIAL_MINUTES}
    ).eq("id", user_id).execute()

    supabase_admin.table("trial_ips").upsert(
        {"ip": ip, "email": email}
    ).execute()

    supabase_admin.table("credit_transactions").insert(
        {
            "user_id": user_id,
            "minutes_added": settings.TRIAL_MINUTES,
            "transaction_type": "trial",
            "notes": f"Free trial granted from IP {ip}",
        }
    ).execute()


def client_ip(request) -> str:
    """Best-effort client IP extraction (handles Railway/Cloudflare proxies)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
