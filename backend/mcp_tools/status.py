import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import quote

import requests

from secret_env import get_secret_env


def _upstash_enabled() -> bool:
    return bool(get_secret_env("UPSTASH_REDIS_REST_URL", "") and get_secret_env("UPSTASH_REDIS_REST_TOKEN", ""))


def _job_key(job_id: str) -> str:
    return f"job:{job_id}"


def _upstash_request(path: str, *, method: str = "GET", data: Optional[str] = None, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    base = get_secret_env("UPSTASH_REDIS_REST_URL", "")
    token = get_secret_env("UPSTASH_REDIS_REST_TOKEN", "")
    if not base or not token:
        return None
    url = f"{base.rstrip('/')}/{path.lstrip('/')}"
    headers = {"Authorization": f"Bearer {token}"}
    if method.upper() == "POST":
        resp = requests.post(url, headers=headers, params=params, data=data or "", timeout=5)
    else:
        resp = requests.get(url, headers=headers, params=params, timeout=5)
    resp.raise_for_status()
    return resp.json()


def _upstash_get(key: str) -> Optional[Dict[str, Any]]:
    payload = _upstash_request(f"get/{quote(key, safe='')}")
    if not payload:
        return None
    result = payload.get("result")
    if result is None:
        return None
    if isinstance(result, dict):
        return result
    try:
        return json.loads(result)
    except Exception:
        return {"value": result}


def _upstash_set(key: str, value: Dict[str, Any], ttl_seconds: int) -> None:
    payload = json.dumps(value)
    _upstash_request(
        f"set/{quote(key, safe='')}",
        method="POST",
        data=payload,
        params={"EX": str(ttl_seconds)},
    )


def update_job_status(message: str, progress: Optional[int] = None) -> None:
    job_id = os.getenv("ASYNC_JOB_ID", "").strip()
    if not job_id or not _upstash_enabled():
        return
    ttl_seconds = int(os.getenv("ASYNC_JOB_TTL_SECONDS", "3600"))
    try:
        job = _upstash_get(_job_key(job_id)) or {"job_id": job_id}
        job["status_message"] = message
        if progress is not None:
            job["status_progress"] = max(0, min(100, int(progress)))
        job["updated_at"] = datetime.now(timezone.utc).isoformat()
        _upstash_set(_job_key(job_id), job, ttl_seconds)
    except Exception:
        # Never break tool execution because of status updates
        return
