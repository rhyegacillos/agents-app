from dataclasses import dataclass
import os
from pathlib import Path


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed


@dataclass(frozen=True)
class Settings:
    app_name: str
    frontend_origin: str
    trader_engine_dir: Path
    read_only_mode: bool
    auto_trade_by_market: bool
    market_watch_interval_sec: int


_DEFAULT_ENGINE_DIR = Path(__file__).resolve().parents[2] / "trader_engine"

settings = Settings(
    app_name=os.getenv("APP_NAME", "Autonomous Trader API"),
    frontend_origin=os.getenv("FRONTEND_ORIGIN", "http://localhost:8000"),
    trader_engine_dir=Path(os.getenv("TRADER_ENGINE_DIR", str(_DEFAULT_ENGINE_DIR))).resolve(),
    read_only_mode=_env_bool("READ_ONLY_MODE", False),
    auto_trade_by_market=_env_bool("AUTO_TRADE_BY_MARKET", False),
    market_watch_interval_sec=max(10, _env_int("MARKET_WATCH_INTERVAL_SEC", 60)),
)
