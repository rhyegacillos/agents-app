import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import quote

import requests

from secret_env import get_secret_env


_LOCK = threading.Lock()
_LOCAL_RESULTS: Dict[str, Dict[str, Any]] = {}
_TRACE_ENV_KEYS = ("TRACEPARENT", "TRACESTATE", "BAGGAGE")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _upstash_enabled() -> bool:
    return bool(get_secret_env("UPSTASH_REDIS_REST_URL", "") and get_secret_env("UPSTASH_REDIS_REST_TOKEN", ""))


def _upstash_request(
    path: str,
    *,
    method: str = "GET",
    data: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
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


def request_scope_id() -> str:
    job_id = os.getenv("ASYNC_JOB_ID", "").strip()
    if job_id:
        return f"job:{job_id}"
    trace_bits = [os.getenv(key, "").strip() for key in _TRACE_ENV_KEYS if os.getenv(key, "").strip()]
    if trace_bits:
        return "trace:" + "|".join(trace_bits)
    return "pid:" + str(os.getpid())


def idempotency_key(*, action: str, payload: Dict[str, Any]) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    payload_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"idempotency:{request_scope_id()}:{action}:{payload_hash}"


def read_result(key: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        cached = _LOCAL_RESULTS.get(key)
    if cached is not None:
        return dict(cached)
    if not _upstash_enabled():
        return None
    stored = _upstash_get(key)
    if isinstance(stored, dict):
        with _LOCK:
            _LOCAL_RESULTS[key] = dict(stored)
        return dict(stored)
    return None


def write_result(key: str, result: Dict[str, Any], *, ttl_seconds: int = 3600) -> Dict[str, Any]:
    payload = dict(result)
    payload.setdefault("stored_at", _utc_now_iso())
    with _LOCK:
        _LOCAL_RESULTS[key] = dict(payload)
    if _upstash_enabled():
        _upstash_set(key, payload, ttl_seconds)
    return payload
