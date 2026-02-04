from __future__ import annotations

import importlib
import sys
from pathlib import Path

from app.core.config import settings


_BOOTSTRAPPED = False


def bootstrap_engine() -> None:
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return

    engine_dir = settings.trader_engine_dir
    if not engine_dir.exists():
        raise RuntimeError(f"Missing trader engine directory: {engine_dir}")

    if str(engine_dir) not in sys.path:
        sys.path.insert(0, str(engine_dir))

    _BOOTSTRAPPED = True


def import_engine_module(name: str):
    bootstrap_engine()
    return importlib.import_module(name)


def engine_static_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "static"
