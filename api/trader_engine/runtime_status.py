import json
import os
from pathlib import Path
from typing import Any


_ENGINE_DIR = Path(__file__).resolve().parent
_DEFAULT_DATA_DIR = _ENGINE_DIR.parent / "data"
_DATA_DIR = Path(os.getenv("TRADER_DATA_DIR", str(_DEFAULT_DATA_DIR))).resolve()
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_RUNTIME_STATUS_FILE = _DATA_DIR / "runtime_status.json"

_DEFAULT_RUNTIME_STATUS: dict[str, Any] = {
    "run_in_progress": False,
    "last_run_started_at": None,
    "last_run_ended_at": None,
}


def read_runtime_status() -> dict[str, Any]:
    if not _RUNTIME_STATUS_FILE.exists():
        return dict(_DEFAULT_RUNTIME_STATUS)
    try:
        raw = json.loads(_RUNTIME_STATUS_FILE.read_text(encoding="utf-8"))
        return {
            "run_in_progress": bool(raw.get("run_in_progress", False)),
            "last_run_started_at": raw.get("last_run_started_at"),
            "last_run_ended_at": raw.get("last_run_ended_at"),
        }
    except Exception:
        return dict(_DEFAULT_RUNTIME_STATUS)


def write_runtime_status(**updates: Any) -> None:
    state = read_runtime_status()
    state.update(updates)
    tmp_file = _RUNTIME_STATUS_FILE.with_suffix(".tmp")
    tmp_file.write_text(json.dumps(state), encoding="utf-8")
    tmp_file.replace(_RUNTIME_STATUS_FILE)
