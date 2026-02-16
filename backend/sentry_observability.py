import logging
import os
from typing import Any, Dict


_SENTRY_IMPORTED = False
try:
    import sentry_sdk
    from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    _SENTRY_IMPORTED = True
except Exception:  # pragma: no cover - optional dependency fallback
    sentry_sdk = None  # type: ignore[assignment]
    AwsLambdaIntegration = None  # type: ignore[assignment]
    FastApiIntegration = None  # type: ignore[assignment]
    LoggingIntegration = None  # type: ignore[assignment]


_INITIALIZED = False


def _parse_float(raw: str, default: float) -> float:
    try:
        return float(raw.strip())
    except Exception:
        return default


def init_sentry() -> bool:
    global _INITIALIZED
    if _INITIALIZED:
        return True

    dsn = (os.getenv("SENTRY_DSN") or "").strip()
    if not dsn:
        logging.info("[sentry] disabled (SENTRY_DSN missing)")
        return False
    if not _SENTRY_IMPORTED:
        logging.warning("[sentry] sentry_sdk not installed; integration disabled")
        return False

    traces_sample_rate = _parse_float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"), 0.1)
    profiles_sample_rate = _parse_float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0"), 0.0)
    environment = (
        (os.getenv("SENTRY_ENVIRONMENT") or "").strip()
        or (os.getenv("ENVIRONMENT") or "").strip()
        or "dev"
    )
    release = (os.getenv("SENTRY_RELEASE") or "").strip() or None
    service_name = (os.getenv("SENTRY_SERVICE") or "").strip() or "digital-assistant-backend"

    integrations = [
        AwsLambdaIntegration(timeout_warning=True),
        FastApiIntegration(transaction_style="endpoint"),
        LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
    ]

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        traces_sample_rate=max(0.0, min(1.0, traces_sample_rate)),
        profiles_sample_rate=max(0.0, min(1.0, profiles_sample_rate)),
        send_default_pii=False,
        integrations=integrations,
    )
    sentry_sdk.set_tag("service", service_name)
    _INITIALIZED = True
    logging.info(
        "[sentry] initialized service=%s env=%s traces=%.3f profiles=%.3f",
        service_name,
        environment,
        traces_sample_rate,
        profiles_sample_rate,
    )
    return True


def set_sentry_tags(tags: Dict[str, Any]) -> None:
    if not _INITIALIZED or sentry_sdk is None:
        return
    for key, value in (tags or {}).items():
        if value is None:
            continue
        sentry_sdk.set_tag(str(key), str(value))


def set_sentry_user(user_id: str | None = None) -> None:
    if not _INITIALIZED or sentry_sdk is None:
        return
    if not user_id:
        sentry_sdk.set_user(None)
        return
    sentry_sdk.set_user({"id": user_id})


def capture_sentry_exception(exc: Exception) -> None:
    if not _INITIALIZED or sentry_sdk is None:
        return
    sentry_sdk.capture_exception(exc)

