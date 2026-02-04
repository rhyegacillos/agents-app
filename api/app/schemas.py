from pydantic import BaseModel, Field
from typing import Any


class LogEntry(BaseModel):
    timestamp: str
    type: str
    message: str


class TraderSummary(BaseModel):
    name: str
    lastname: str
    model_name: str
    balance: float
    total_portfolio_value: float
    total_profit_loss: float
    holdings_count: int
    transactions_count: int


class TraderDetail(BaseModel):
    summary: TraderSummary
    account: dict[str, Any]
    logs: list[LogEntry]


class TraderListResponse(BaseModel):
    traders: list[TraderSummary]


class SchedulerStatus(BaseModel):
    running: bool
    pid: int | None = None
    started_at: str | None = None
    run_in_progress: bool = False
    last_run_started_at: str | None = None
    last_run_ended_at: str | None = None
    read_only_mode: bool = False


class StartSchedulerRequest(BaseModel):
    run_even_when_market_is_closed: bool | None = None
    run_every_n_minutes: int | None = Field(default=None, ge=1, le=1440)


class MarketStatus(BaseModel):
    status: str
    is_open: bool | None = None
    detail: str | None = None


class MessageResponse(BaseModel):
    message: str
