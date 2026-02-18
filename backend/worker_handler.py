import asyncio
import os
import logging
from typing import Any, Dict

from fastapi import HTTPException
from opentelemetry.trace import SpanKind

from config import ASYNC_JOB_TTL_SECONDS
from observability import log_event, now_local_iso, reset_trace_id, set_trace_id
from otel_observability import (
    flush_otel,
    get_tracer as get_otel_tracer,
    record_current_span_exception,
    set_current_span_attributes,
)
from services.storage import _job_key, _upstash_get, _upstash_set
from server import _reset_current_job_id, _run_chat_flow, _set_current_job_id


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    job_id = (event or {}).get("job_id")
    trace_id = (event or {}).get("trace_id")
    user_id = (event or {}).get("user_id")
    session_id = (event or {}).get("session_id")
    message = (event or {}).get("message", "")
    file_id = (event or {}).get("file_id")

    if not job_id or not user_id or not session_id or not message:
        return {"status": "error", "error": "missing job fields"}

    _, trace_token = set_trace_id(trace_id)
    try:
        tracer = get_otel_tracer("digital_assistant.worker")
        with tracer.start_as_current_span("worker.job", kind=SpanKind.CONSUMER) as span:
            if span is not None:
                span.set_attribute("trace_id", trace_id or "-")
                span.set_attribute("job.id", job_id)
                span.set_attribute("user.id", user_id)
                span.set_attribute("session.id", session_id)
                span.set_attribute("runtime", "worker")
            set_current_span_attributes({"trace_id": trace_id or "-", "job.id": job_id, "session.id": session_id})
            log_event("worker.start", job_id=job_id, user_id=user_id, session_id=session_id)
            job = _upstash_get(_job_key(job_id)) or {
                "job_id": job_id,
                "user_id": user_id,
                "session_id": session_id,
            }
            if job.get("status") == "canceled":
                log_event("worker.canceled_prestart", job_id=job_id)
                return {"status": "canceled", "job_id": job_id}
            job["status"] = "running"
            job["updated_at"] = now_local_iso()
            _upstash_set(_job_key(job_id), job, ASYNC_JOB_TTL_SECONDS)

            worker_max_seconds = int(os.getenv("WORKER_MAX_SECONDS", "240"))
            token = _set_current_job_id(job_id)
            try:
                async def _run_with_timeout():
                    return await asyncio.wait_for(
                        _run_chat_flow(
                            user_id=user_id,
                            session_id=session_id,
                            message=message,
                            file_id=file_id,
                        ),
                        timeout=worker_max_seconds,
                    )

                assistant_response = asyncio.run(_run_with_timeout())
                job["status"] = "completed"
                job["response"] = assistant_response
                job["updated_at"] = now_local_iso()
                _upstash_set(_job_key(job_id), job, ASYNC_JOB_TTL_SECONDS)
                log_event("worker.completed", job_id=job_id)
                return {"status": "ok", "job_id": job_id}
            except asyncio.TimeoutError:
                timeout_exc = asyncio.TimeoutError(f"Worker timed out after {worker_max_seconds}s")
                record_current_span_exception(timeout_exc)
                job["status"] = "failed"
                job["error"] = f"Worker timed out after {worker_max_seconds}s"
                job["updated_at"] = now_local_iso()
                _upstash_set(_job_key(job_id), job, ASYNC_JOB_TTL_SECONDS)
                log_event(
                    "worker.timeout",
                    level=logging.WARNING,
                    job_id=job_id,
                    after_s=worker_max_seconds,
                )
                return {"status": "error", "job_id": job_id, "error": "timeout"}
            except HTTPException as e:
                if str(e.detail) == "canceled":
                    job["status"] = "canceled"
                    job["error"] = "canceled by user"
                    job["updated_at"] = now_local_iso()
                    _upstash_set(_job_key(job_id), job, ASYNC_JOB_TTL_SECONDS)
                    log_event("worker.canceled", job_id=job_id)
                    return {"status": "canceled", "job_id": job_id}
                record_current_span_exception(e)
                job["status"] = "failed"
                job["error"] = str(e.detail)
                job["updated_at"] = now_local_iso()
                _upstash_set(_job_key(job_id), job, ASYNC_JOB_TTL_SECONDS)
                logging.exception("event=worker.http_exception job_id=%s", job_id)
                return {"status": "error", "job_id": job_id, "error": str(e.detail)}
            except Exception as e:
                record_current_span_exception(e)
                job["status"] = "failed"
                job["error"] = str(e)
                job["updated_at"] = now_local_iso()
                _upstash_set(_job_key(job_id), job, ASYNC_JOB_TTL_SECONDS)
                logging.exception("event=worker.exception job_id=%s", job_id)
                return {"status": "error", "job_id": job_id, "error": str(e)}
            finally:
                _reset_current_job_id(token)
    finally:
        flush_otel()
        reset_trace_id(trace_token)
