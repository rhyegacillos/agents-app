import asyncio
import os
import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import HTTPException

from config import ASYNC_JOB_TTL_SECONDS
from observability import reset_trace_id, set_trace_id
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
    logging.info("[worker] start job_id=%s user_id=%s session_id=%s", job_id, user_id, session_id)
    job = _upstash_get(_job_key(job_id)) or {
        "job_id": job_id,
        "user_id": user_id,
        "session_id": session_id,
    }
    if job.get("status") == "canceled":
        logging.info("[worker] canceled before start job_id=%s", job_id)
        return {"status": "canceled", "job_id": job_id}
    job["status"] = "running"
    job["updated_at"] = datetime.now().isoformat()
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
        job["updated_at"] = datetime.now().isoformat()
        _upstash_set(_job_key(job_id), job, ASYNC_JOB_TTL_SECONDS)
        logging.info("[worker] completed job_id=%s", job_id)
        return {"status": "ok", "job_id": job_id}
    except asyncio.TimeoutError:
        job["status"] = "failed"
        job["error"] = f"Worker timed out after {worker_max_seconds}s"
        job["updated_at"] = datetime.now().isoformat()
        _upstash_set(_job_key(job_id), job, ASYNC_JOB_TTL_SECONDS)
        logging.warning("[worker] timeout job_id=%s after=%ss", job_id, worker_max_seconds)
        return {"status": "error", "job_id": job_id, "error": "timeout"}
    except HTTPException as e:
        if str(e.detail) == "canceled":
            job["status"] = "canceled"
            job["error"] = "canceled by user"
            job["updated_at"] = datetime.now().isoformat()
            _upstash_set(_job_key(job_id), job, ASYNC_JOB_TTL_SECONDS)
            logging.info("[worker] canceled job_id=%s", job_id)
            return {"status": "canceled", "job_id": job_id}
        job["status"] = "failed"
        job["error"] = str(e.detail)
        job["updated_at"] = datetime.now().isoformat()
        _upstash_set(_job_key(job_id), job, ASYNC_JOB_TTL_SECONDS)
        logging.exception("[worker] http exception job_id=%s", job_id)
        return {"status": "error", "job_id": job_id, "error": str(e.detail)}
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
        job["updated_at"] = datetime.now().isoformat()
        _upstash_set(_job_key(job_id), job, ASYNC_JOB_TTL_SECONDS)
        logging.exception("[worker] exception job_id=%s", job_id)
        return {"status": "error", "job_id": job_id, "error": str(e)}
    finally:
        _reset_current_job_id(token)
        reset_trace_id(trace_token)
