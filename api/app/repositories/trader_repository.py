from __future__ import annotations

import json
from typing import Any

from app.infrastructure.engine_loader import import_engine_module


def get_trader_definitions() -> list[dict[str, str]]:
    trading_floor = import_engine_module("trading_floor")
    return [
        {
            "name": name,
            "lastname": lastname,
            "model_name": model_name,
        }
        for name, lastname, model_name in zip(
            trading_floor.names,
            trading_floor.lastnames,
            trading_floor.short_model_names,
        )
    ]


def get_trader_account(name: str) -> dict[str, Any]:
    accounts = import_engine_module("accounts")
    account = accounts.Account.get(name)
    return json.loads(account.report())


def get_trader_logs(name: str, limit: int = 20) -> list[dict[str, str]]:
    database = import_engine_module("database")
    rows = list(database.read_log(name, last_n=limit))
    return [
        {
            "timestamp": timestamp,
            "type": log_type,
            "message": message,
        }
        for timestamp, log_type, message in rows
    ]


def reset_all_traders() -> None:
    reset_module = import_engine_module("reset")
    reset_module.reset_traders()


def is_market_open() -> bool:
    market = import_engine_module("market")
    return bool(market.is_market_open())
