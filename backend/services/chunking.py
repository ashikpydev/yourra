"""
Audio chunking service.

Splits a long audio file into ~8-minute chunks, cutting at silence so
sentences are not broken mid-word. If no silence is found within a
10-minute window, a hard cut is made at CHUNK_HARD_MAX_SECONDS.

Requires ffmpeg to be available on PATH (installed automatically by
Railway's nixpacks when pydub is in requirements.txt).
"""
import os
from pydub import AudioSegment
from pydub.silence import detect_silence

from backend.config import settings


def get_audio_duration_seconds(path: str) -> float:
    audio = AudioSegment.from_file(path)
    return len(audio) / 1000.0


def split_on_silence_chunks(input_path: str, output_dir: str, max_seconds: float | None = None) -> list[str]:
    """
    Split `input_path` into chunk files inside `output_dir`.
    Returns a sorted list of chunk file paths (chunk_001.mp3, chunk_002.mp3, ...).

    If `max_seconds` is given, only the first `max_seconds` of audio are
    processed (used to cap a job to the user's available credit minutes — e.g.
    a 5-minute free trial only transcribes the first 5 minutes).
    """
    os.makedirs(output_dir, exist_ok=True)

    audio = AudioSegment.from_file(input_path)
    total_ms = len(audio)

    if max_seconds is not None:
        cap_ms = int(max_seconds * 1000)
        if cap_ms > 0:
            total_ms = min(total_ms, cap_ms)
            audio = audio[:total_ms]

    target_ms = settings.CHUNK_TARGET_SECONDS * 1000
    hard_max_ms = settings.CHUNK_HARD_MAX_SECONDS * 1000

    chunk_paths = []
    chunk_index = 1
    pos = 0

    while pos < total_ms:
        # Default end point: target chunk length, or end of audio
        remaining = total_ms - pos
        if remaining <= target_ms:
            end = total_ms
        else:
            # Search for a silence gap between [pos + target_ms, pos + hard_max_ms]
            search_start = pos + target_ms
            search_end = min(pos + hard_max_ms, total_ms)

            window = audio[search_start:search_end]
            silences = detect_silence(
                window,
                min_silence_len=settings.MIN_SILENCE_LEN_MS,
                silence_thresh=settings.SILENCE_THRESH_DBFS,
            )

            if silences:
                # Cut at the midpoint of the first silence gap found
                silence_start, silence_end = silences[0]
                cut_point = (silence_start + silence_end) // 2
                end = search_start + cut_point
            else:
                # No silence found - hard cut at the max window
                end = search_end

        segment = audio[pos:end]
        out_path = os.path.join(output_dir, f"chunk_{chunk_index:03d}.mp3")
        segment.export(out_path, format="mp3")
        chunk_paths.append(out_path)

        pos = end
        chunk_index += 1

    return chunk_paths
