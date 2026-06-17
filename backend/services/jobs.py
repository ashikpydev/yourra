"""
Optional Redis-backed job queue.

When REDIS_URL is configured, transcription jobs are enqueued and processed by a
separate worker process (see worker.py) — this scales independently of the web
app and survives deploys. When REDIS_URL is blank, the caller falls back to
in-process FastAPI BackgroundTasks (fine for local/low volume).
"""
from backend.config import settings

_QUEUE_NAME = "transcription"


def _get_queue():
    if not settings.REDIS_URL:
        return None
    from redis import Redis
    from rq import Queue

    return Queue(_QUEUE_NAME, connection=Redis.from_url(settings.REDIS_URL))


def enqueue_transcription(job_id, user_id, r2_key, model_name, max_minutes,
                          source_language="auto") -> bool:
    """Enqueue a transcription job. Returns True if it was queued, False if no
    queue is configured (caller should then run it in-process)."""
    q = _get_queue()
    if q is None:
        return False
    q.enqueue(
        "backend.services.pipeline.run_job_sync",
        job_id, user_id, r2_key, model_name, max_minutes, source_language,
        job_timeout=7200,  # up to 2 hours per job
    )
    return True
