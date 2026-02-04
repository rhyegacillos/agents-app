from __future__ import annotations

import threading

from app.repositories.trader_repository import is_market_open

_market_status_lock = threading.RLock()
_last_market_status: dict[str, str | bool | None] = {
    "status": "closed",
    "is_open": False,
    "detail": None,
}


def get_market_status() -> dict[str, str | bool | None]:
    try:
        open_now = is_market_open()
        status = {
            "status": "open" if open_now else "closed",
            "is_open": open_now,
            "detail": None,
        }
        with _market_status_lock:
            _last_market_status.update(status)
        return status
    except Exception as exc:
        with _market_status_lock:
            fallback = dict(_last_market_status)
        fallback["detail"] = f"Using last known market status due to error: {exc}"
        return fallback
