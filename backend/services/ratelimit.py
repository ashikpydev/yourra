"""
Tiny in-memory rate limiter.

Good enough for a single-process deployment (our case): a per-key sliding
window kept in a dict. Used to slow brute-force on login/signup. Not shared
across processes — if you scale to multiple web workers, move this to Redis.
"""
import time
from collections import defaultdict, deque

_buckets: dict[str, deque] = defaultdict(deque)


def too_many(key: str, max_hits: int, window_seconds: int) -> bool:
    """Record a hit for `key`; return True if it exceeds `max_hits` within the
    trailing `window_seconds`."""
    now = time.time()
    dq = _buckets[key]
    cutoff = now - window_seconds
    while dq and dq[0] < cutoff:
        dq.popleft()
    if len(dq) >= max_hits:
        return True
    dq.append(now)
    # Opportunistically drop empty buckets so the dict doesn't grow forever.
    if len(_buckets) > 10000:
        for k in [k for k, v in list(_buckets.items()) if not v]:
            _buckets.pop(k, None)
    return False
