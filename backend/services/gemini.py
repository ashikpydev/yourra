"""
Gemini transcription service.

Each audio chunk is transcribed FULLY into a speaker-labelled, timestamped
Bangla verbatim transcript plus an English translation. Chunks are processed
in order (reliable, smooth progress, and each chunk sees the previous chunk's
tail so labels stay consistent). The chunk transcripts are concatenated
losslessly — no text is dropped between chunks.

Extras:
- Moderator vs Respondent labelling (the moderator asks the questions).
- Absolute timestamps roughly every 2 minutes, for cross-checking.
- extract_demographics(): pulls spoken respondent details from the transcript
  to help fill the demographic table.
"""
import asyncio
import json
import re
import time

import google.generativeai as genai

from backend.config import settings

genai.configure(api_key=settings.GOOGLE_API_KEY)

_PLACEHOLDER_HINTS = ("xxxx", "placeholder", "your_", "changeme", "paste", "here")


def _use_mock() -> bool:
    key = (settings.GOOGLE_API_KEY or "").strip().strip('"').strip("'")
    if len(key) < 20:
        return True
    low = key.lower()
    return any(h in low for h in _PLACEHOLDER_HINTS)


def _fmt_ts(seconds) -> str:
    s = int(seconds or 0)
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


PROMPT_TEMPLATE = """You are transcribing part {idx} of {total} of a Bangladeshi research interview or focus group discussion (FGD).

This segment begins at {start_ts} of the full recording.

Rules:
- Transcribe ALL speech fully and accurately in Bangla. Do NOT summarize, paraphrase, shorten, or skip anything; every sentence matters for research.
- The MODERATOR is the person asking the questions and guiding the discussion. Label their lines "Moderator:". Label the people answering "Respondent 1:", "Respondent 2:", and so on. Use the SAME label for the same voice.
- Put ONE speaker turn per line, and BEGIN EVERY line with an absolute timestamp in square brackets in [H:MM:SS] format marking when that turn is spoken, counting forward from {start_ts}. For example: "[{start_ts}] Moderator: ...". The timestamp must be as accurate as possible because it is used to play back the matching audio.
- Keep natural spoken Bangla verbatim, including fillers, repetitions, and any English words spoken.
- CONFIDENCE FLAGGING: when the audio is noisy, faint, or overlapping and you are NOT sure about a word or phrase, still write your best guess but wrap it in double parentheses like ((your best guess)) so a human can quickly find and verify it. Use [inaudible] only when nothing at all can be made out. Apply the SAME ((...)) flags in both the Bangla and the English versions.
{continuity}
Return your answer in EXACTLY this format and nothing else:
BANGLA:
<each line as: [H:MM:SS] Speaker: verbatim Bangla>

ENGLISH:
<the same lines translated to natural English, keeping the SAME [H:MM:SS] timestamp and the SAME speaker label at the start of each line>
"""

DEMO_PROMPT = """From the following research interview transcript, extract any demographic or survey details that are actually mentioned by the respondent or moderator. Return ONLY a compact JSON object with exactly these keys, using an empty string "" when something is not mentioned:
{{"survey_type":"","resp_name":"","resp_age":"","resp_sex":"","resp_education":"","resp_profession":"","resp_location":""}}

Transcript:
\"\"\"
{transcript}
\"\"\""""


def _continuity_hint(prev_tail: str) -> str:
    if not prev_tail.strip():
        return "- This is the first segment of the recording.\n"
    return (
        "- For speaker consistency, here are the last lines of the PREVIOUS segment "
        "(with their labels). Continue using the same labels for the same voices:\n"
        f'"""\n{prev_tail}\n"""\n'
    )


def _parse(text: str) -> tuple[str, str]:
    if not text:
        return "", ""
    bn = re.search(r"BANGLA:\s*(.*?)(?=ENGLISH:|\Z)", text, re.S | re.I)
    en = re.search(r"ENGLISH:\s*(.*)", text, re.S | re.I)
    bangla = bn.group(1).strip() if bn else text.strip()
    english = en.group(1).strip() if en else ""
    return bangla, english


def _upload_and_wait(path: str):
    f = genai.upload_file(path)
    waited = 0
    while f.state.name == "PROCESSING" and waited < 180:
        time.sleep(2)
        waited += 2
        f = genai.get_file(name=f.name)
    if f.state.name != "ACTIVE":
        raise RuntimeError(f"Gemini could not process the audio (state={f.state.name})")
    return f


def _transcribe_one(path, model_name, idx, total, start_ts, prev_tail):
    f = _upload_and_wait(path)
    try:
        model = genai.GenerativeModel(model_name)
        prompt = PROMPT_TEMPLATE.format(
            idx=idx, total=total, start_ts=start_ts, continuity=_continuity_hint(prev_tail)
        )
        resp = model.generate_content([prompt, f])
        return _parse(resp.text)
    finally:
        try:
            genai.delete_file(f.name)
        except Exception:
            pass


async def _transcribe_one_with_retry(path, model_name, idx, total, start_ts, prev_tail, attempts=3):
    last = None
    for attempt in range(1, attempts + 1):
        try:
            return await asyncio.to_thread(_transcribe_one, path, model_name, idx, total, start_ts, prev_tail)
        except Exception as e:
            last = e
            await asyncio.sleep(2 * attempt)
    raise RuntimeError(f"Segment {idx}/{total} failed after {attempts} attempts: {last}")


def _mock(chunk_paths, offsets):
    bn, en = [], []
    offs = offsets or [0] * len(chunk_paths)
    for i, _ in enumerate(chunk_paths, 1):
        base = offs[i - 1]
        ts1, ts2 = _fmt_ts(base), _fmt_ts(base + 6)
        bn.append(f"[{ts1}] Moderator: [লোকাল মক — অংশ {i}] আপনার নাম কী?\n[{ts2}] Respondent 1: আমার নাম ((রিনা))।")
        en.append(f"[{ts1}] Moderator: [Local mock — part {i}] What is your name?\n[{ts2}] Respondent 1: My name is ((Rina)).")
    return "\n\n".join(bn), "\n\n".join(en)


async def transcribe_all_chunks(chunk_paths, model_name, offsets=None, progress_cb=None):
    """Transcribe every chunk in order and concatenate losslessly.
    `offsets[i]` is the start time (seconds) of chunk i in the full recording,
    used for absolute timestamps. `progress_cb(done, total)` moves the UI bar."""
    total = len(chunk_paths)
    offsets = offsets or [0] * total
    if _use_mock():
        if progress_cb:
            progress_cb(total, total)
        return _mock(chunk_paths, offsets)

    bn_parts, en_parts = [], []
    prev_tail = ""
    for i, path in enumerate(chunk_paths, 1):
        start_ts = _fmt_ts(offsets[i - 1] if i - 1 < len(offsets) else 0)
        bn, en = await _transcribe_one_with_retry(path, model_name, i, total, start_ts, prev_tail)
        bn_parts.append(bn)
        en_parts.append(en)
        prev_tail = "\n".join((en or "").strip().splitlines()[-4:])
        if progress_cb:
            progress_cb(i, total)

    transcript_bn = "\n\n".join(p for p in bn_parts if p.strip())
    transcript_en = "\n\n".join(p for p in en_parts if p.strip())
    return transcript_bn, transcript_en


async def extract_demographics(transcript_text: str) -> dict:
    """Best-effort extraction of spoken respondent details from the transcript.
    Returns a dict with only the fields that were actually mentioned."""
    if _use_mock() or not (transcript_text or "").strip():
        return {}

    def _run():
        model = genai.GenerativeModel(settings.GEMINI_MODEL_FLASH)
        resp = model.generate_content(DEMO_PROMPT.format(transcript=transcript_text[:12000]))
        return resp.text

    try:
        text = await asyncio.to_thread(_run)
    except Exception:
        return {}

    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except Exception:
        return {}
    return {k: v.strip() for k, v in data.items() if isinstance(v, str) and v.strip()}
