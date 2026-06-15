"""
Auth routes: signup, login, logout.
"""
from fastapi import APIRouter, Request, Response, Form, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse

from backend.config import settings
from backend.database import supabase_admin
from backend.services.trial import is_disposable_email

router = APIRouter(tags=["auth"])

COOKIE_NAME = "sb_access_token"


@router.post("/signup")
async def signup(
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(""),
    organization: str = Form(""),
):
    if await is_disposable_email(email):
        raise HTTPException(status_code=400, detail="Please use a permanent email address.")

    try:
        result = supabase_admin.auth.sign_up({"email": email, "password": password})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if result.user is None:
        raise HTTPException(status_code=400, detail="Signup failed. Please try again.")

    # Create the profile now so we can store the name / organization.
    uid = result.user.id
    try:
        existing = supabase_admin.table("user_profiles").select("id").eq("id", uid).execute()
        if not existing.data:
            supabase_admin.table("user_profiles").insert({
                "id": uid,
                "email": email.strip().lower(),
                "full_name": full_name.strip() or None,
                "organization": organization.strip() or None,
                "credits_minutes": 0,
                "trial_used": True,
                "is_active": 1,
            }).execute()
    except Exception:
        pass

    if settings.LOCAL_MODE:
        return {"message": "Account created. You can log in now."}
    return {"message": "Account created. Please check your email to verify your account, then log in."}


@router.post("/login")
async def login(email: str = Form(...), password: str = Form(...)):
    try:
        result = supabase_admin.auth.sign_in_with_password({"email": email, "password": password})
    except Exception:
        raise HTTPException(status_code=401, detail="Wrong email or password.")

    if not result.session:
        raise HTTPException(status_code=401, detail="Wrong email or password, or email not verified.")

    access_token = result.session.access_token
    user_id = result.user.id

    existing = supabase_admin.table("user_profiles").select("*").eq("id", user_id).execute()
    if not existing.data:
        supabase_admin.table("user_profiles").insert(
            {"id": user_id, "email": email, "credits_minutes": 0, "trial_used": True, "is_active": 1}
        ).execute()
    elif existing.data[0].get("is_active") == 0:
        raise HTTPException(status_code=403, detail="Your account is paused. Please contact support.")

    resp = JSONResponse({"ok": True})
    resp.set_cookie(
        key=COOKIE_NAME, value=access_token, httponly=True,
        secure=settings.COOKIE_SECURE, samesite="lax", max_age=604800,
    )
    return resp


@router.post("/logout")
async def logout():
    redirect = RedirectResponse(url="/login", status_code=303)
    redirect.delete_cookie(COOKIE_NAME)
    return redirect
