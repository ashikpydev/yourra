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
import json
import math
import os
import shutil
import traceback
from datetime import datetime, timezone

from backend.config import settings
from backend.database import supabase_admin
from backend.services import chunking, gemini, storage


def _update_job(job_id: str, **fields):
    supabase_admin.table("transcription_jobs").update(fields).eq("id", job_id).execute()


def run_job_sync(job_id: str, user_id: str, r2_key: str, model_name: str, max_minutes=None):
    """Synchronous entrypoint for the RQ worker (it runs sync functions)."""
    import asyncio
    asyncio.run(run_transcription_job(job_id, user_id, r2_key, model_name, max_minutes))


async def run_transcription_job(job_id: str, user_id: str, r2_key: str, model_name: str,
                                max_minutes: int | None = None):
    print(f"[pipeline] job {job_id} STARTING (model={model_name}, max_minutes={max_minutes})", flush=True)
    job_dir = os.path.join(settings.TMP_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    local_input = os.path.join(job_dir, "input")
    chunks_dir = os.path.join(job_dir, "chunks")

    try:
        _update_job(job_id, status="processing", progress_pct=10)

        # 1. Download original from R2
        storage.download_to_path(r2_key, local_input)
        print(f"[pipeline] job {job_id} downloaded audio", flush=True)

        # 2. Determine duration + chunk.
        # Cap processing to the user's available minutes (max_minutes) so a
        # 5-minute trial only transcribes the first 5 minutes, and paying
        # users never get billed/processed beyond their balance.
        full_seconds = chunking.get_audio_duration_seconds(local_input)
        cap_seconds = (max_minutes * 60) if max_minutes else None
        effective_seconds = min(full_seconds, cap_seconds) if cap_seconds else full_seconds
        duration_minutes = max(1, math.ceil(effective_seconds / 60))

        chunk_paths = chunking.split_on_silence_chunks(local_input, chunks_dir, max_seconds=cap_seconds)
        total_chunks = len(chunk_paths)

        # Start time (seconds) of each chunk within the full recording, used for
        # absolute timestamps in the transcript.
        offsets, running = [], 0.0
        for cp in chunk_paths:
            offsets.append(running)
            running += chunking.get_audio_duration_seconds(cp)

        print(f"[pipeline] job {job_id} split into {total_chunks} chunk(s); starting transcription", flush=True)
        _update_job(job_id, chunk_count=total_chunks, status="processing", progress_pct=15)

        # 3. Transcribe each chunk fully, in order, updating progress per chunk
        #    so the bar moves smoothly (15% -> ~95%). No lossy boundary stitch:
        #    chunk transcripts are concatenated as-is.
        def _progress(done, total):
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

        # Free the stored audio now that the transcript is saved — keeps R2
        # storage near zero so you stay well within the free tier. (The
        # transcript is in the database; the original is on the user's device.)
        try:
            storage.delete_object(r2_key)
        except Exception:
            pass

    except Exception as e:
        print(f"[pipeline] job {job_id} FAILED: {e}", flush=True)
        print(traceback.format_exc(), flush=True)
        _update_job(
            job_id,
            status="failed",
            error_message=f"{e}\n{traceback.format_exc()[-1000:]}",
        )
    finally:
        # 7. Cleanup local temp files (R2 original kept for retention window)
        shutil.rmtree(job_dir, ignore_errors=True)
