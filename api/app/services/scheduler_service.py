from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any

from app.core.config import settings
from app.infrastructure.engine_loader import bootstrap_engine

_DEFAULT_RUNTIME_STATUS: dict[str, Any] = {
    "run_in_progress": False,
    "last_run_started_at": None,
    "last_run_ended_at": None,
}


def _runtime_status_path() -> Path:
    data_dir = Path(
        os.getenv("TRADER_DATA_DIR", str(settings.trader_engine_dir.parent / "data"))
    ).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "runtime_status.json"


def _read_runtime_status() -> dict[str, Any]:
    path = _runtime_status_path()
    if not path.exists():
        return dict(_DEFAULT_RUNTIME_STATUS)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {
            "run_in_progress": bool(raw.get("run_in_progress", False)),
            "last_run_started_at": raw.get("last_run_started_at"),
            "last_run_ended_at": raw.get("last_run_ended_at"),
        }
    except Exception:
        return dict(_DEFAULT_RUNTIME_STATUS)


def _write_runtime_status(**updates: Any) -> None:
    state = _read_runtime_status()
    state.update(updates)
    path = _runtime_status_path()
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(state), encoding="utf-8")
    tmp_path.replace(path)


class SchedulerManager:
    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._started_at: datetime | None = None
        self._lock = threading.RLock()

    def status(self) -> dict[str, Any]:
        with self._lock:
            running = self._process is not None and self._process.poll() is None
            runtime_status = _read_runtime_status()
            run_in_progress = running and bool(runtime_status.get("run_in_progress", False))
            return {
                "running": running,
                "pid": self._process.pid if running and self._process else None,
                "started_at": self._started_at.isoformat() if running and self._started_at else None,
                "run_in_progress": run_in_progress,
                "last_run_started_at": runtime_status.get("last_run_started_at"),
                "last_run_ended_at": runtime_status.get("last_run_ended_at"),
            }

    def start(
        self,
        run_even_when_market_is_closed: bool | None = None,
        run_every_n_minutes: int | None = None,
    ) -> dict[str, Any]:
        bootstrap_engine()
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return self.status()

            env = os.environ.copy()
            if run_even_when_market_is_closed is not None:
                env["RUN_EVEN_WHEN_MARKET_IS_CLOSED"] = "true" if run_even_when_market_is_closed else "false"
            if run_every_n_minutes is not None:
                env["RUN_EVERY_N_MINUTES"] = str(run_every_n_minutes)
            _write_runtime_status(run_in_progress=False)
            self._process = subprocess.Popen(
                [sys.executable, "trading_floor.py"],
                cwd=str(settings.trader_engine_dir),
                env=env,
            )
            self._started_at = datetime.now(timezone.utc)
            return self.status()

    def stop(self, timeout_seconds: int = 10) -> dict[str, Any]:
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                self._process = None
                self._started_at = None
                _write_runtime_status(run_in_progress=False)
                runtime_status = _read_runtime_status()
                return {
                    "running": False,
                    "pid": None,
                    "started_at": None,
                    "run_in_progress": False,
                    "last_run_started_at": runtime_status.get("last_run_started_at"),
                    "last_run_ended_at": runtime_status.get("last_run_ended_at"),
                }

            self._process.terminate()
            try:
                self._process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2)

            self._process = None
            self._started_at = None
            _write_runtime_status(run_in_progress=False)
            runtime_status = _read_runtime_status()
            return {
                "running": False,
                "pid": None,
                "started_at": None,
                "run_in_progress": False,
                "last_run_started_at": runtime_status.get("last_run_started_at"),
                "last_run_ended_at": runtime_status.get("last_run_ended_at"),
            }


scheduler_manager = SchedulerManager()
