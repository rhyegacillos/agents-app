import atexit
import logging
import os
import sys
from typing import Iterable

try:
    from otel_observability import flush_otel, init_otel
except Exception:  # pragma: no cover - keep MCP tools resilient if OTel deps are unavailable
    flush_otel = None
    init_otel = None


_DEFAULT_NOISY_LOGGERS = (
    "mcp.server.lowlevel.server",
    "mcp.server.fastmcp",
    "httpx",
)


def _parse_level(raw: str, fallback: str) -> int:
    level_name = (raw or fallback).upper()
    return getattr(logging, level_name, logging.INFO)


def bootstrap_mcp_process(
    *,
    log_level_env: str,
    default_level: str = "INFO",
    service_label: str,
    noisy_loggers: Iterable[str] = _DEFAULT_NOISY_LOGGERS,
) -> None:
    """
    Configure a consistent logging/OTel baseline for MCP subprocesses.
    """
    logging.basicConfig(
        stream=sys.stderr,
        level=_parse_level(os.getenv(log_level_env, default_level), default_level),
    )
    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    if not init_otel:
        return
    try:
        init_otel()
        if flush_otel:
            atexit.register(flush_otel)
    except Exception:
        logging.exception("[otel] %s init failed", service_label)
