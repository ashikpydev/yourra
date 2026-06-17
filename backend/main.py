"""
YourRA — FastAPI application entrypoint.

Mounts:
- /            marketing/landing + auth pages + dashboard (Jinja2 templates)
- /api/*       transcription, profile, bundles, topup (transcription.py, profile.py)
- /signup,/login,/logout   auth (auth_router.py)
- /admin/*     admin panel (HTTP Basic Auth) (admin.py)
"""
import uuid

from fastapi import FastAPI, Request, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.auth import ACCESS_COOKIE, REFRESH_COOKIE, get_current_user
from backend.config import settings
from backend.database import supabase_admin
from backend.routers import auth_router, profile, transcription, admin
from backend.services import storage

app = FastAPI(title="YourRA")

app.mount("/static", StaticFiles(directory="backend/static"), name="static")
templates = Jinja2Templates(directory="backend/templates")
# Make contact details available to every template (e.g. the WhatsApp button).
templates.env.globals["whatsapp_number"] = settings.WHATSAPP_NUMBER
templates.env.globals["bkash_number"] = settings.BKASH_NUMBER

app.include_router(auth_router.router)
app.include_router(profile.router)
app.include_router(transcription.router)
app.include_router(admin.router)


@app.middleware("http")
async def _refresh_session_cookies(request: Request, call_next):
    """If get_current_user renewed an expired access token during the request,
    write the new tokens back to the browser so the session stays alive."""
    response = await call_next(request)
    tokens = getattr(request.state, "refreshed_tokens", None)
    if tokens:
        access, refresh = tokens
        response.set_cookie(
            ACCESS_COOKIE, access, httponly=True,
            secure=settings.COOKIE_SECURE, samesite="lax", max_age=604800,
        )
        if refresh:
            response.set_cookie(
                REFRESH_COOKIE, refresh, httponly=True,
                secure=settings.COOKIE_SECURE, samesite="lax", max_age=2592000,
            )
    return response


async def get_optional_user(request: Request):
    try:
        return await get_current_user(request)
    except Exception:
        return None


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    user = await get_optional_user(request)
    if user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("landing.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = await get_optional_user(request)
    if user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    user = await get_optional_user(request)
    if user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("signup.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = await get_optional_user(request)
    if not user:
        # Session missing/expired and not refreshable — send to login, never
        # dump a raw JSON 401 to the browser.
        return RedirectResponse(url="/login")
    # Best-effort housekeeping for this user (fire-and-forget, off the request
    # path): clear expired review audio, and recover any jobs left stuck by a
    # server restart so they can be retried.
    try:
        import asyncio
        from backend.services import pipeline
        uid = user["_auth_user_id"]
        asyncio.create_task(asyncio.to_thread(pipeline.cleanup_expired_audio, uid))
        asyncio.create_task(asyncio.to_thread(pipeline.recover_stuck_jobs, uid))
    except Exception:
        pass
    jobs = (
        supabase_admin.table("transcription_jobs")
        .select("id, status, progress_pct, original_filename, duration_minutes, "
                "credits_used, model_used, created_at")
        .eq("user_id", user["_auth_user_id"])
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "jobs": jobs.data,
            "bundles": transcription.BUNDLES,
            "bkash_number": settings.BKASH_NUMBER,
            "whatsapp_number": settings.WHATSAPP_NUMBER,
            "max_upload_mb": settings.MAX_UPLOAD_MB,
        },
    )


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_result_page(request: Request, job_id: str):
    user = await get_optional_user(request)
    if not user:
        return RedirectResponse(url="/login")
    result = (
        supabase_admin.table("transcription_jobs")
        .select("*")
        .eq("id", job_id)
        .eq("user_id", user["_auth_user_id"])
        .execute()
    )
    job = result.data[0] if result.data else None
    return templates.TemplateResponse(
        "result.html",
        {
            "request": request, "user": user, "job": job, "job_id": job_id,
            "retention_days": settings.R2_RETENTION_DAYS,
        },
    )


@app.get("/pricing", response_class=HTMLResponse)
async def pricing(request: Request):
    user = await get_optional_user(request)
    return templates.TemplateResponse(
        "pricing.html",
        {"request": request, "user": user, "bundles": transcription.BUNDLES,
         "whatsapp_number": settings.WHATSAPP_NUMBER},
    )


@app.get("/services", response_class=HTMLResponse)
async def services_page(request: Request):
    user = await get_optional_user(request)
    return templates.TemplateResponse("services.html", {"request": request, "user": user})


@app.post("/services/request")
async def submit_service_request(
    service_type: str = Form(...),
    description: str = Form(""),
    estimated_size: str = Form(""),
    deadline: str = Form(""),
    contact_email: str = Form(...),
    contact_whatsapp: str = Form(""),
    attachment: UploadFile = File(None),
):
    attachment_key = None
    if attachment and attachment.filename:
        attachment_key = f"service_requests/{uuid.uuid4()}/{attachment.filename}"
        storage.upload_fileobj(attachment.file, attachment_key, content_type=attachment.content_type)

    supabase_admin.table("service_requests").insert(
        {
            "service_type": service_type,
            "description": description or None,
            "estimated_size": estimated_size or None,
            "deadline": deadline or None,
            "contact_email": contact_email,
            "contact_whatsapp": contact_whatsapp or None,
            "attachment_r2_key": attachment_key,
            "status": "new",
        }
    ).execute()

    return RedirectResponse(url="/services?submitted=1", status_code=303)


@app.get("/trial", response_class=HTMLResponse)
async def trial_page(request: Request):
    user = await get_optional_user(request)
    return templates.TemplateResponse("trial.html", {"request": request, "user": user})


@app.post("/trial/request")
async def submit_trial_request(
    full_name: str = Form(...),
    email: str = Form(...),
    organization: str = Form(""),
    purpose: str = Form(""),
):
    supabase_admin.table("trial_requests").insert(
        {
            "full_name": full_name,
            "email": email.strip().lower(),
            "organization": organization or None,
            "purpose": purpose or None,
            "status": "new",
        }
    ).execute()
    return RedirectResponse(url="/trial?submitted=1", status_code=303)


@app.get("/health")
async def health():
    return {"status": "ok"}
# end of YourRA application entrypoint
