import asyncio
import os
from datetime import datetime
from typing import Any, Dict

from fastapi import HTTPException

from config import ASYNC_JOB_TTL_SECONDS
from services.storage import _job_key, _upstash_get, _upstash_set
from server import _reset_current_job_id, _run_chat_flow, _set_current_job_id


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    job_id = (event or {}).get("job_id")
    user_id = (event or {}).get("user_id")
    session_id = (event or {}).get("session_id")
    message = (event or {}).get("message", "")
    file_id = (event or {}).get("file_id")

    if not job_id or not user_id or not session_id or not message:
        return {"status": "error", "error": "missing job fields"}

    print(f"[worker] start job_id={job_id} user_id={user_id} session_id={session_id}")
    job = _upstash_get(_job_key(job_id)) or {
        "job_id": job_id,
        "user_id": user_id,
        "session_id": session_id,
    }
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
        print(f"[worker] completed job_id={job_id}")
        return {"status": "ok", "job_id": job_id}
    except asyncio.TimeoutError:
        job["status"] = "failed"
        job["error"] = f"Worker timed out after {worker_max_seconds}s"
        job["updated_at"] = datetime.now().isoformat()
        _upstash_set(_job_key(job_id), job, ASYNC_JOB_TTL_SECONDS)
        print(f"[worker] timeout job_id={job_id} after={worker_max_seconds}s")
        return {"status": "error", "job_id": job_id, "error": "timeout"}
    except HTTPException as e:
        job["status"] = "failed"
        job["error"] = str(e.detail)
        job["updated_at"] = datetime.now().isoformat()
        _upstash_set(_job_key(job_id), job, ASYNC_JOB_TTL_SECONDS)
        print(f"[worker] failed job_id={job_id} error={e.detail}")
        return {"status": "error", "job_id": job_id, "error": str(e.detail)}
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
        job["updated_at"] = datetime.now().isoformat()
        _upstash_set(_job_key(job_id), job, ASYNC_JOB_TTL_SECONDS)
        print(f"[worker] failed job_id={job_id} error={e}")
        return {"status": "error", "job_id": job_id, "error": str(e)}
    finally:
        _reset_current_job_id(token)
