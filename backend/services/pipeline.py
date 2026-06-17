"""
Main background pipeline orchestrator.

run_transcription_job() is invoked as a FastAPI BackgroundTask after
/api/upload creates the job record. It:

1. Downloads the original audio from R2 to /tmp
2. Splits it into silence-aware chunks
3. Transcribes all chunks in parallel (Flash or Pro depending on plan)
4. Stitches chunk boundaries
5. Stores the final transcript_bn / transcript_en on the job row
6. Deducts credits from the user
7. Cleans up local temp files
"""
import asyncio
import json
import math
import os
import shutil
import traceback
from datetime import datetime, timezone

from backend.config import settings
from backend.database import supabase_admin
from backend.services import chunking, gemini, storage

# Limit how many transcription jobs may run concurrently inside one process.
# This prevents multiple large audio files from being decoded into RAM at the
# same time (the primary cause of Railway OOM).  Set MAX_CONCURRENT_JOBS in
# your env to override; the Redis/RQ worker path is naturally limited to 1 job
# per worker process, so this mainly guards the in-process BackgroundTask path.
_MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "2"))
_JOB_SEMAPHORE: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _JOB_SEMAPHORE
    if _JOB_SEMAPHORE is None:
        _JOB_SEMAPHORE = asyncio.Semaphore(_MAX_CONCURRENT_JOBS)
    return _JOB_SEMAPHORE


class JobCancelled(Exception):
    """Raised inside the pipeline when a user cancels a job mid-flight."""


def _update_job(job_id: str, **fields):
    supabase_admin.table("transcription_jobs").update(fields).eq("id", job_id).execute()


def _job_status(job_id: str) -> str | None:
    try:
        row = (
            supabase_admin.table("transcription_jobs")
            .select("status").eq("id", job_id).execute().data
        )
        return row[0]["status"] if row else None
    except Exception:
        return None


def _raise_if_cancelled(job_id: str):
    if _job_status(job_id) == "cancelled":
        raise JobCancelled()


def _notify(job_id: str, user_id: str, ok: bool):
    """Email the owner that their transcript is ready (or that it failed).
    Best-effort: silently does nothing if SMTP isn't configured or anything
    goes wrong — it must never break the pipeline."""
    try:
        from backend.services import mailer

        prof = (
            supabase_admin.table("user_profiles")
            .select("email").eq("id", user_id).execute().data
        )
        if not prof or not prof[0].get("email"):
            return
        email = prof[0]["email"]

        jobrow = (
            supabase_admin.table("transcription_jobs")
            .select("original_filename").eq("id", job_id).execute().data
        )
        filename = (jobrow[0].get("original_filename") if jobrow else "") or "your audio"
        url = f"{settings.APP_BASE_URL.rstrip('/')}/jobs/{job_id}"

        if ok:
            subject = "✅ Your transcript is ready — YourRA"
            body = (
                f'Good news! Your transcription of "{filename}" is complete.\n\n'
                f"View, edit, and download it here:\n{url}\n\n"
                f"— YourRA"
            )
        else:
            subject = "Your transcription didn't finish — YourRA"
            body = (
                f'Unfortunately the transcription of "{filename}" did not complete.\n\n'
                f"You can retry it from your dashboard with one click — no re-upload "
                f"needed:\n{url}\n\n"
                f"If it keeps failing, please contact support.\n\n"
                f"— YourRA"
            )
        mailer.send_email(email, subject, body)
    except Exception:
        pass


def cleanup_expired_audio(user_id: str):
    """Delete audio originals older than R2_RETENTION_DAYS for one user, and
    null their key. Best-effort; safe to call on every dashboard load."""
    try:
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.R2_RETENTION_DAYS)
        rows = (
            supabase_admin.table("transcription_jobs")
            .select("id, audio_r2_key, completed_at")
            .eq("user_id", user_id)
            .execute()
        ).data or []
        for r in rows:
            key, comp = r.get("audio_r2_key"), r.get("completed_at")
            if not key or not comp:
                continue
            try:
                t = datetime.fromisoformat(str(comp).replace("Z", "+00:00"))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if t < cutoff:
                try:
                    storage.delete_object(key)
                except Exception:
                    pass
                _update_job(r["id"], audio_r2_key=None)
    except Exception:
        pass


def recover_stuck_jobs(user_id: str):
    """Mark a user's long-stalled jobs as 'failed' so they become retryable.

    On free hosting the web process can restart/sleep, which silently drops any
    in-process queued or running job — it would otherwise sit in 'processing' or
    'pending' forever with no way to recover. This is best-effort and cheap: it
    runs opportunistically on dashboard load (in a thread), scoped to one user,
    with generous thresholds so real long-running jobs are never touched.
    """
    try:
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        proc_cutoff = now - timedelta(minutes=settings.STUCK_JOB_MINUTES)
        pend_cutoff = now - timedelta(minutes=settings.STUCK_PENDING_MINUTES)

        rows = (
            supabase_admin.table("transcription_jobs")
            .select("id, status, created_at")
            .eq("user_id", user_id)
            .in_("status", ["pending", "processing", "merging"])
            .execute()
        ).data or []

        for r in rows:
            created = r.get("created_at")
            try:
                t = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            stuck = (
                (r["status"] in ("processing", "merging") and t < proc_cutoff)
                or (r["status"] == "pending" and t < pend_cutoff)
            )
            if stuck:
                _update_job(
                    r["id"],
                    status="failed",
                    error_message="This job stalled (the server likely restarted). "
                                  "Click Retry to run it again — no re-upload needed.",
                )
                print(f"[watchdog] recovered stuck job {r['id']} (was {r['status']})", flush=True)
    except Exception:
        pass


def run_job_sync(job_id: str, user_id: str, r2_key: str, model_name: str, max_minutes=None):
    """Synchronous entrypoint for the RQ worker (it runs sync functions)."""
    import asyncio
    asyncio.run(run_transcription_job(job_id, user_id, r2_key, model_name, max_minutes))


async def run_transcription_job(job_id: str, user_id: str, r2_key: str, model_name: str,
                                max_minutes: int | None = None):
    print(f"[pipeline] job {job_id} STARTING (model={model_name}, max_minutes={max_minutes})", flush=True)

    # Guard against processing when the user has no credits left (race condition
    # where two uploads cleared the balance simultaneously).
    try:
        profile_check = (
            supabase_admin.table("user_profiles")
            .select("credits_minutes")
            .eq("id", user_id)
            .execute()
            .data
        )
        if profile_check and profile_check[0]["credits_minutes"] <= 0:
            _update_job(job_id, status="failed",
                        error_message="No credits remaining. Please top up and re-upload.")
            print(f"[pipeline] job {job_id} aborted — user has 0 credits", flush=True)
            return
    except Exception:
        pass  # If the check fails, proceed and let the pipeline handle it normally

    # Semaphore: cap concurrent in-process jobs to avoid simultaneous large
    # RAM allocations crashing the server.
    async with _get_semaphore():
        await _run_transcription_job_inner(job_id, user_id, r2_key, model_name, max_minutes)


async def _run_transcription_job_inner(job_id: str, user_id: str, r2_key: str, model_name: str,
                                       max_minutes: int | None = None):
    job_dir = os.path.join(settings.TMP_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    local_input = os.path.join(job_dir, "input")
    chunks_dir = os.path.join(job_dir, "chunks")

    try:
        _raise_if_cancelled(job_id)
        _update_job(job_id, status="processing", progress_pct=10)

        # 1. Download original from R2 (in a thread so the web server stays free)
        await asyncio.to_thread(storage.download_to_path, r2_key, local_input)
        print(f"[pipeline] job {job_id} downloaded audio", flush=True)

        # 2. Determine duration + chunk.
        # Cap processing to the user's available minutes (max_minutes) so a
        # 5-minute trial only transcribes the first 5 minutes, and paying
        # users never get billed/processed beyond their balance.
        full_seconds = await asyncio.to_thread(chunking.get_audio_duration_seconds, local_input)
        cap_seconds = (max_minutes * 60) if max_minutes else None
        effective_seconds = min(full_seconds, cap_seconds) if cap_seconds else full_seconds
        duration_minutes = max(1, math.ceil(effective_seconds / 60))

        # CPU-heavy splitting runs in a thread so many jobs process concurrently.
        chunk_paths = await asyncio.to_thread(
            chunking.split_on_silence_chunks, local_input, chunks_dir, cap_seconds
        )
        total_chunks = len(chunk_paths)

        # Start time (seconds) of each chunk within the full recording, used for
        # absolute timestamps in the transcript.
        offsets, running = [], 0.0
        for cp in chunk_paths:
            offsets.append(running)
            running += await asyncio.to_thread(chunking.get_audio_duration_seconds, cp)

        print(f"[pipeline] job {job_id} split into {total_chunks} chunk(s); starting transcription", flush=True)
        _update_job(job_id, chunk_count=total_chunks, status="processing", progress_pct=15)

        # 3. Transcribe each chunk fully, in order, updating progress per chunk
        #    so the bar moves smoothly (15% -> ~95%). No lossy boundary stitch:
        #    chunk transcripts are concatenated as-is.
        def _progress(done, total):
            # Abort promptly if the user cancelled while chunks were processing.
            _raise_if_cancelled(job_id)
            pct = 15 + int((done / max(total, 1)) * 80)
            _update_job(job_id, status="processing", progress_pct=min(95, pct))

        transcript_bn, transcript_en = await gemini.transcribe_all_chunks(
            chunk_paths, model_name, offsets=offsets, progress_cb=_progress
        )
        print(f"[pipeline] job {job_id} transcription done ({len(transcript_bn)} bn chars)", flush=True)

        _update_job(job_id, status="merging", progress_pct=97)

        # 4. Auto-fill the demographic table from anything spoken in the audio,
        #    without overwriting details the user already entered.
        try:
            existing_meta = {}
            row = (
                supabase_admin.table("transcription_jobs")
                .select("respondent_meta").eq("id", job_id).execute()
            )
            if row.data and row.data[0].get("respondent_meta"):
                existing_meta = json.loads(row.data[0]["respondent_meta"])
            extracted = await gemini.extract_demographics(transcript_en or transcript_bn)
            merged = {**extracted, **existing_meta}  # user-entered values win
            merged = {k: v for k, v in merged.items() if v}
            if merged:
                _update_job(job_id, respondent_meta=json.dumps(merged, ensure_ascii=False))
        except Exception:
            pass

        # 5. Deduct credits
        profile = (
            supabase_admin.table("user_profiles")
            .select("credits_minutes")
            .eq("id", user_id)
            .execute()
            .data[0]
        )
        new_balance = max(0, profile["credits_minutes"] - duration_minutes)
        supabase_admin.table("user_profiles").update(
            {"credits_minutes": new_balance}
        ).eq("id", user_id).execute()

        # 6. Finalize job record
        _update_job(
            job_id,
            status="completed",
            progress_pct=100,
            duration_minutes=duration_minutes,
            credits_used=duration_minutes,
            transcript_bn=transcript_bn,
            transcript_en=transcript_en,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        print(f"[pipeline] job {job_id} COMPLETED", flush=True)

        # NOTE: the audio is intentionally KEPT (not deleted here) so the
        # researcher can click any transcript line to play it back and verify
        # accuracy. It is auto-deleted after R2_RETENTION_DAYS by
        # cleanup_expired_audio(), called opportunistically on dashboard load.

        # Let the user know their transcript is ready (they likely left the page).
        await asyncio.to_thread(_notify, job_id, user_id, True)

    except JobCancelled:
        # User cancelled mid-flight: mark cancelled, drop the audio, no credit
        # charge, no email. Not an error.
        print(f"[pipeline] job {job_id} CANCELLED by user", flush=True)
        try:
            storage.delete_object(r2_key)
        except Exception:
            pass
        _update_job(job_id, status="cancelled", audio_r2_key=None,
                    error_message="Cancelled by user before completion.")

    except Exception as e:
        print(f"[pipeline] job {job_id} FAILED: {e}", flush=True)
        print(traceback.format_exc(), flush=True)
        _update_job(
            job_id,
            status="failed",
            error_message=f"{e}\n{traceback.format_exc()[-1000:]}",
        )
        # Notify the owner so they can retry without watching the page.
        await asyncio.to_thread(_notify, job_id, user_id, False)
    finally:
        # 7. Cleanup local temp files (R2 original kept for retention window)
        shutil.rmtree(job_dir, ignore_errors=True)
