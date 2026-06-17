# YourRA production image.
# Python 3.12 (no audioop shim needed) with FFmpeg for audio chunking.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# FFmpeg is required for audio duration probing and silence-aware chunking.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY backend ./backend
COPY schema.sql ./schema.sql
COPY run.py worker.py ./

# Default data dir (mount a persistent volume here in LOCAL_MODE).
RUN mkdir -p /data
ENV LOCAL_DB_PATH=/data/yourra_local.db \
    LOCAL_STORAGE_DIR=/data/local_storage \
    TMP_DIR=/tmp/yourra

EXPOSE 8000

# Reads $PORT in Python (run.py) so we never depend on shell expansion.
CMD ["python", "run.py"]
