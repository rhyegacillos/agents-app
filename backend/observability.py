import logging
import uuid
from contextvars import ContextVar
from typing import Optional, Tuple


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

