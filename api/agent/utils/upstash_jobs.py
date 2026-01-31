import os
import time
import json
import asyncio
from typing import Any, AsyncGenerator, Callable, Iterable, Optional
from openai import AsyncOpenAI

from ..models import Visit
from .upstash_rest import get_upstash, UpstashError

# Environment-configurable knobs
# Hard-coded 24h TTL for summary job cache
SUMMARY_JOBS_TTL_SECONDS = 60 * 60 * 24
SUMMARY_JOBS_POLL_SECONDS = float(os.getenv("SUMMARY_JOBS_POLL_SECONDS", "0.5"))
SUMMARY_JOBS_POLL_MAX_SECONDS = float(os.getenv("SUMMARY_JOBS_POLL_MAX_SECONDS", "5.0"))
SUMMARY_JOBS_POLL_BACKOFF_MULT = float(os.getenv("SUMMARY_JOBS_POLL_BACKOFF_MULT", "1.6"))
SUMMARY_EVENTS_MAX = int(os.getenv("SUMMARY_EVENTS_MAX", "250"))


def upstash_client():
    return get_upstash()


def upstash_enabled() -> bool:
    return upstash_client() is not None


def job_meta_key(job_id: str) -> str:
    return f"summary:job:{job_id}:meta"


def job_events_key(job_id: str) -> str:
    return f"summary:job:{job_id}:events"


def job_keymap_key(cache_key: str) -> str:
    return f"summary:jobkey:{cache_key}"


async def run_summary_job_upstash(
    job_id: str,
    visit: Visit,
    client: AsyncOpenAI,
    persist_events: Iterable[str],
    events_max: int,
    ttl_seconds: int,
    run_pipeline: Callable[[Visit, AsyncOpenAI, Any], AsyncGenerator[str, None]],
    logger,
) -> None:
    """
    Upstash-backed job runner. Writes SSE chunks into a Redis list so any instance can stream them.
    """
    redis = upstash_client()
    if redis is None:
        return

    meta_key = job_meta_key(job_id)
    events_key = job_events_key(job_id)

    now = time.time()

    # Initial meta state
    await redis.execute(
        "HSET",
        meta_key,
        "status",
        "running",
        "created_at",
        str(now),
        "updated_at",
        str(now),
        "event_count",
        "0",
        "done",
        "0",
    )
    await redis.execute("EXPIRE", meta_key, str(ttl_seconds))
    await redis.execute("EXPIRE", events_key, str(ttl_seconds))

    try:
        async for chunk in run_pipeline(visit, client, request=None):
            if not isinstance(chunk, str):
                chunk = str(chunk)

            # Persist only whitelisted events
            matches = []
            if chunk.startswith("event:"):
                try:
                    evt = chunk.split("\n", 1)[0].split("event:", 1)[1].strip()
                    matches.append(evt)
                except Exception:
                    pass

            if matches and matches[0] in persist_events:
                await redis.execute("RPUSH", events_key, chunk)
                await redis.execute("LTRIM", events_key, str(-events_max), "-1")
                await redis.execute("HINCRBY", meta_key, "event_count", "1")
                await redis.execute("HSET", meta_key, "updated_at", str(time.time()))

        await redis.execute("HSET", meta_key, "status", "done", "done", "1", "updated_at", str(time.time()))
    except Exception as exc:
        logger.error(f"Upstash summary job failed: {exc}")
        await redis.execute("HSET", meta_key, "status", "error", "error", str(exc), "done", "1", "updated_at", str(time.time()))
        raise
    finally:
        # Ensure TTL remains
        await redis.execute("EXPIRE", meta_key, str(ttl_seconds))
        await redis.execute("EXPIRE", events_key, str(ttl_seconds))


async def stream_job_events_upstash(
    job_id: str,
    request: Optional[Any],
    poll_seconds: float,
    poll_max_seconds: float,
    backoff_mult: float,
    logger,
) -> AsyncGenerator[str, None]:
    """
    Stream SSE event chunks for a job from Upstash Redis (REST) with adaptive backoff.
    """
    redis = upstash_client()
    if redis is None:
        return

    meta_key = job_meta_key(job_id)
    events_key = job_events_key(job_id)

    idx = 0
    sleep_s = poll_seconds

    while True:
        if request is not None:
            try:
                if await request.is_disconnected():
                    return
            except Exception:
                pass

        meta = await redis.execute("HMGET", meta_key, "done", "event_count", "error")
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

        if idx < event_count:
            start = idx
            end = event_count - 1
            items = await redis.execute("LRANGE", events_key, str(start), str(end)) or []
            for item in items:
                yield str(item)
            idx = event_count
            sleep_s = poll_seconds
            continue

        if done == "1":
            if error:
                yield f"event: error\ndata: {json.dumps({'error': error})}\n\n"
            return

        await asyncio.sleep(sleep_s)
        sleep_s = min(poll_max_seconds, sleep_s * backoff_mult)


async def get_job_meta_upstash(job_id: str) -> Optional[dict[str, str]]:
    if not upstash_enabled():
        return None
    redis = upstash_client()
    assert redis is not None
    meta = await redis.execute("HGETALL", job_meta_key(job_id))
    if not meta:
        return None
    if isinstance(meta, list):
        it = iter(meta)
        return {str(k): str(v) for k, v in zip(it, it)}
    if isinstance(meta, dict):
        return {str(k): str(v) for k, v in meta.items()}
    return {"raw": str(meta)}
