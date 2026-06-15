"""
Background transcription worker.

Run this as a SEPARATE process/service in production:
    python worker.py
It pulls transcription jobs off the Redis queue and processes them, so the web
app stays responsive and jobs survive web restarts. Requires REDIS_URL to be set.
"""
from redis import Redis
from rq import Queue, Worker

from backend.config import settings

if __name__ == "__main__":
    if not settings.REDIS_URL:
        raise SystemExit("REDIS_URL is not set — nothing for the worker to do.")
    conn = Redis.from_url(settings.REDIS_URL)
    queue = Queue("transcription", connection=conn)
    Worker([queue], connection=conn).work(with_scheduler=True)
