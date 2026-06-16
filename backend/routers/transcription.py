"""
Transcription routes: upload, status polling, result, download, and
manual bKash top-up submission.
"""
import io
import math
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse

from backend.auth import get_current_user
from backend.config import settings
from backend.database import supabase_admin
from backend.services import chunking, storage
from backend.services.pipeline import run_transcription_job

router = APIRouter(prefix="/api", tags=["transcription"])

ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".mp4"}

# Credit bundles, kept here so the upload form / admin reference stay in sync.
# All paid jobs run on Gemini Pro (best accuracy — quality first).
# Priced at a flat ~৳399/hour (Gemini Pro costs ~৳185/hour) ≈ 53% margin —
# still a fraction of human transcription (~৳3,000/hour for organizations).
BUNDLES = [
    {"name": "Mini", "minutes": 60, "price_bdt": 399, "model": "pro"},
    {"name": "Standard", "minutes": 180, "price_bdt": 1199, "model": "pro"},
    {"name": "Value", "minutes": 360, "price_bdt": 2399, "model": "pro"},
    {"name": "Pro Bundle", "minutes": 900, "price_bdt": 5999, "model": "pro"},
]

# Flat per-hour rate used for Custom orders (any number of hours).
PER_HOUR_BDT = 399


@router.post("/upload")
async def upload_audio(
    background_tasks: BackgroundTasks,
    audio: UploadFile = File(...),
    survey_type: str = Form(""),
    resp_name: str = Form(""),
    resp_age: str = Form(""),
    resp_sex: str = Form(""),
    resp_education: str = Form(""),
    resp_profession: str = Form(""),
    resp_location: str = Form(""),
    interviewer: str = Form(""),
    interview_date: str = Form(""),
    user=Depends(get_current_user),
):
    import json
    import os

    respondent_meta = {
        "survey_type": survey_type, "resp_name": resp_name, "resp_age": resp_age,
        "resp_sex": resp_sex, "resp_education": resp_education,
        "resp_profession": resp_profession, "resp_location": resp_location,
        "interviewer": interviewer, "interview_date": interview_date,
    }
    respondent_meta = {k: v for k, v in respondent_meta.items() if v}
    respondent_meta_json = json.dumps(respondent_meta, ensure_ascii=False) if respondent_meta else None

    ext = os.path.splitext(audio.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Check size against MAX_UPLOAD_MB (best-effort; Content-Length may be absent)
    contents = await audio.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_MB:
        raise HTTPException(status_code=400, detail=f"File too large (max {settings.MAX_UPLOAD_MB} MB).")

    if user["credits_minutes"] <= 0:
        raise HTTPException(
            status_code=402,
            detail="You have 0 transcription minutes left. Please top up to upload more.",
        )

    job_id = str(uuid.uuid4())
    r2_key = f"uploads/{user['_auth_user_id']}/{job_id}/{audio.filename}"

    # Stream to R2
    storage.upload_fileobj(io.BytesIO(contents), r2_key, content_type=audio.content_type)

    # Always use the best model (Gemini Pro) for every job.
    model_name = settings.GEMINI_MODEL_PRO
    model_key = "pro"

    job = (
        supabase_admin.table("transcription_jobs")
        .insert(
            {
                "id": job_id,
                "user_id": user["_auth_user_id"],
                "status": "pending",
                "progress_pct": 0,
                "original_filename": audio.filename,
                "audio_r2_key": r2_key,
                "model_used": model_key,
                "respondent_meta": respondent_meta_json,
            }
        )
        .execute()
    )

    # Prefer the Redis queue (separate worker) in production; fall back to an
    # in-process background task when no queue is configured.
    from backend.services import jobs
    queued = jobs.enqueue_transcription(
        job_id, user["_auth_user_id"], r2_key, model_name, user["credits_minutes"]
    )
    print(f"[upload] job {job_id} created; queued_to_redis={queued}", flush=True)
    if not queued:
        background_tasks.add_task(
            run_transcription_job, job_id, user["_auth_user_id"], r2_key, model_name,
            user["credits_minutes"],
        )

    return {"job_id": job_id}


@router.get("/status/{job_id}")
async def get_status(job_id: str, user=Depends(get_current_user)):
    result = (
        supabase_admin.table("transcription_jobs")
        .select("status, progress_pct, error_message")
        .eq("id", job_id)
        .eq("user_id", user["_auth_user_id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Job not found")
    return result.data[0]


@router.get("/result/{job_id}")
async def get_result(job_id: str, user=Depends(get_current_user)):
    result = (
        supabase_admin.table("transcription_jobs")
        .select("transcript_bn, transcript_en, duration_minutes, credits_used, "
                "model_used, status, original_filename")
        .eq("id", job_id)
        .eq("user_id", user["_auth_user_id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Job not found")

    row = result.data[0]
    if row["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Job is not completed yet (status: {row['status']})")
    return row


@router.get("/audio/{job_id}")
async def get_audio(job_id: str, user=Depends(get_current_user)):
    """Stream the original audio back to its owner so the result page can play
    it from any transcript timestamp. Local mode serves the file directly (with
    range/seek support); production redirects to a short-lived signed R2 URL."""
    import mimetypes
    import os

    result = (
        supabase_admin.table("transcription_jobs")
        .select("audio_r2_key, original_filename")
        .eq("id", job_id)
        .eq("user_id", user["_auth_user_id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Job not found")

    key = result.data[0].get("audio_r2_key")
    if not key or not storage.object_exists(key):
        raise HTTPException(status_code=404, detail="Audio is no longer available for this job.")

    media_type = mimetypes.guess_type(result.data[0].get("original_filename") or key)[0] or "audio/mpeg"

    if settings.LOCAL_MODE:
        path = storage.local_full_path(key)
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Audio is no longer available for this job.")
        return FileResponse(path, media_type=media_type)

    return RedirectResponse(storage.presigned_get_url(key, expires=3600))


@router.post("/transcript/{job_id}")
async def save_transcript(
    job_id: str,
    transcript_bn: str = Form(""),
    transcript_en: str = Form(""),
    user=Depends(get_current_user),
):
    """Save the researcher's edited transcript (Bangla + English). Owner-checked.
    Editing keeps the [H:MM:SS] line prefixes so click-to-play keeps working; the
    Word export strips them for the clean final document."""
    result = (
        supabase_admin.table("transcription_jobs")
        .select("id")
        .eq("id", job_id)
        .eq("user_id", user["_auth_user_id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Job not found")

    supabase_admin.table("transcription_jobs").update(
        {"transcript_bn": transcript_bn, "transcript_en": transcript_en}
    ).eq("id", job_id).eq("user_id", user["_auth_user_id"]).execute()
    return {"ok": True}


@router.get("/download/{job_id}/{lang}")
async def download_transcript(job_id: str, lang: str, user=Depends(get_current_user)):
    if lang not in ("bn", "en", "combined", "docx"):
        raise HTTPException(status_code=400, detail="lang must be 'bn', 'en', 'combined', or 'docx'")

    result = (
        supabase_admin.table("transcription_jobs")
        .select("transcript_bn, transcript_en, status, original_filename, "
                "duration_minutes, model_used, respondent_meta")
        .eq("id", job_id)
        .eq("user_id", user["_auth_user_id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Job not found")

    row = result.data[0]
    if row["status"] != "completed":
        raise HTTPException(status_code=409, detail="Job is not completed yet")

    if lang == "docx":
        from backend.services import docgen
        data = docgen.build_transcript_docx(row)
        return StreamingResponse(
            io.BytesIO(data),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": "attachment; filename=transcript.docx"},
        )

    if lang == "bn":
        content = row["transcript_bn"] or ""
        filename = "transcript_bangla.txt"
    elif lang == "en":
        content = row["transcript_en"] or ""
        filename = "transcript_english.txt"
    else:
        content = (
            "===== BANGLA =====\n\n" + (row["transcript_bn"] or "")
            + "\n\n===== ENGLISH =====\n\n" + (row["transcript_en"] or "")
        )
        filename = "transcript_combined.txt"

    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/bundles")
async def get_bundles():
    return BUNDLES


@router.post("/topup")
async def submit_topup(
    bundle_name: str = Form(...),
    bkash_trx_id: str = Form(...),
    custom_minutes: int = Form(0),
    user=Depends(get_current_user),
):
    if bundle_name == "Custom":
        minutes = int(custom_minutes or 0)
        if minutes < 60:
            raise HTTPException(status_code=400, detail="Custom orders start at 1 hour.")
        bundle = {
            "name": f"Custom ({minutes // 60} hr)",
            "minutes": minutes,
            "price_bdt": round(minutes / 60 * PER_HOUR_BDT),
        }
    else:
        bundle = next((b for b in BUNDLES if b["name"] == bundle_name), None)
        if not bundle:
            raise HTTPException(status_code=400, detail="Unknown bundle")

    supabase_admin.table("pending_payments").insert(
        {
            "user_id": user["_auth_user_id"],
            "bundle_name": bundle["name"],
            "bundle_minutes": bundle["minutes"],
            "bundle_price_bdt": bundle["price_bdt"],
            "bkash_trx_id": bkash_trx_id,
            "status": "pending",
        }
    ).execute()

    return {"message": "Thanks! We'll verify your payment and activate your credits shortly."}
