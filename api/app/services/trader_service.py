from __future__ import annotations

from typing import Any

from app.repositories.trader_repository import (
    get_trader_account,
    get_trader_definitions,
    get_trader_logs,
    reset_all_traders,
)


def build_trader_summary(meta: dict[str, str], account: dict[str, Any]) -> dict[str, Any]:
    holdings = account.get("holdings", {}) or {}
    transactions = account.get("transactions", []) or []
    cash_balance = float(account.get("cash_balance", account.get("balance", 0.0)))
    total_equity = float(account.get("total_equity", account.get("total_portfolio_value", 0.0)))
    holdings_market_value = float(
        account.get("holdings_market_value", max(0.0, total_equity - cash_balance))
    )
    return {
        **meta,
        "balance": cash_balance,
        "cash_balance": cash_balance,
        "holdings_market_value": holdings_market_value,
        "total_equity": total_equity,
        "total_portfolio_value": total_equity,
        "total_profit_loss": float(account.get("total_profit_loss", 0.0)),
        "holdings_count": len(holdings),
        "transactions_count": len(transactions),
    }


def list_trader_summaries() -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for meta in get_trader_definitions():
        account = get_trader_account(meta["name"])
        summaries.append(build_trader_summary(meta, account))
    return summaries


def get_trader_detail(name: str, limit: int = 20) -> dict[str, Any]:
    trader_definitions = get_trader_definitions()
    meta = next(
        (item for item in trader_definitions if item["name"].lower() == name.lower()),
        None,
    )
    if meta is None:
        raise ValueError(f"Unknown trader: {name}")
    account = get_trader_account(meta["name"])
    return {
        "summary": build_trader_summary(meta, account),
        "account": account,
        "logs": get_trader_logs(meta["name"], limit=limit),
    }


def reset_traders() -> None:
    reset_all_traders()
