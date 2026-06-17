"""
Profile + job history routes.
"""
from fastapi import APIRouter, Depends

from backend.auth import get_current_user
from backend.database import supabase_admin

router = APIRouter(prefix="/api", tags=["profile"])


@router.get("/profile")
async def get_profile(user=Depends(get_current_user)):
    jobs_count = (
        supabase_admin.table("transcription_jobs")
        .select("id", count="exact")
        .eq("user_id", user["_auth_user_id"])
        .execute()
    )
    return {
        "email": user["email"],
        "credits_minutes": user["credits_minutes"],
        "trial_used": user["trial_used"],
        "jobs_count": jobs_count.count or 0,
    }


@router.get("/jobs")
async def get_jobs(user=Depends(get_current_user)):
    result = (
        supabase_admin.table("transcription_jobs")
        .select("id, status, progress_pct, original_filename, duration_minutes, "
                "credits_used, model_used, created_at, completed_at")
        .eq("user_id", user["_auth_user_id"])
        .order("created_at", desc=True)
        .limit(50)  # bounded payload — this endpoint is polled frequently
        .execute()
    )
    return result.data
