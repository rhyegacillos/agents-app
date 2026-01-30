import asyncio
import os
import json
import re
import hashlib
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import AsyncGenerator, Dict, Any, Callable, Awaitable, Optional
from fastapi import Request

from openai import AsyncOpenAI
from .models import Visit
from .utils import generate_with_fallback, get_logger
from .utils.upstash_rest import get_upstash, UpstashError
from .utils.templates import get_template
from .utils.html_sections import ensure_html_summary, html_to_text
from .utils import guardrails as guardrails_util
from . import extraction_agent, coordinator_agent, memory_agent, research_agent, critic_agent, evidence_agent

logger = get_logger(__name__)

redis = get_upstash()

SUMMARY_CACHE: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
SUMMARY_CACHE_MAX = 10
MEMORY_DB_PATH = Path("data/memory_db.json")
SUMMARY_JOBS_MAX = 10
SUMMARY_JOBS_TTL_SECONDS = int(os.getenv("SUMMARY_JOBS_TTL_SECONDS", str(60 * 60 * 6)))
SUMMARY_JOBS_POLL_SECONDS = float(os.getenv("SUMMARY_JOBS_POLL_SECONDS", "0.5"))
SUMMARY_EVENTS_MAX = int(os.getenv("SUMMARY_EVENTS_MAX", "250"))  # keep last N events only
EVIDENCE_MAX_CHUNKS = int(os.getenv("EVIDENCE_MAX_CHUNKS", "25"))  # shrink evidence payload
EVIDENCE_MAX_CITATIONS = int(os.getenv("EVIDENCE_MAX_CITATIONS", "40"))
EVIDENCE_SNIPPET_MAX = int(os.getenv("EVIDENCE_SNIPPET_MAX", "180"))

SUMMARY_JOBS_BY_ID: Dict[str, "SummaryJob"] = {}
SUMMARY_JOBS_BY_KEY: Dict[str, "SummaryJob"] = {}
REGEN_MODELS = ["deepseek-chat"]

SSE_EVENT_RE = re.compile(r"(?m)^event:\s*([a-zA-Z0-9_:-]+)\s*$")

# Only persist events needed for resumability + UI rendering
_PERSIST_EVENTS = {
    "status",
    "metadata",
    "actions",
    "evidence_update",
    "summary",
    "error",
    "job",
}

class SummaryJob:
    def __init__(self, key: str, job_id: str):
        self.key = key
        self.job_id = job_id
        self.events: list[str] = []
        self.done = False
        self.error: str | None = None
        self.condition = asyncio.Condition()
        self.created_at = time.time()
        self.last_access = self.created_at
        self.task: asyncio.Task | None = None


def _upstash():
    return get_upstash()

def _upstash_enabled() -> bool:
    return _upstash() is not None

def _job_meta_key(job_id: str) -> str:
    return f"summary:job:{job_id}:meta"

def _job_events_key(job_id: str) -> str:
    return f"summary:job:{job_id}:events"

def _job_keymap_key(cache_key: str) -> str:
    # cache_key is already a sha256 hex string
    return f"summary:jobkey:{cache_key}"

MEDICATION_HINT_RE = re.compile(
    r"\b(?:mg|mcg|g|ml|units|tablet|tab|capsule|cap|injection|iv|po|bid|tid|qid|qd|prn|rx|prescribed|medication|medications)\b",
    re.IGNORECASE,
)
DOSAGE_RE = re.compile(r"\b\d+(?:\.\d+)?\s?(?:mg|mcg|g|ml|units)\b", re.IGNORECASE)
CONDITION_HINT_RE = re.compile(
    r"\b(?:diagnosis|diagnosed|dx|impression|assessment|condition|disease|syndrome|infection|hypertension|diabetes|asthma|pneumonia|cancer|fracture)\b",
    re.IGNORECASE,
)

BASE_SYSTEM_PROMPT = """
You are an expert Clinical Medical Scribe and Physician Assistant.
Your goal is to generate a professional, accurate, and concise clinical summary based ONLY on the provided doctor's notes, patient history, research findings, and ALL attached files (documents, audio transcripts, prescription images).

# CORE RESPONSIBILITIES
1. ACCURACY: Do not invent, hallucinate, or assume information not present in the source text. If a detail is missing, omit it or state "Not documented."
2. INTEGRATION: You must synthesize information from ALL sources. If a prescription image is provided, list its medications. If an audio transcript is provided, include its details. Do not ignore attachments.
3. PROFESSIONALISM: Use standard medical terminology (e.g., "patient reports" instead of "patient said"). Use abbreviations only if standard (e.g., HTN, DM2, BP).
4. SAFETY: Explicitly highlight any drug interactions or guideline warnings provided in the context.

# OUTPUT STRUCTURE
You must output strict HTML with exactly these three sections:

<section data-section="summary">
  <h3>Summary of visit for the doctor's records</h3>
  [Content: A comprehensive medical note. Include Subjective (HPI, ROS), Objective (Vitals, PE, Labs), Assessment (Diagnoses), and Plan (Treatment, Follow-up). Integrate safety/guideline notes here.]
</section>

<section data-section="next_steps">
  <h3>Next steps for the doctor</h3>
  <ul>
    <li>[Actionable item 1]</li>
    <li>[Actionable item 2]</li>
  </ul>
</section>

<section data-section="patient_email">
  <h3>Draft Email for Patient</h3>
  <p>[Patient-friendly language. 6th-grade reading level. Clear instructions. No medical jargon without explanation.]</p>
</section>

# CRITICAL INSTRUCTIONS
- Do not sign the email.
- Do not include text outside the sections.
- If Research/Guideline findings are provided, you MUST incorporate them into the 'Assessment' or 'Plan' as a "Clinical Safety Note" or "Guideline Note".
"""


def _build_system_prompt() -> str:
    guardrails = guardrails_util.get_guardrails()
    if not guardrails:
        return BASE_SYSTEM_PROMPT
    lines = "\n- ".join(guardrails)
    return f"{BASE_SYSTEM_PROMPT}\n\nFormat guardrails:\n- {lines}"

RESEARCH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_drug_interactions",
            "description": "Checks for potential interactions between a list of 2 or more medications.",
            "parameters": {
                "type": "object",
                "properties": {
                    "medications": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "A list of medication names to check.",
                    }
                },
                "required": ["medications"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_medical_guidelines",
            "description": "Finds guideline recommendations for a clinical condition.",
            "parameters": {
                "type": "object",
                "properties": {
                    "condition": {
                        "type": "string",
                        "description": "The condition to research.",
                    }
                },
                "required": ["condition"],
            },
        },
    }
]

COORDINATOR_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "extract_actions",
            "description": "Extracts structured next-step actions from a clinical summary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary_html": {
                        "type": "string",
                        "description": "The full HTML summary to analyze.",
                    }
                },
                "required": ["summary_html"],
            },
        },
    }
]

def summary_prompt_for(visit: Visit, context: dict) -> str:
    attachment_block = ""
    if context.get("attachments"):
        attachment_block = "\n\n" + "\n\n".join(
            f"{label}:\n{text}" for label, text in context["attachments"]
        )
    
    history_block = ""
    if context.get("patient_history"):
        history_block = f"\n\n{context['patient_history']}"

    research_block = _format_findings_block(
        "Safety Check / Research Findings",
        context.get("research_findings"),
    )

    guidelines_block = _format_findings_block(
        "Guideline Findings",
        context.get("guideline_findings"),
    )

    doctor_block = ""
    doctor_info = context.get("doctor_info") or {}
    doctor_name = (doctor_info.get("doctor_name") or "").strip()
    if doctor_name:
        doctor_block = f"\n\nAttending Physician: {doctor_name}"

    template = get_template(visit)

    return f"""Create the summary, next steps and draft email for:
Patient Name: {visit.patient_name}
Date of Visit: {visit.date_of_visit}
Notes:
{context["notes_text"]}{attachment_block}{history_block}{research_block}{guidelines_block}{doctor_block}

Template: {template["label"]}
{template["summary_html"]}
Follow the template exactly and do not add or remove headings.
If two or more medications are mentioned, call the check_drug_interactions tool with a list of medication names.
If a condition or diagnosis is mentioned, call search_medical_guidelines with the condition name.
After drafting the summary, call extract_actions with the full HTML summary.
If there are any safety findings, incorporate a 'Clinical Safety Note' into the 'Assessment' or 'Plan' section of your summary.
If there are guideline findings, incorporate a short 'Guideline Note' into the 'Assessment' or 'Plan' section.
If an attending physician is provided, include a line "Attending Physician: <name>" in the Summary section (sentence only, not a heading).
For the Next steps section, use a <ul> list with clear, actionable items.
For the patient email section, use short <p> paragraphs in patient-friendly language."""


def _format_findings_block(label: str, value: Any) -> str:
    if not value:
        return ""
    items = value if isinstance(value, list) else [value]
    lines = []
    for item in items:
        if isinstance(item, dict):
            text = item.get("summary") or item.get("text") or ""
        else:
            text = str(item)
        text = text.strip()
        if text:
            lines.append(text)
    if not lines:
        return ""
    formatted = "\n- ".join(lines)
    return f"\n\n{label}:\n- {formatted}"

def _strip_tool_call_artifacts(text: str) -> str:
    if not text:
        return ""
    # Match both ASCII '|' and fullwidth '｜'
    bar = r"[|｜]"
    # Remove DSML tool call blocks
    text = re.sub(
        rf"<{bar}DSML{bar}function_calls>.*?</{bar}DSML{bar}function_calls>",
        "",
        text,
        flags=re.DOTALL,
    )
    # Remove any remaining DSML tags
    text = re.sub(rf"<{bar}DSML{bar}.*?>", "", text, flags=re.DOTALL)
    return text.strip()



def correction_prompt_for(
    visit: Visit,
    context: dict,
    summary_html: str,
    review: Dict[str, Any],
) -> str:
    attachment_block = ""
    if context.get("attachments"):
        attachment_block = "\n\n" + "\n\n".join(
            f"{label}:\n{text}" for label, text in context["attachments"]
        )

    history_block = ""
    if context.get("patient_history"):
        history_block = f"\n\n{context['patient_history']}"

    research_block = _format_findings_block("Safety Check / Research Findings", context.get("research_findings"))
    guidelines_block = _format_findings_block("Guideline Findings", context.get("guideline_findings"))

    template = get_template(visit)
    issues = critic_agent.format_issue_lines(review)
    issues_text = "\n- ".join(issues) if issues else "No issues reported."

    return f"""Revise the clinical summary to fix the issues below.
Do not introduce new facts. Use only the provided source text.
Keep the exact HTML structure with three sections.

Issues to fix:
- {issues_text}

Current summary (HTML):
{summary_html}

Source notes:
{context["notes_text"]}{attachment_block}{history_block}{research_block}{guidelines_block}

Template: {template["label"]}
{template["summary_html"]}
Follow the template exactly and do not add or remove headings.
Return only the three HTML sections."""


def _has_medication_candidates(text: str) -> bool:
    if not text:
        return False
    if DOSAGE_RE.search(text):
        return True
    return bool(MEDICATION_HINT_RE.search(text))


def _has_condition_candidates(text: str) -> bool:
    if not text:
        return False
    return bool(CONDITION_HINT_RE.search(text))


def _memory_db_mtime() -> float:
    try:
        return MEMORY_DB_PATH.stat().st_mtime
    except FileNotFoundError:
        return 0.0


def _summary_cache_key(visit: Visit) -> str:
    payload = visit.model_dump()
    #payload["_memory_db_mtime"] = _memory_db_mtime()
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> Dict[str, Any] | None:
    cached = SUMMARY_CACHE.get(key)
    if cached:
        SUMMARY_CACHE.move_to_end(key)
    return cached


def _cache_set(key: str, value: Dict[str, Any]) -> None:
    SUMMARY_CACHE[key] = value
    SUMMARY_CACHE.move_to_end(key)
    while len(SUMMARY_CACHE) > SUMMARY_CACHE_MAX:
        SUMMARY_CACHE.popitem(last=False)

def _prune_jobs() -> None:
    now = time.time()
    stale_keys = [
        job_id
        for job_id, job in SUMMARY_JOBS_BY_ID.items()
        if job.done and (now - job.last_access) > SUMMARY_JOBS_TTL_SECONDS
    ]
    for job_id in stale_keys:
        job = SUMMARY_JOBS_BY_ID.pop(job_id, None)
        if job:
            SUMMARY_JOBS_BY_KEY.pop(job.key, None)
    if len(SUMMARY_JOBS_BY_ID) <= SUMMARY_JOBS_MAX:
        return
    # Drop oldest completed jobs if over capacity
    completed = sorted(
        (job for job in SUMMARY_JOBS_BY_ID.values() if job.done),
        key=lambda job: job.last_access,
    )
    while len(SUMMARY_JOBS_BY_ID) > SUMMARY_JOBS_MAX and completed:
        job = completed.pop(0)
        SUMMARY_JOBS_BY_ID.pop(job.job_id, None)
        SUMMARY_JOBS_BY_KEY.pop(job.key, None)

def _register_job(job: SummaryJob) -> None:
    SUMMARY_JOBS_BY_ID[job.job_id] = job
    SUMMARY_JOBS_BY_KEY[job.key] = job

def _get_job_by_id(job_id: str) -> SummaryJob | None:
    job = SUMMARY_JOBS_BY_ID.get(job_id)
    if job:
        job.last_access = time.time()
    return job

def _get_job_by_key(key: str) -> SummaryJob | None:
    job = SUMMARY_JOBS_BY_KEY.get(key)
    if job:
        job.last_access = time.time()
    return job

def _new_job_id() -> str:
    return uuid.uuid4().hex

async def _run_summary_job(job: SummaryJob, visit: Visit, client: AsyncOpenAI) -> None:
    """
    In-memory job runner (fallback when Upstash is not configured).
    """
    try:
        async for event in run_summary_pipeline(visit, client, request=None):
            async with job.condition:
                job.events.append(event)
                job.condition.notify_all()
    except Exception as exc:
        job.error = str(exc)
        logger.error(f"Summary job failed: {exc}")
    finally:
        async with job.condition:
            job.done = True
            job.condition.notify_all()

async def _run_summary_job_upstash(job_id: str, visit: Visit, client: AsyncOpenAI) -> None:
    """
    Upstash-backed job runner. Writes SSE chunks into a Redis list so any instance can stream them.
    """
    redis = _upstash()
    if redis is None:
        return

    meta_key = _job_meta_key(job_id)
    events_key = _job_events_key(job_id)
    now = time.time()

    async def _meta_set_done(done: bool, error: str | None = None) -> None:
        fields = ["updated_at", str(time.time()), "done", "1" if done else "0"]
        if error:
            fields += ["error", error]
        await redis.execute("HSET", meta_key, *fields)

    async def _emit(chunk: str) -> None:
        if not chunk or chunk.startswith(":"):
            return

        ev = _sse_event_name(chunk)
        if ev is None or ev not in _PERSIST_EVENTS:
            return

        await redis.execute("RPUSH", events_key, chunk)

        # FINAL FIX: cap list size using existing SUMMARY_EVENTS_MAX
        await redis.execute("LTRIM", events_key, str(-SUMMARY_EVENTS_MAX), "-1")

        await redis.execute("HINCRBY", meta_key, "event_count", "1")
        await redis.execute("HSET", meta_key, "updated_at", str(time.time()))

    try:
        # mark running
        await redis.execute("HSET", meta_key, "status", "running", "updated_at", str(now), "done", "0")
        async for event in run_summary_pipeline(visit, client, request=None):
            await _emit(event)
    except Exception as exc:
        err = str(exc)
        logger.error(f"Summary job failed: {exc}")
        await _meta_set_done(True, error=err)
        # also emit a final error event for clients
        try:
            await _emit(f"event: error\\ndata: {json.dumps({'error': err})}\\n\\n")
        except Exception:
            pass
    else:
        await _meta_set_done(True, error=None)
        await redis.execute("HSET", meta_key, "status", "done")


async def start_summary_job(visit: Visit, client: AsyncOpenAI) -> str:
    """
    Start (or reuse) a summary job.

    - If Upstash is configured, job state/events are persisted in Redis.
    - Otherwise, falls back to in-memory jobs.
    """
    if not _upstash_enabled():
        _prune_jobs()
        cache_key = _summary_cache_key(visit)
        cached = _cache_get(cache_key)
        existing = _get_job_by_key(cache_key)
        if existing and not existing.done:
            return existing.job_id
        job_id = _new_job_id()
        job = SummaryJob(cache_key, job_id)
        if cached:
            job.events = list(cached.get("events") or [])
            job.done = True
            _register_job(job)
            return job.job_id
        _register_job(job)
        job.task = asyncio.create_task(_run_summary_job(job, visit, client))
        return job.job_id

    redis = _upstash()
    assert redis is not None

    cache_key = _summary_cache_key(visit)
    keymap_key = _job_keymap_key(cache_key)

    # Reuse existing job for the same input if present
    existing_job_id = await redis.execute("GET", keymap_key)
    if existing_job_id:
        return str(existing_job_id)

    job_id = _new_job_id()

    # SET keymap NX to avoid races
    set_res = await redis.execute("SET", keymap_key, job_id, "NX", "EX", str(SUMMARY_JOBS_TTL_SECONDS))
    if set_res is None:
        # Someone else won; reuse theirs
        existing_job_id = await redis.execute("GET", keymap_key)
        if existing_job_id:
            return str(existing_job_id)

    meta_key = _job_meta_key(job_id)
    events_key = _job_events_key(job_id)

    now = str(time.time())
    await redis.execute(
        "HSET",
        meta_key,
        "key", cache_key,
        "status", "queued",
        "done", "0",
        "error", "",
        "event_count", "0",
        "created_at", now,
        "updated_at", now,
    )

    # TTL for job metadata + events list
    await redis.execute("EXPIRE", meta_key, str(SUMMARY_JOBS_TTL_SECONDS))
    await redis.execute("EXPIRE", events_key, str(SUMMARY_JOBS_TTL_SECONDS))

    asyncio.create_task(_run_summary_job_upstash(job_id, visit, client))
    return job_id

async def _stream_job_events(
    job: SummaryJob,
    request: Optional[Any] = None,
) -> AsyncGenerator[str, None]:
    idx = 0
    while True:
        if request is not None:
            try:
                if await request.is_disconnected():
                    return
            except Exception:
                pass
        async with job.condition:
            while idx >= len(job.events) and not job.done:
                await job.condition.wait()
            while idx < len(job.events):
                yield job.events[idx]
                idx += 1
            if job.done:
                return


async def _stream_job_events_upstash(
    job_id: str,
    request: Optional[Any] = None
) -> AsyncGenerator[str, None]:
    """
    Stream SSE event chunks for a job from Upstash Redis (REST).

    GOAL
    - Avoid aggressive polling (HMGET + LLEN every 0.5s).
    - Keep resumability intact (client can reconnect and continue from last idx).

    KEY IDEAS
    1) Do NOT call LLEN at all. It’s extra work and shows up as spam in your logs.
       Instead, rely on the meta field `event_count` that you already maintain via HINCRBY.
    2) Use adaptive backoff:
       - Poll fast while events are flowing.
       - Back off (poll slower) when idle.
       - Reset to fast polling immediately when new events appear.
    3) Only fetch new events using LRANGE(start=idx, end=event_count-1).
       That keeps bandwidth bounded and ensures reconnect works.

    WHAT THIS DOES NOT CHANGE
    - Restarting behavior/resume correctness:
      You still stream from Redis list + event_count; reconnect picks up where it left off.
    """

    redis = _upstash()
    if redis is None:
        return  # Upstash not configured

    meta_key = _job_meta_key(job_id)      # e.g. summary:job:<id>:meta
    events_key = _job_events_key(job_id)  # e.g. summary:job:<id>:events

    # idx = how many events we have already yielded to this client stream
    idx = 0

    # Base polling interval (fast mode) while job is active or just started.
    # This is your existing env var. Keep it low-ish (e.g. 0.25–0.75).
    base_sleep_s = float(os.getenv("SUMMARY_JOBS_POLL_SECONDS", "0.5"))

    # Maximum backoff interval when idle. This is new.
    # This is where you get “less polling” without hurting active streaming much.
    max_sleep_s = float(os.getenv("SUMMARY_JOBS_POLL_MAX_SECONDS", "5.0"))

    # Current sleep starts at base and grows when idle.
    sleep_s = base_sleep_s

    # Backoff multiplier. 1.6 is a typical compromise (fast ramp without exploding).
    backoff_mult = float(os.getenv("SUMMARY_JOBS_POLL_BACKOFF_MULT", "1.6"))

    # Optional: cap how long we keep streaming if job disappears (rare).
    # Not required; only if you want to prevent infinite loops on missing meta.
    # max_missing_meta_loops = int(os.getenv("SUMMARY_JOBS_META_MISS_MAX", "0"))

    while True:
        # If the HTTP client disconnected, stop immediately.
        # Prevents unnecessary Upstash queries after browser/tab close.
        if request is not None:
            try:
                if await request.is_disconnected():
                    return
            except Exception:
                # If request object doesn’t support is_disconnected in some context,
                # do not fail streaming; just continue.
                pass

        # Single meta call per poll. No LLEN.
        #
        # We rely on these meta fields being written by _run_summary_job_upstash:
        # - done: "0" or "1"
        # - event_count: integer count of persisted events
        # - error: optional error string
        meta = await redis.execute("HMGET", meta_key, "done", "event_count", "error")

        # Parse meta safely (Upstash returns list-like results)
        done = "0"
        event_count = 0
        error = ""

        if meta and len(meta) >= 1 and meta[0] is not None:
            done = str(meta[0])
        if meta and len(meta) >= 2 and meta[1] is not None:
            try:
                event_count = int(meta[1])
            except Exception:
                event_count = 0
        if meta and len(meta) >= 3 and meta[2] is not None:
            error = str(meta[2])

        # If new events exist since last yield, fetch only that range.
        # This keeps network + Redis load minimal.
        if idx < event_count:
            start = idx
            end = event_count - 1

            # Fetch new chunks only.
            # Each item is already a full SSE chunk string like:
            #   "event: status\ndata: ...\n\n"
            items = await redis.execute("LRANGE", events_key, str(start), str(end)) or []

            for item in items:
                yield str(item)

            # Advance idx so reconnect continues properly.
            idx = event_count

            # Reset backoff because we’re “active” again.
            sleep_s = base_sleep_s
            continue

        # No new events; if job is done, end the stream.
        if done == "1":
            # Optional safety: ensure client receives an error event if job ended in error
            # and the runner didn’t emit one for some reason.
            if error:
                yield f"event: error\ndata: {json.dumps({'error': error})}\n\n"
            return

        # Idle: wait, then back off.
        # This is where you reduce the aggressive HMGET spam in Upstash logs.
        await asyncio.sleep(sleep_s)

        # Increase sleep up to a cap (exponential-ish backoff).
        sleep_s = min(max_sleep_s, sleep_s * backoff_mult)


async def stream_summary_job(
    job_id: str,
    request: Optional[Any] = None,
) -> AsyncGenerator[str, None]:
    """
    Stream SSE chunks for a job.

    - Upstash configured: tail Redis list for job events (polling).
    - Otherwise: stream in-memory job events.
    """
    if _upstash_enabled():
        async for chunk in _stream_job_events_upstash(job_id, request=request):
            yield chunk
        return

    job = _get_job_by_id(job_id)
    if not job:
        return
    async for chunk in _stream_job_events(job, request=request):
        yield chunk

async def get_summary_job(job_id: str) -> Dict[str, Any] | SummaryJob | None:
    """
    Returns job metadata (Upstash) or SummaryJob (in-memory), or None if not found.
    """
    if _upstash_enabled():
        redis = _upstash()
        assert redis is not None
        meta_key = _job_meta_key(job_id)
        meta = await redis.execute("HGETALL", meta_key)
        if not meta:
            return None
        # Upstash returns flat list [k1,v1,k2,v2,...] for HGETALL
        if isinstance(meta, list):
            it = iter(meta)
            return {str(k): str(v) for k, v in zip(it, it)}
        if isinstance(meta, dict):
            return {str(k): str(v) for k, v in meta.items()}
        return {"raw": str(meta)}
    return _get_job_by_id(job_id)


def _normalize_notes_text(text: str) -> str:
    if not text:
        return ""
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned = []
    blank = False
    for line in lines:
        if not line.strip():
            if not blank:
                cleaned.append("")
                blank = True
            continue
        cleaned.append(line)
        blank = False
    return "\n".join(cleaned).strip()


def _format_evidence_text(evidence_map: Dict[str, Any]) -> str:
    if not evidence_map:
        return ""
    citations = evidence_map.get("citations") or []
    chunks = evidence_map.get("chunks") or []
    if not citations or not chunks:
        return ""
    chunk_lookup = {chunk.get("id"): chunk for chunk in chunks if chunk.get("id")}
    lines = ["Evidence Links:"]
    for item in citations:
        sentence = (item.get("sentence") or "").strip()
        if not sentence:
            continue
        lines.append(f"- {sentence}")
        snippets = item.get("snippets") or {}
        for chunk_id in item.get("chunk_ids") or []:
            chunk = chunk_lookup.get(chunk_id)
            if not chunk:
                continue
            source = chunk.get("source") or "Source"
            snippet = (snippets.get(chunk_id) or chunk.get("text") or "").strip()
            if len(snippet) > 140:
                snippet = snippet[:140] + "..."
            lines.append(f"  - {source}: {snippet}")
            for link in chunk.get("sources") or []:
                url = (link.get("url") or "").strip()
                if not url:
                    continue
                title = (link.get("title") or "").strip()
                if title:
                    lines.append(f"    - {title}: {url}")
                else:
                    lines.append(f"    - {url}")
    return "\n".join(lines).strip()

def _format_notes_text(context: Dict[str, Any]) -> str:
    notes_text = _normalize_notes_text(context.get("notes_text", ""))
    attachments = context.get("attachments") or []
    attachment_blocks = []
    for label, text in attachments:
        cleaned = _normalize_notes_text(text)
        if cleaned:
            attachment_blocks.append(f"{label}:\n{cleaned}")
    parts = []
    if notes_text:
        parts.append(f"Notes:\n{notes_text}")
    if attachment_blocks:
        parts.append("Attachments:\n" + "\n\n".join(attachment_blocks))
    return "\n\n".join(parts).strip()



async def _fill_doctor_info_from_summary(
    doctor_info: Dict[str, Any],
    summary_html: str,
    client: AsyncOpenAI,
) -> Dict[str, Any]:
    summary_text = html_to_text(summary_html)
    if not summary_text:
        return doctor_info
    try:
        extracted = await extraction_agent.extract_doctor_info(summary_text, client)
    except Exception as exc:
        logger.warning(f"Failed to extract doctor info from summary: {exc}")
        return doctor_info

    for key in ("doctor_name", "doctor_phone", "clinic_name", "doctor_email"):
        existing = (doctor_info.get(key) or "").strip()
        candidate = (extracted.get(key) or "").strip()
        if not existing and candidate:
            doctor_info[key] = candidate
            logger.info("Filled %s from summary text.", key)

    return doctor_info


async def generate_summary_stream(
    visit: Visit,
    context: Dict[str, Any],
    doctor_info: Dict[str, Any],
    client: AsyncOpenAI,
    should_abort: Optional[Callable[[], Awaitable[bool]]] = None,
) -> AsyncGenerator[str, None]:
    async def _abort_now(stage: str) -> bool:
        if should_abort and await should_abort():
            logger.info("Summary generation aborted: %s", stage)
            return True
        return False

    # Helper to run a task while yielding keep-alive comments
    async def run_with_keepalive(coro):
        task = asyncio.create_task(coro)
        while not task.done():
            await asyncio.sleep(2) # Ping every 2 seconds
            if not task.done():
                yield ": keep-alive\n\n"
        yield ": keep-alive\n\n"
        if task.exception():
            raise task.exception()
        yield task.result()

    if await _abort_now("before prompt assembly"):
        return
        
    yield "event: status\ndata: Analyzing consultation data...\n\n"
    
    user_prompt = summary_prompt_for(visit, context)
    system_prompt = _build_system_prompt()
    prompt = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    actions_from_tool = None
    try:
        if await _abort_now("before initial generation"):
            return
        tool_enabled = _has_medication_candidates(context.get("combined_text", ""))
        condition_enabled = _has_condition_candidates(context.get("combined_text", ""))
        research_tools: list[dict] = []
        if tool_enabled or condition_enabled:
            research_tools = RESEARCH_TOOLS
        tools = COORDINATOR_TOOL + research_tools
        
        # 1. Initial Generation with Keep-Alive
        response = None
        async for chunk in run_with_keepalive(
            generate_with_fallback(
                client=client,
                messages=prompt,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
                models=["deepseek-chat"],
            )
        ):
            if isinstance(chunk, str) and chunk.startswith(": keep-alive"):
                yield chunk
            else:
                response = chunk

        if await _abort_now("after initial generation"):
            return
        message = response.choices[0].message
        tool_calls = message.tool_calls
        if tool_calls:
            prompt.append(message)
            
            yield "event: status\ndata: Checking drug interactions and guidelines...\n\n"
            
            # Create parallel tasks for all tool calls
            tasks = []
            for tool_call in tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse arguments for tool {fn_name}.")
                    fn_args = {}

                if fn_name == "check_drug_interactions":
                    tasks.append(research_agent.check_drug_interactions(fn_args.get("medications", [])))
                elif fn_name == "search_medical_guidelines":
                    tasks.append(research_agent.search_medical_guidelines(fn_args.get("condition", "")))
                elif fn_name == "extract_actions":
                    tasks.append(coordinator_agent.extract_actions(fn_args.get("summary_html", ""), client))
                else:
                    tasks.append(asyncio.sleep(0, result=json.dumps({"error": f"Unknown tool {fn_name}"})))

            # 2. Execute tasks in parallel with Keep-Alive
            results = None
            async def _gather_research():
                return await asyncio.gather(*tasks, return_exceptions=True)
                
            async for chunk in run_with_keepalive(_gather_research()):
                if isinstance(chunk, str) and chunk.startswith(": keep-alive"):
                    yield chunk
                else:
                    results = chunk

            # Process results
            has_new_findings = False
            for i, result in enumerate(results):
                tool_call = tool_calls[i]
                fn_name = tool_call.function.name
                
                if isinstance(result, Exception):
                    logger.error(f"Tool call {fn_name} failed with exception: {result}")
                    tool_result = json.dumps({"error": str(result)})
                else:
                    if fn_name == "check_drug_interactions":
                        if result:
                            context["research_findings"] = result
                            has_new_findings = True
                        tool_result = json.dumps({"findings": result})
                    elif fn_name == "search_medical_guidelines":
                        if result:
                            context["guideline_findings"] = result
                            has_new_findings = True
                        tool_result = json.dumps({"guidelines": result})
                    elif fn_name == "extract_actions":
                        actions_from_tool = result
                        tool_result = json.dumps({"actions": actions_from_tool})
                    else:
                        tool_result = json.dumps(result)

                prompt.append(
                    {"role": "tool", "tool_call_id": tool_call.id, "content": tool_result}
                )

            # If new research was found, update the prompt with the new context
            if has_new_findings:
                prompt[1]["content"] = summary_prompt_for(visit, context)

            if await _abort_now("before post-tool generation"):
                return
            
            # 3. Post-tool Generation with Keep-Alive
            async for chunk in run_with_keepalive(
                generate_with_fallback(
                    client=client,
                    messages=prompt,
                    tools=tools,
                    tool_choice="none",
                    models=["deepseek-chat"],
                )
            ):
                if isinstance(chunk, str) and chunk.startswith(": keep-alive"):
                    yield chunk
                else:
                    response = chunk
            raw_text = response.choices[0].message.content or ""
        else:
            raw_text = message.content or ""
    except Exception as e:
        logger.error(f"Failed to generate summary: {e}")
        raw_text = "<p>Error generating summary. Please check logs.</p>"

    raw_text = _strip_tool_call_artifacts(raw_text)
    template = get_template(visit)
    # final_html = ensure_html_summary(raw_text, template)

    # FINALIZE once here before critic/other agents
    final_html = await finalize_summary_html(client, template, raw_text)

    if critic_agent.critic_enabled():
        if await _abort_now("before critic review"):
            return
            
        yield "event: status\ndata: Reviewing summary for clinical accuracy...\n\n"
        
        logger.info("Critic review starting.")
        critic_client = critic_agent.build_critic_client(client)
        
        # 4. Critic Review with Keep-Alive
        review = None
        async for chunk in run_with_keepalive(
            critic_agent.review_summary(
                summary_html=final_html,
                source_text=context.get("combined_text", ""),
                patient_history=context.get("patient_history", ""),
                research_findings=_format_findings_block("Research", context.get("research_findings")),
                guideline_findings=_format_findings_block("Guidelines", context.get("guideline_findings")),
                client=critic_client,
            )
        ):
            if isinstance(chunk, str) and chunk.startswith(": keep-alive"):
                yield chunk
            else:
                review = chunk

        await guardrails_util.record_critic_issues(review.get("issues", []), client)
        
        if critic_agent.review_requires_regen(review):
            logger.info("Critic review failed. Triggering Parallel Regeneration Tournament (N=3).")
            
            # 1. Prepare Prompt
            correction_prompt = correction_prompt_for(visit, context, final_html, review)
            
            # 2. Generate 3 Candidates in Parallel
            N_CANDIDATES = 3
            gen_tasks = []
            for _ in range(N_CANDIDATES):
                gen_tasks.append(
                    generate_with_fallback(
                        client=critic_client,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": correction_prompt},
                        ],
                        models=REGEN_MODELS,
                        temperature=0.7 # Slight variance for diversity
                    )
                )
            
            # 5. Tournament Generation with Keep-Alive
            gen_results = None
            async def _gather_gen():
                return await asyncio.gather(*gen_tasks, return_exceptions=True)

            async for chunk in run_with_keepalive(_gather_gen()):
                if isinstance(chunk, str) and chunk.startswith(": keep-alive"):
                    yield chunk
                else:
                    gen_results = chunk
            
            candidates = []
            for res in gen_results:
                if isinstance(res, Exception):
                    logger.warning(f"Tournament generation failed: {res}")
                    continue
                raw = res.choices[0].message.content or ""
                if raw.strip():
                    candidates.append(ensure_html_summary(raw, template))
            
            if not candidates:
                logger.error("All tournament generations failed. Keeping original draft.")
            else:
                # 3. Critique Candidates in Parallel
                logger.info(f"Tournament Phase 2: Critiquing {len(candidates)} candidates...")
                critique_tasks = []
                for cand in candidates:
                    critique_tasks.append(
                        critic_agent.review_summary(
                            summary_html=cand,
                            source_text=context.get("combined_text", ""),
                            patient_history=context.get("patient_history", ""),
                            research_findings=_format_findings_block("Research", context.get("research_findings")),
                            guideline_findings=_format_findings_block("Guidelines", context.get("guideline_findings")),
                            client=critic_client,
                        )
                    )
                
                # 6. Tournament Critique with Keep-Alive
                critique_results = None
                async def _gather_critique():
                    return await asyncio.gather(*critique_tasks, return_exceptions=True)

                async for chunk in run_with_keepalive(_gather_critique()):
                    if isinstance(chunk, str) and chunk.startswith(": keep-alive"):
                        yield chunk
                    else:
                        critique_results = chunk
                
                # 4. Pick Winner
                best_cand = None
                best_review = None
                best_score = -1.0
                
                for i, (cand, rev) in enumerate(zip(candidates, critique_results)):
                    if isinstance(rev, Exception):
                        logger.warning(f"Tournament critique {i} failed: {rev}")
                        continue
                    
                    score = rev.get("score", 0.0)
                    passed = not critic_agent.review_requires_regen(rev)
                    
                    logger.info(f"Candidate {i}: score={score}, passed={passed}")
                    
                    # Immediate winner if passes
                    if passed:
                        best_cand = cand
                        best_review = rev
                        logger.info(f"Candidate {i} is the winner (Passed).")
                        break
                    
                    # Track best failing candidate
                    if score > best_score:
                        best_score = score
                        best_cand = cand
                        best_review = rev
                
                # 5. Apply Result
                if best_cand:
                    final_html = best_cand
                    if best_review:
                        review = best_review # Update review state for final log/audit
                        await guardrails_util.record_critic_issues(review.get("issues", []), client)
                    logger.info(f"Tournament finished. Selected candidate with score={best_score if best_score > -1 else 'Pass'}")
                else:
                    logger.warning("Tournament produced no valid candidates. Keeping original.")

        logger.info("Critic review finished.")
        # Enforce strict 3-section HTML after any critic/tournament edits
        final_html = await finalize_summary_html(client, template, final_html)

    doctor_info = await _fill_doctor_info_from_summary(doctor_info, final_html, client)
    
    # --- Now that the summary is generated, do slower tasks ---
    
    # Coordinator Agent: Extract actions
    if await _abort_now("before action extraction"):
        return
        
    yield "event: status\ndata: Extracting next steps...\n\n"
    
    actions = actions_from_tool
    if actions is None:
        logger.info("Coordinator Agent: Manually extracting actions from final summary.")
        # 7. Action Extraction with Keep-Alive
        async for chunk in run_with_keepalive(coordinator_agent.extract_actions(final_html, client)):
            if isinstance(chunk, str) and chunk.startswith(": keep-alive"):
                yield chunk
            else:
                actions = chunk
        logger.info("Coordinator Agent: Action extraction finished.")
    else:
        logger.info("Coordinator Agent: Actions were already extracted via tool call.")
        
    # Initial metadata and actions events
    metadata = json.dumps(
        {
            **doctor_info,
            "evidence_map": {"chunks": [], "citations": []},
            "prescription_text": context.get("prescription_text", ""),
            "prescription_filename": context.get("prescription_filename", ""),
            "prescription_texts": context.get("prescription_texts", []),
            "prescription_filenames": context.get("prescription_filenames", []),
        }
    )
    yield f"event: metadata\ndata: {metadata}\n\n"
    if actions:
        yield f"event: actions\ndata: {json.dumps(actions)}\n\n"

    # Evidence mapping
    if await _abort_now("before evidence mapping"):
        return
        
    yield "event: status\ndata: Linking evidence to source documents...\n\n"
    logger.info("Starting evidence mapping.")
    
    # Run evidence mapping with keep-alive
    try:
        evidence_map = None
        async for chunk in run_with_keepalive(evidence_agent.build_evidence_map(final_html, context, client)):
            if isinstance(chunk, str) and chunk.startswith(": keep-alive"):
                yield chunk
            else:
                evidence_map = chunk
    except Exception as exc:
        logger.error(f"Evidence mapping failed: {exc}")
        evidence_map = {"chunks": [], "citations": []}

    logger.info("Evidence mapping finished.")
    evidence_map = _shrink_evidence_map(evidence_map)
    yield f"event: evidence_update\ndata: {json.dumps(evidence_map)}\n\n"


    # Persist summary, notes, and evidence to long-term memory after evidence mapping completes.
    try:
        summary_text = html_to_text(final_html)
        notes_text = _format_notes_text(context)
        evidence_text = _format_evidence_text(evidence_map)
        if summary_text and visit.patient_name and visit.date_of_visit:
            await memory_agent.remember_visit(
                summary=summary_text,
                patient_name=visit.patient_name,
                date=visit.date_of_visit,
                client=client,
            )
            logger.info("Saved summary to long-term memory.")
        if notes_text and visit.patient_name and visit.date_of_visit:
            await memory_agent.remember_visit(
                summary=notes_text,
                patient_name=visit.patient_name,
                date=visit.date_of_visit,
                client=client,
                doc_type="visit_notes",
            )
            logger.info("Saved notes to long-term memory.")
        if evidence_text and visit.patient_name and visit.date_of_visit:
            await memory_agent.remember_visit(
                summary=evidence_text,
                patient_name=visit.patient_name,
                date=visit.date_of_visit,
                client=client,
                doc_type="visit_evidence",
                payload=evidence_map,
            )
            logger.info("Saved evidence links to long-term memory.")
        if not (summary_text and visit.patient_name and visit.date_of_visit):
            logger.info("Skipping summary memory save: missing summary text or visit metadata.")
    except Exception as exc:
        logger.error(f"Failed to save memory records: {exc}")

    # Send final summary as a single payload for clients that do not stream partial output.
    yield f"event: summary\ndata: {json.dumps({'summary_html': final_html})}\n\n"


async def run_summary_pipeline(
    visit: Visit,
    client: AsyncOpenAI,
    request: Optional[Any] = None,
) -> AsyncGenerator[str, None]:
    """
    Orchestrates the full summary generation pipeline:
    1. Extract text/data from visit files.
    2. Extract doctor info.
    3. Recall patient history (RAG).
    4. Generate and stream summary.
    """
    logger.info(f"Starting summary pipeline for patient: {visit.patient_name}")

    async def is_disconnected() -> bool:
        if request is None:
            return False
        try:
            return await request.is_disconnected()
        except Exception:
            return False

    if await is_disconnected():
        logger.info("Client disconnected before summary start.")
        return

    cache_key = _summary_cache_key(visit)
    cached = _cache_get(cache_key)
    if cached:
        logger.info("Summary cache hit.")
        for chunk in cached["events"]:
            yield chunk
        return
    logger.info("Summary cache miss.")

    # 1. Extraction Phase
    context = await extraction_agent.build_visit_context(visit, client)
    if await is_disconnected():
        logger.info("Client disconnected after extraction.")
        return

    # 2. Memory Recall Phase (parallel with doctor info extraction)
    doctor_task = extraction_agent.extract_doctor_info(context["combined_text"], client)
    history_task = None
    if visit.patient_name and context.get("combined_text"):
        history_task = memory_agent.recall_patient_history(
            patient_name=visit.patient_name,
            query=context["combined_text"],
            client=client
        )

    if history_task:
        doctor_info, history = await asyncio.gather(doctor_task, history_task)
    else:
        doctor_info = await doctor_task
        history = "No past history found."

    context["patient_history"] = history
    context["doctor_info"] = doctor_info

    # 3. Generation Phase
    events: list[str] = []
    async for chunk in generate_summary_stream(
        visit,
        context,
        doctor_info,
        client,
        should_abort=is_disconnected,
    ):
        if await is_disconnected():
            logger.info("Client disconnected during summary stream.")
            return
        events.append(chunk)
        yield chunk

    if await is_disconnected():
        logger.info("Client disconnected before cache write.")
        return

    _cache_set(cache_key, {"events": events})




async def run_summary_pipeline_resumable(
    visit,
    client,
    request: Request,
) -> AsyncGenerator[str, None]:
    """
    Starts (or reuses) a job_id, sends it immediately to the UI, then streams
    status + final output from the job event log (Upstash or in-memory).
    """
    try:
        job_id = await start_summary_job(visit, client)
    except UpstashError as e:
        yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
        return

    # Always tell the UI the job_id first (so reconnect works)
    yield f"event: job\ndata: {json.dumps({'job_id': job_id})}\n\n"

    # Then stream the job events (this is where your status + final output come from)
    async for chunk in stream_summary_job(job_id, request=request):
        yield chunk

# --- STRICT HTML FINALIZER (3 sections only) ---

_SECTION_NAMES = ("summary", "next_steps", "patient_email")

def _extract_section(html: str, name: str) -> Optional[str]:
    if not html:
        return None
    # case-insensitive match, tolerate extra attributes
    pattern = re.compile(
        rf'<section\s+[^>]*data-section=["\']{re.escape(name)}["\'][^>]*>.*?</section>',
        re.IGNORECASE | re.DOTALL,
    )
    m = pattern.search(html)
    return m.group(0).strip() if m else None

def _strict_three_sections(html: str) -> Optional[str]:
    s = _extract_section(html, "summary")
    n = _extract_section(html, "next_steps")
    p = _extract_section(html, "patient_email")
    if not (s and n and p):
        return None
    return f"{s}\n\n{n}\n\n{p}".strip()

async def _repair_to_three_sections(
    client: AsyncOpenAI,
    template: dict,
    text_or_html: str,
) -> str:
    """
    One repair pass: force the model to return ONLY the three <section> blocks.
    Then we still validate with _strict_three_sections.
    """
    repair_system = (
        "Return ONLY strict HTML with EXACTLY these 3 sections and NOTHING else:\n"
        '<section data-section="summary">...</section>\n'
        '<section data-section="next_steps">...</section>\n'
        '<section data-section="patient_email">...</section>\n'
        "No preamble, no titles, no markdown. Do not wrap in <html> or <body>.\n"
        "Follow the provided template headings exactly."
    )

    repair_user = (
        "Fix this content so it becomes valid output (three sections only).\n\n"
        f"Template label: {template.get('label','')}\n"
        f"Template HTML:\n{template.get('summary_html','')}\n\n"
        f"Content to fix:\n{text_or_html}"
    )

    resp = await generate_with_fallback(
        client=client,
        messages=[
            {"role": "system", "content": repair_system},
            {"role": "user", "content": repair_user},
        ],
        models=["deepseek-chat"],
        temperature=0.0,
    )
    raw = resp.choices[0].message.content or ""
    raw = _strip_tool_call_artifacts(raw)
    return raw.strip()

async def finalize_summary_html(
    client: AsyncOpenAI,
    template: dict,
    raw_text_or_html: str,
) -> str:
    """
    Guarantee the final output is ONLY the three required <section data-section="..."> blocks.
    """
    # 1) If it already contains the 3 sections, strip everything else
    strict = _strict_three_sections(raw_text_or_html)
    if strict:
        return strict

    # 2) Try your wrapper/normalizer, then extract again
    wrapped = ensure_html_summary(raw_text_or_html or "", template)
    strict = _strict_three_sections(wrapped)
    if strict:
        return strict

    # 3) One repair pass, then validate
    repaired = await _repair_to_three_sections(client, template, raw_text_or_html or "")
    strict = _strict_three_sections(repaired)
    if strict:
        return strict

    wrapped2 = ensure_html_summary(repaired, template)
    strict = _strict_three_sections(wrapped2)
    if strict:
        return strict

    # 4) Last resort (still valid for the UI)
    return (
        '<section data-section="summary"><h3>Summary of visit for the doctor\'s records</h3>'
        "<p>Not documented.</p></section>\n\n"
        '<section data-section="next_steps"><h3>Next steps for the doctor</h3><ul>'
        "<li>Not documented.</li></ul></section>\n\n"
        '<section data-section="patient_email"><h3>Draft Email for Patient</h3>'
        "<p>Not documented.</p></section>"
    )



def _sse_event_name(chunk: str) -> str | None:
    if not chunk:
        return None
    m = SSE_EVENT_RE.search(chunk)
    return m.group(1) if m else None

def _shrink_evidence_map(evidence_map: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reduce Redis payload size while keeping UI useful.
    Keeps first N chunks/citations and truncates long snippet texts.
    """
    if not isinstance(evidence_map, dict):
        return {"chunks": [], "citations": []}

    chunks = evidence_map.get("chunks") or []
    citations = evidence_map.get("citations") or []

    if isinstance(chunks, list):
        chunks = chunks[:EVIDENCE_MAX_CHUNKS]
        for c in chunks:
            if isinstance(c, dict) and "text" in c and isinstance(c["text"], str):
                t = c["text"].strip()
                if len(t) > EVIDENCE_SNIPPET_MAX:
                    c["text"] = t[:EVIDENCE_SNIPPET_MAX] + "..."

    if isinstance(citations, list):
        citations = citations[:EVIDENCE_MAX_CITATIONS]
        for cit in citations:
            if not isinstance(cit, dict):
                continue
            snips = cit.get("snippets")
            if isinstance(snips, dict):
                for k, v in list(snips.items()):
                    if isinstance(v, str):
                        vv = v.strip()
                        if len(vv) > EVIDENCE_SNIPPET_MAX:
                            snips[k] = vv[:EVIDENCE_SNIPPET_MAX] + "..."

    return {"chunks": chunks, "citations": citations}
