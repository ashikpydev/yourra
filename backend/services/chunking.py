"""
Audio chunking service.

Splits a long audio file into ~10-minute chunks, cutting at silence so
sentences are not broken mid-word.  Uses ffmpeg subprocesses for all
heavy work so the full file is NEVER loaded into Python RAM — only one
small chunk is in memory at a time.  This is the main defence against
Railway OOM on large uploads.

Requires ffmpeg + ffprobe to be on PATH (Railway/nixpacks installs them
automatically when ffmpeg is in nixpacks.toml).
"""
import os
import re
import subprocess

from backend.config import settings


def get_audio_duration_seconds(path: str) -> float:
    """Return audio duration using ffprobe — zero RAM overhead."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def _find_silence_cut(input_path: str, start: float, end: float) -> float | None:
    """Use ffmpeg silencedetect filter to find the midpoint of the first
    silence in [start, end].  Returns an absolute timestamp (seconds) or
    None if no silence is found."""
    duration = end - start
    thresh_db = settings.SILENCE_THRESH_DBFS
    min_silence_s = settings.MIN_SILENCE_LEN_MS / 1000.0

    result = subprocess.run(
        [
            "ffmpeg",
            "-ss", str(start), "-t", str(duration),
            "-i", input_path,
            "-af", f"silencedetect=noise={thresh_db}dB:d={min_silence_s}",
            "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )

    silence_starts = [float(m) for m in re.findall(r"silence_start: ([\d.]+)", result.stderr)]
    silence_ends   = [float(m) for m in re.findall(r"silence_end: ([\d.]+)",   result.stderr)]

    if not silence_starts:
        return None

    s = silence_starts[0]
    e = silence_ends[0] if silence_ends else s + min_silence_s
    return start + (s + e) / 2.0


def split_on_silence_chunks(
    input_path: str,
    output_dir: str,
    max_seconds: float | None = None,
) -> list[str]:
    """
    Split *input_path* into chunk files inside *output_dir* using ffmpeg.

    Each chunk is ~CHUNK_TARGET_SECONDS long, cut at the nearest silence
    gap so speech is not broken.  If no silence is found within
    CHUNK_HARD_MAX_SECONDS the cut is made at the hard limit.

    If *max_seconds* is given, only the first *max_seconds* are processed
    (used to cap a job to the user's available credit minutes).

    Returns a sorted list of chunk file paths.  No audio data is loaded
    into Python memory — ffmpeg streams directly from disk to disk.
    """
    os.makedirs(output_dir, exist_ok=True)

    full_duration = get_audio_duration_seconds(input_path)
    effective = min(full_duration, max_seconds) if max_seconds else full_duration

    target_s   = float(settings.CHUNK_TARGET_SECONDS)
    hard_max_s = float(settings.CHUNK_HARD_MAX_SECONDS)

    chunk_paths: list[str] = []
    idx = 1
    pos = 0.0

    while pos < effective - 0.1:
        remaining = effective - pos
        if remaining <= target_s:
            end = effective
        else:
            search_start = pos + target_s
            search_end   = min(pos + hard_max_s, effective)
            cut = _find_silence_cut(input_path, search_start, search_end)
            end = cut if cut else search_end

        out_path = os.path.join(output_dir, f"chunk_{idx:03d}.mp3")
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", str(pos), "-to", str(end),
                "-i", input_path,
                "-acodec", "libmp3lame", "-q:a", "4",
                out_path,
            ],
            capture_output=True,
            check=True,
        )
        chunk_paths.append(out_path)
        pos = end
        idx += 1

    # Safety: if nothing was produced (very short audio), encode whole file
    if not chunk_paths:
        out_path = os.path.join(output_dir, "chunk_001.mp3")
        subprocess.run(
            ["ffmpeg", "-y", "-i", input_path, "-acodec", "libmp3lame", "-q:a", "4", out_path],
            capture_output=True, check=True,
        )
        chunk_paths.append(out_path)

    return chunk_paths
