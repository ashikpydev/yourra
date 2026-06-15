"""
Auth routes: signup, login, logout.

Supabase handles password hashing, email verification emails, and session
tokens. This router is a thin wrapper that:
- Blocks disposable emails at signup
- Stores the resulting access token in an httpOnly cookie
- On first login, triggers the free-trial check (handled lazily in
  get_current_user / the dashboard, since trial eligibility also depends
  on the client's IP which is only known per-request)
"""
from fastapi import APIRouter, Request, Response, Form, HTTPException
from fastapi.responses import RedirectResponse

from backend.config import settings
from backend.database import supabase_admin
from backend.services.trial import is_disposable_email

router = APIRouter(tags=["auth"])

COOKIE_NAME = "sb_access_token"


@router.post("/signup")
async def signup(request: Request, email: str = Form(...), password: str = Form(...)):
    if await is_disposable_email(email):
        raise HTTPException(status_code=400, detail="Please use a permanent email address.")

    try:
        result = supabase_admin.auth.sign_up({"email": email, "password": password})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if result.user is None:
        raise HTTPException(status_code=400, detail="Signup failed. Please try again.")

    # Supabase sends a verification email automatically (if enabled in
    # project settings). The user_profiles row is created lazily on first
    # authenticated request (see backend/auth.py).
    if settings.LOCAL_MODE:
        return {"message": "Account created. You can log in now."}
    return {"message": "Account created. Please check your email to verify your account."}


@router.post("/login")
async def login(request: Request, response: Response, email: str = Form(...), password: str = Form(...)):
    try:
        result = supabase_admin.auth.sign_in_with_password({"email": email, "password": password})
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    if not result.session:
        raise HTTPException(status_code=401, detail="Invalid email or password, or email not verified.")

    access_token = result.session.access_token
    user_id = result.user.id

    # Ensure profile exists. New accounts start with 0 credits — access is
    # granted by an admin from the panel (no automatic free trial).
    existing = supabase_admin.table("user_profiles").select("*").eq("id", user_id).execute()
    if not existing.data:
        supabase_admin.table("user_profiles").insert(
            {"id": user_id, "email": email, "credits_minutes": 0, "trial_used": True}
        ).execute()
    elif existing.data[0].get("is_active") == 0:
        raise HTTPException(status_code=403, detail="Your account is paused. Please contact support.")

    redirect = RedirectResponse(url="/dashboard", status_code=303)
    redirect.set_cookie(
        key=COOKIE_NAME,
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    return redirect


@router.post("/logout")
async def logout():
    redirect = RedirectResponse(url="/login", status_code=303)
    redirect.delete_cookie(COOKIE_NAME)
    return redirect
