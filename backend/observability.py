import logging
import json
import os
import re
import uuid
from datetime import datetime, timezone
from contextvars import ContextVar
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


TRACE_ID: ContextVar[str] = ContextVar("trace_id", default="-")
JOB_ID: ContextVar[str] = ContextVar("job_id", default="-")


def new_trace_id() -> str:
    return uuid.uuid4().hex


def set_trace_id(trace_id: Optional[str]) -> Tuple[ContextVar, object]:
    token = TRACE_ID.set(trace_id or "-")
    return TRACE_ID, token


def reset_trace_id(token: object) -> None:
    TRACE_ID.reset(token)


def set_job_id(job_id: Optional[str]) -> Tuple[ContextVar, object]:
    token = JOB_ID.set(job_id or "-")
    return JOB_ID, token


def reset_job_id(token: object) -> None:
    JOB_ID.reset(token)


def install_logging() -> None:
    # Centralized so Lambda/API/worker all get consistent context fields.
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.trace_id = TRACE_ID.get()
        record.job_id = JOB_ID.get()
        return record

    logging.setLogRecordFactory(record_factory)


_SAFE_VALUE_RE = re.compile(r"^[A-Za-z0-9._:/@-]+$")
_DEFAULT_TZ_NAME = (os.getenv("APP_TIMEZONE") or "Asia/Manila").strip() or "Asia/Manila"
try:
    _APP_TZ = ZoneInfo(_DEFAULT_TZ_NAME)
except ZoneInfoNotFoundError:
    _APP_TZ = timezone.utc
    _DEFAULT_TZ_NAME = "UTC"


def _fmt_field_value(value: object) -> str:
    if value is None:
        return ""
    raw = str(value)
    if not raw:
        return '""'
    if _SAFE_VALUE_RE.match(raw):
        return raw
    return json.dumps(raw, ensure_ascii=True)


def _coerce_json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_coerce_json_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _coerce_json_value(v) for k, v in value.items()}
    return str(value)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=_APP_TZ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", "-"),
            "job_id": getattr(record, "job_id", "-"),
        }
        event_name = getattr(record, "event", None)
        if event_name:
            payload["event"] = str(event_name)
        fields = getattr(record, "log_fields", None)
        if isinstance(fields, dict) and fields:
            payload["fields"] = _coerce_json_value(fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def log_event(event: str, *, level: int = logging.INFO, **fields: object) -> None:
    normalized_fields = {k: _coerce_json_value(v) for k, v in fields.items() if v is not None}
    parts = [f"event={event}"]
    for key, value in normalized_fields.items():
        parts.append(f"{key}={_fmt_field_value(value)}")
    logging.log(
        level,
        " ".join(parts),
        extra={"event": event, "log_fields": normalized_fields},
    )


def app_timezone_name() -> str:
    return _DEFAULT_TZ_NAME


def now_local() -> datetime:
    return datetime.now(_APP_TZ)


def now_local_iso() -> str:
    return now_local().isoformat()
