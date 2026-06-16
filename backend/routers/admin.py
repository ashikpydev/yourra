"""
Admin panel: HTTP Basic Auth protected.

- /admin             summary stats
- /admin/users       all users + credit balances
- /admin/payments    pending bKash top-up requests -> approve/reject
- /admin/jobs        all transcription jobs
- /admin/requests    Phase 2 service requests
- /admin/activate    manual credit grant (fallback / adjustments)
"""
import secrets
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from backend.auth import require_admin
from backend.config import settings
from backend.database import supabase_admin, supabase_auth
from backend.services import mailer

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])
templates = Jinja2Templates(directory="backend/templates")


@router.get("")
async def admin_index(request: Request):
    users = supabase_admin.table("user_profiles").select("id", count="exact").execute()
    jobs = supabase_admin.table("transcription_jobs").select("id", count="exact").execute()

    today = datetime.now(timezone.utc).date().isoformat()
    jobs_today = (
        supabase_admin.table("transcription_jobs")
        .select("duration_minutes")
        .gte("created_at", today)
        .execute()
    )
    minutes_today = sum(r["duration_minutes"] or 0 for r in jobs_today.data)

    pending_payments = (
        supabase_admin.table("pending_payments").select("id", count="exact").eq("status", "pending").execute()
    )
    new_requests = (
        supabase_admin.table("service_requests").select("id", count="exact").eq("status", "new").execute()
    )

    return templates.TemplateResponse(
        "admin/index.html",
        {
            "request": request,
            "total_users": users.count or 0,
            "total_jobs": jobs.count or 0,
            "minutes_today": minutes_today,
            "pending_payments": pending_payments.count or 0,
            "new_requests": new_requests.count or 0,
        },
    )


@router.get("/users")
async def admin_users(request: Request):
    users = (
        supabase_admin.table("user_profiles")
        .select("email, credits_minutes, is_active, created_at")
        .order("created_at", desc=True)
        .execute()
    )
    return templates.TemplateResponse("admin/users.html", {"request": request, "users": users.data})


@router.post("/users/add")
async def admin_add_user(email: str = Form(...), minutes: int = Form(0)):
    """Create a brand-new user account, grant initial minutes, and email them
    their login. (To top up an EXISTING user, use 'Manually activate credits'.)"""
    email = email.strip().lower()
    password = secrets.token_urlsafe(9)
    try:
        if settings.LOCAL_MODE:
            result = supabase_auth.auth.sign_up({"email": email, "password": password})
        else:
            # Production: create an already-confirmed account (no verification email needed).
            # admin.create_user uses the service-role admin endpoint and does NOT
            # set a user session, so it's safe on supabase_admin.
            result = supabase_admin.auth.admin.create_user(
                {"email": email, "password": password, "email_confirm": True}
            )
    except Exception:
        return RedirectResponse(url="/admin/users?msg=User%20may%20already%20exist", status_code=303)

    uid = getattr(getattr(result, "user", None), "id", None)
    if not uid:
        return RedirectResponse(url="/admin/users?msg=Could%20not%20create%20user", status_code=303)

    supabase_admin.table("user_profiles").insert(
        {"id": uid, "email": email, "credits_minutes": int(minutes or 0),
         "trial_used": True, "is_active": 1}
    ).execute()
    if minutes:
        supabase_admin.table("credit_transactions").insert(
            {"user_id": uid, "minutes_added": int(minutes), "transaction_type": "manual_bkash",
             "notes": "Admin created account", "activated_by": "admin"}
        ).execute()

    login_url = settings.APP_BASE_URL.rstrip("/") + "/login"
    body = (
        f"Hello,\n\nAn account has been created for you on YourRA.\n\n"
        f"Login page: {login_url}\nEmail: {email}\nTemporary password: {password}\n\n"
        f"Please log in and keep this password safe.\n\nYourRA"
    )
    sent = mailer.send_email(email, "Your YourRA account is ready", body)
    note = "User created and emailed" if sent else "User created (email not configured, password: %s)" % password
    return RedirectResponse(url=f"/admin/users?msg={note.replace(' ', '%20')}", status_code=303)


@router.post("/users/pause")
async def admin_pause_user(email: str = Form(...)):
    supabase_admin.table("user_profiles").update({"is_active": 0}).eq("email", email).execute()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/unpause")
async def admin_unpause_user(email: str = Form(...)):
    supabase_admin.table("user_profiles").update({"is_active": 1}).eq("email", email).execute()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/delete")
async def admin_delete_user(email: str = Form(...)):
    prof = supabase_admin.table("user_profiles").select("id").eq("email", email).execute()
    if prof.data:
        uid = prof.data[0]["id"]
        for tbl, col in [
            ("transcription_jobs", "user_id"), ("pending_payments", "user_id"),
            ("credit_transactions", "user_id"), ("user_profiles", "id"),
            ("auth_users", "id"), ("sessions", "user_id"),
        ]:
            try:
                supabase_admin.table(tbl).delete().eq(col, uid).execute()
            except Exception:
                pass
        try:
            supabase_admin.auth.admin.delete_user(uid)  # Supabase only; ignored locally
        except Exception:
            pass
    return RedirectResponse(url="/admin/users", status_code=303)


@router.get("/payments")
async def admin_payments(request: Request):
    payments = (
        supabase_admin.table("pending_payments")
        .select("id, user_id, bundle_name, bundle_minutes, bundle_price_bdt, bkash_trx_id, status, created_at")
        .order("created_at", desc=True)
        .execute()
    )

    # Attach user email for display
    rows = []
    for p in payments.data:
        profile = (
            supabase_admin.table("user_profiles").select("email").eq("id", p["user_id"]).execute()
        )
        p["email"] = profile.data[0]["email"] if profile.data else "unknown"
        rows.append(p)

    return templates.TemplateResponse("admin/payments.html", {"request": request, "payments": rows})


@router.post("/payments/{payment_id}/approve")
async def approve_payment(payment_id: str):
    payment = (
        supabase_admin.table("pending_payments").select("*").eq("id", payment_id).execute()
    )
    if not payment.data:
        return RedirectResponse(url="/admin/payments", status_code=303)

    p = payment.data[0]
    if p["status"] != "pending":
        return RedirectResponse(url="/admin/payments", status_code=303)

    # Add minutes to user's balance
    profile = supabase_admin.table("user_profiles").select("credits_minutes").eq("id", p["user_id"]).execute()
    current = profile.data[0]["credits_minutes"] if profile.data else 0
    supabase_admin.table("user_profiles").update(
        {"credits_minutes": current + p["bundle_minutes"]}
    ).eq("id", p["user_id"]).execute()

    # Log transaction
    supabase_admin.table("credit_transactions").insert(
        {
            "user_id": p["user_id"],
            "minutes_added": p["bundle_minutes"],
            "transaction_type": "manual_bkash",
            "bkash_reference": p["bkash_trx_id"],
            "notes": f"{p['bundle_name']} bundle approved",
            "activated_by": "admin",
        }
    ).execute()

    # Mark payment approved
    supabase_admin.table("pending_payments").update(
        {"status": "approved", "resolved_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", payment_id).execute()

    return RedirectResponse(url="/admin/payments", status_code=303)


@router.post("/payments/{payment_id}/reject")
async def reject_payment(payment_id: str, admin_notes: str = Form("")):
    supabase_admin.table("pending_payments").update(
        {
            "status": "rejected",
            "admin_notes": admin_notes,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", payment_id).execute()
    return RedirectResponse(url="/admin/payments", status_code=303)


@router.get("/jobs")
async def admin_jobs(request: Request):
    jobs = (
        supabase_admin.table("transcription_jobs")
        .select("id, user_id, original_filename, status, duration_minutes, "
                "credits_used, model_used, created_at")
        .order("created_at", desc=True)
        .limit(200)
        .execute()
    )

    rows = []
    for j in jobs.data:
        profile = supabase_admin.table("user_profiles").select("email").eq("id", j["user_id"]).execute()
        j["email"] = profile.data[0]["email"] if profile.data else "unknown"
        rows.append(j)

    return templates.TemplateResponse("admin/jobs.html", {"request": request, "jobs": rows})


@router.get("/requests")
async def admin_requests(request: Request):
    requests_ = (
        supabase_admin.table("service_requests")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return templates.TemplateResponse("admin/requests.html", {"request": request, "requests": requests_.data})


@router.get("/trials")
async def admin_trials(request: Request):
    rows = (
        supabase_admin.table("trial_requests")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return templates.TemplateResponse("admin/trials.html", {"request": request, "trials": rows.data})


@router.post("/requests/{request_id}/update")
async def update_request(request_id: str, status: str = Form(...), quoted_price: str = Form(""), admin_notes: str = Form("")):
    supabase_admin.table("service_requests").update(
        {"status": status, "quoted_price": quoted_price, "admin_notes": admin_notes}
    ).eq("id", request_id).execute()
    return RedirectResponse(url="/admin/requests", status_code=303)


@router.post("/activate")
async def manual_activate(email: str = Form(...), minutes: int = Form(...), bkash_ref: str = Form(""), notes: str = Form("")):
    """Fallback: manually grant credits to a user by email (e.g., for
    institutional/custom arrangements outside the standard bundles)."""
    profile = supabase_admin.table("user_profiles").select("id, credits_minutes").eq("email", email).execute()
    if not profile.data:
        return RedirectResponse(url="/admin/users", status_code=303)

    p = profile.data[0]
    supabase_admin.table("user_profiles").update(
        {"credits_minutes": p["credits_minutes"] + minutes}
    ).eq("id", p["id"]).execute()

    supabase_admin.table("credit_transactions").insert(
        {
            "user_id": p["id"],
            "minutes_added": minutes,
            "transaction_type": "manual_bkash",
            "bkash_reference": bkash_ref,
            "notes": notes,
            "activated_by": "admin",
        }
    ).execute()

    return RedirectResponse(url="/admin/users", status_code=303)
