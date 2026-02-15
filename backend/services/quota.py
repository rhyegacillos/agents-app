from __future__ import annotations

import json
import logging
import os
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from botocore.exceptions import ClientError

from config import DAILY_EMAIL_LIMIT, DAILY_PDF_LIMIT, DAILY_TOKEN_LIMIT, S3_BUCKET, USE_S3, s3_client
from services.storage import _upstash_enabled, _upstash_get, _upstash_hgetall, _upstash_set

_METRICS = ("tokens", "pdf", "email")
_LOGGER = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _limits() -> Dict[str, int]:
    return {
        "tokens": max(0, DAILY_TOKEN_LIMIT),
        "pdf": max(0, DAILY_PDF_LIMIT),
        "email": max(0, DAILY_EMAIL_LIMIT),
    }


def _quota_key(user_id: str, now: datetime) -> str:
    return f"quota:{user_id}:{now.strftime('%Y%m%d')}"


def _reset_at(now: datetime) -> datetime:
    day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    return day_start + timedelta(days=1)


def _ttl_seconds(now: datetime) -> int:
    reset_time = _reset_at(now)
    # Keep the key alive for one extra day for debugging/inspection.
    return max(86400, int((reset_time - now).total_seconds()) + 86400)


def _usage_from_hash(data: Dict[str, str]) -> Dict[str, int]:
    return {
        "tokens": max(0, _as_int(data.get("tokens"), 0)),
        "pdf": max(0, _as_int(data.get("pdf"), 0)),
        "email": max(0, _as_int(data.get("email"), 0)),
    }


def _local_quota_enabled() -> bool:
    return str(os.getenv("QUOTA_LOCAL_FALLBACK", "true")).strip().lower() not in {"0", "false", "off", "no"}


def _s3_quota_enabled() -> bool:
    return bool(USE_S3 and s3_client and S3_BUCKET)


def _s3_quota_key(user_id: str, now: datetime) -> str:
    safe_user = "".join(ch for ch in user_id if ch.isalnum() or ch in {"_", "-"})
    day = now.strftime("%Y%m%d")
    return f"quota/{safe_user}-{day}.json"


def _s3_read_usage(user_id: str, now: datetime) -> Dict[str, int]:
    try:
        resp = s3_client.get_object(Bucket=S3_BUCKET, Key=_s3_quota_key(user_id, now))
        payload = json.loads(resp["Body"].read().decode("utf-8"))
        if isinstance(payload, dict):
            usage = payload.get("usage", payload)
            if isinstance(usage, dict):
                return _usage_from_hash({k: str(v) for k, v in usage.items()})
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "NoSuchKey":
            raise
    except Exception:
        return {"tokens": 0, "pdf": 0, "email": 0}
    return {"tokens": 0, "pdf": 0, "email": 0}


def _s3_read_payload_with_etag(user_id: str, now: datetime) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        resp = s3_client.get_object(Bucket=S3_BUCKET, Key=_s3_quota_key(user_id, now))
        payload = json.loads(resp["Body"].read().decode("utf-8"))
        etag = str(resp.get("ETag") or "").strip() or None
        if isinstance(payload, dict):
            return payload, etag
        return {}, etag
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"NoSuchKey", "404"}:
            return None, None
        raise


def _apply_quota_limits(
    current_usage: Dict[str, int],
    increments: Dict[str, int],
    limits: Dict[str, int],
) -> Tuple[Dict[str, int], Dict[str, int], list[str]]:
    usage = {
        "tokens": max(0, _as_int(current_usage.get("tokens"), 0)),
        "pdf": max(0, _as_int(current_usage.get("pdf"), 0)),
        "email": max(0, _as_int(current_usage.get("email"), 0)),
    }
    exceeded: list[str] = []
    applied: Dict[str, int] = {}

    for metric in _METRICS:
        requested = max(0, _as_int(increments.get(metric), 0))
        if requested <= 0:
            continue
        limit = max(0, _as_int(limits.get(metric), 0))
        used = max(0, _as_int(usage.get(metric), 0))
        allowed = max(0, limit - used)
        consume = min(requested, allowed)

        if consume <= 0:
            exceeded.append(metric)
            continue

        usage[metric] = used + consume
        applied[metric] = consume
        if consume < requested:
            exceeded.append(metric)

    return usage, applied, sorted(set(exceeded))


def _s3_write_usage_atomic(
    *,
    user_id: str,
    now: datetime,
    increments: Dict[str, int],
    limits: Dict[str, int],
) -> Tuple[Dict[str, int], Dict[str, int], list[str]]:
    max_retries = max(1, int(os.getenv("S3_QUOTA_MAX_RETRIES", "6")))
    key = _s3_quota_key(user_id, now)
    last_usage = {"tokens": 0, "pdf": 0, "email": 0}
    last_applied: Dict[str, int] = {}
    last_exceeded: list[str] = []
    conflict_count = 0

    for attempt in range(max_retries):
        attempt_no = attempt + 1
        payload, etag = _s3_read_payload_with_etag(user_id, now)
        base = payload or {}
        current_raw = base.get("usage", base) if isinstance(base, dict) else {}
        if not isinstance(current_raw, dict):
            current_raw = {}
        current_usage = _usage_from_hash({k: str(v) for k, v in current_raw.items()})
        next_usage, applied, exceeded = _apply_quota_limits(current_usage, increments, limits)
        last_usage, last_applied, last_exceeded = next_usage, applied, exceeded

        body = json.dumps(
            {
                "day": now.strftime("%Y-%m-%d"),
                "usage": next_usage,
                "updated_at": now.isoformat(),
            }
        )
        try:
            put_kwargs = {
                "Bucket": S3_BUCKET,
                "Key": key,
                "Body": body,
                "ContentType": "application/json",
            }
            if etag:
                put_kwargs["IfMatch"] = etag
            else:
                put_kwargs["IfNoneMatch"] = "*"
            s3_client.put_object(**put_kwargs)
            _LOGGER.info(
                "[quota_s3_cas] status=ok user_id=%s key=%s attempt=%d/%d conflicts=%d etag=%s applied_tokens=%d applied_pdf=%d applied_email=%d exceeded=%s",
                user_id,
                key,
                attempt_no,
                max_retries,
                conflict_count,
                etag or "none",
                int(applied.get("tokens", 0)),
                int(applied.get("pdf", 0)),
                int(applied.get("email", 0)),
                ",".join(exceeded) if exceeded else "-",
            )
            return next_usage, applied, exceeded
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in {"PreconditionFailed", "ConditionalRequestConflict"} or attempt >= max_retries - 1:
                _LOGGER.error(
                    "[quota_s3_cas] status=error user_id=%s key=%s attempt=%d/%d code=%s",
                    user_id,
                    key,
                    attempt_no,
                    max_retries,
                    code or "unknown",
                )
                raise
            # Short jitter before retry to reduce thundering-herd collisions.
            conflict_count += 1
            _LOGGER.warning(
                "[quota_s3_cas] status=conflict user_id=%s key=%s attempt=%d/%d code=%s",
                user_id,
                key,
                attempt_no,
                max_retries,
                code,
            )
            time.sleep(0.01 + random.random() * 0.02)

    return last_usage, last_applied, last_exceeded


def _local_quota_path(user_id: str, now: datetime) -> str:
    base = os.getenv("QUOTA_LOCAL_DIR", "/tmp/quota").strip() or "/tmp/quota"
    safe_user = "".join(ch for ch in user_id if ch.isalnum() or ch in {"_", "-"})
    day = now.strftime("%Y%m%d")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, f"{safe_user}-{day}.json")


def _local_read_usage(user_id: str, now: datetime) -> Dict[str, int]:
    path = _local_quota_path(user_id, now)
    if not os.path.exists(path):
        return {"tokens": 0, "pdf": 0, "email": 0}
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return {"tokens": 0, "pdf": 0, "email": 0}
    if isinstance(payload, dict):
        usage = payload.get("usage", payload)
        if isinstance(usage, dict):
            return _usage_from_hash({k: str(v) for k, v in usage.items()})
    return {"tokens": 0, "pdf": 0, "email": 0}


def _local_write_usage(user_id: str, now: datetime, usage: Dict[str, int]) -> None:
    path = _local_quota_path(user_id, now)
    payload = {
        "day": now.strftime("%Y-%m-%d"),
        "usage": {
            "tokens": max(0, _as_int(usage.get("tokens"), 0)),
            "pdf": max(0, _as_int(usage.get("pdf"), 0)),
            "email": max(0, _as_int(usage.get("email"), 0)),
        },
        "updated_at": now.isoformat(),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def get_daily_quota(user_id: str) -> Dict[str, Any]:
    now = _utc_now()
    limits = _limits()
    usage = {"tokens": 0, "pdf": 0, "email": 0}
    enabled = _upstash_enabled()
    backend = "upstash"

    if enabled:
        try:
            payload = _upstash_get(_quota_key(user_id, now)) or {}
            if isinstance(payload, dict):
                usage = _usage_from_hash(payload.get("usage", payload))
        except Exception:
            # Backward compatibility: older deployments stored this key as a Redis hash.
            try:
                usage = _usage_from_hash(_upstash_hgetall(_quota_key(user_id, now)))
            except Exception:
                enabled = False
    elif _s3_quota_enabled():
        enabled = True
        backend = "s3"
        usage = _s3_read_usage(user_id, now)
    elif _local_quota_enabled():
        enabled = True
        backend = "local"
        usage = _local_read_usage(user_id, now)

    remaining = {metric: max(0, limits[metric] - usage.get(metric, 0)) for metric in _METRICS}
    return {
        "enabled": enabled,
        "backend": backend if enabled else "none",
        "day": now.strftime("%Y-%m-%d"),
        "reset_at": _reset_at(now).isoformat(),
        "limits": limits,
        "usage": usage,
        "remaining": remaining,
    }


def count_quota_actions_from_truth_context(context: Dict[str, Any]) -> Dict[str, int]:
    pdf = 0
    email = 0

    seen_pdf = set()
    for artifact in context.get("artifacts", []) or []:
        if not isinstance(artifact, dict):
            continue
        if str(artifact.get("kind") or "").lower() != "pdf":
            continue
        source_tool = str(artifact.get("source_tool") or "")
        if "generate_pdf_from_text" not in source_tool:
            continue
        if str(artifact.get("status") or "").lower() not in {"", "ok"}:
            continue
        key = (
            str(artifact.get("download_url") or "").strip()
            or str(artifact.get("filename") or "").strip()
            or str(artifact.get("artifact_id") or "").strip()
        )
        if not key or key in seen_pdf:
            continue
        seen_pdf.add(key)
        pdf += 1

    seen_email = set()
    for outcome in context.get("outcomes", []) or []:
        if not isinstance(outcome, dict):
            continue
        if str(outcome.get("tool") or "") != "send_resend_email":
            continue
        if str(outcome.get("status") or "").lower() != "ok":
            continue
        key = (
            str(outcome.get("email_id") or "").strip()
            or str(outcome.get("created_at") or "").strip()
            or str(outcome.get("message") or "").strip()
        )
        if not key or key in seen_email:
            continue
        seen_email.add(key)
        email += 1

    return {"pdf": pdf, "email": email}


def consume_daily_quota(user_id: str, increments: Dict[str, int]) -> Dict[str, Any]:
    snapshot = get_daily_quota(user_id)
    if not snapshot.get("enabled"):
        _LOGGER.info(
            "[quota] status=disabled user_id=%s backend=%s increments_tokens=%d increments_pdf=%d increments_email=%d",
            user_id,
            snapshot.get("backend", "none"),
            max(0, _as_int(increments.get("tokens"), 0)),
            max(0, _as_int(increments.get("pdf"), 0)),
            max(0, _as_int(increments.get("email"), 0)),
        )
        return {"snapshot": snapshot, "exceeded": [], "applied": {}}

    now = _utc_now()
    limits = snapshot["limits"]
    usage_before = dict(snapshot["usage"])
    usage = dict(usage_before)
    applied: Dict[str, int] = {}
    exceeded: list[str] = []

    if snapshot.get("backend") == "s3":
        usage, applied, exceeded = _s3_write_usage_atomic(
            user_id=user_id,
            now=now,
            increments=increments,
            limits=limits,
        )
    else:
        usage, applied, exceeded = _apply_quota_limits(usage, increments, limits)

    final_snapshot = {
        "enabled": True,
        "backend": snapshot.get("backend", "upstash"),
        "day": now.strftime("%Y-%m-%d"),
        "reset_at": _reset_at(now).isoformat(),
        "limits": limits,
        "usage": usage,
        "remaining": {m: max(0, limits[m] - usage.get(m, 0)) for m in _METRICS},
    }
    if final_snapshot["backend"] == "local":
        _local_write_usage(user_id, now, usage)
    elif final_snapshot["backend"] == "upstash":
        _upstash_set(
            _quota_key(user_id, now),
            {
                "day": final_snapshot["day"],
                "usage": usage,
                "updated_at": now.isoformat(),
            },
            _ttl_seconds(now),
        )
    _LOGGER.info(
        "[quota] status=ok user_id=%s backend=%s increments_tokens=%d increments_pdf=%d increments_email=%d before_tokens=%d before_pdf=%d before_email=%d after_tokens=%d after_pdf=%d after_email=%d remaining_tokens=%d remaining_pdf=%d remaining_email=%d exceeded=%s",
        user_id,
        final_snapshot["backend"],
        max(0, _as_int(increments.get("tokens"), 0)),
        max(0, _as_int(increments.get("pdf"), 0)),
        max(0, _as_int(increments.get("email"), 0)),
        max(0, _as_int(usage_before.get("tokens"), 0)),
        max(0, _as_int(usage_before.get("pdf"), 0)),
        max(0, _as_int(usage_before.get("email"), 0)),
        max(0, _as_int(final_snapshot["usage"].get("tokens"), 0)),
        max(0, _as_int(final_snapshot["usage"].get("pdf"), 0)),
        max(0, _as_int(final_snapshot["usage"].get("email"), 0)),
        max(0, _as_int(final_snapshot["remaining"].get("tokens"), 0)),
        max(0, _as_int(final_snapshot["remaining"].get("pdf"), 0)),
        max(0, _as_int(final_snapshot["remaining"].get("email"), 0)),
        ",".join(exceeded) if exceeded else "-",
    )
    return {"snapshot": final_snapshot, "exceeded": sorted(set(exceeded)), "applied": applied}


def quota_exceeded_message(metric: str, snapshot: Dict[str, Any]) -> str:
    labels = {
        "tokens": "token",
        "pdf": "PDF export",
        "email": "email",
    }
    label = labels.get(metric, metric)
    reset_at = str(snapshot.get("reset_at") or "").replace("+00:00", "Z")
    limit = _as_int((snapshot.get("limits") or {}).get(metric), 0)
    return (
        f"Daily {label} limit reached ({limit}). "
        f"Please retry after quota reset at {reset_at}."
    )
