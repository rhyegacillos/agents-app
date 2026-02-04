from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.infrastructure.engine_loader import engine_static_dir
from app.schemas import (
    LogEntry,
    MarketStatus,
    MessageResponse,
    SchedulerStatus,
    StartSchedulerRequest,
    TraderDetail,
    TraderListResponse,
)
from app.services.scheduler_service import scheduler_manager
from app.services.market_service import get_market_status
from app.services.trader_service import (
    get_trader_detail,
    get_trader_logs,
    list_trader_summaries,
    reset_traders as reset_all_traders,
)
from app.repositories.trader_repository import is_market_open


def _scheduler_payload(status: dict[str, object]) -> dict[str, object]:
    payload = dict(status)
    payload["read_only_mode"] = settings.read_only_mode
    return payload


async def _market_auto_trade_loop(stop_event: asyncio.Event) -> None:
    """Keep trading process aligned with market open/closed status."""
    interval = settings.market_watch_interval_sec
    while not stop_event.is_set():
        try:
            market_open = bool(is_market_open())
            status = scheduler_manager.status()
            if market_open and not status["running"]:
                scheduler_manager.start(run_even_when_market_is_closed=False)
            elif not market_open and status["running"]:
                scheduler_manager.stop()
        except Exception:
            # Leave current scheduler state untouched if market lookup fails.
            pass

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue


@asynccontextmanager
async def lifespan(_: FastAPI):
    auto_trade_stop = asyncio.Event()
    auto_trade_task: asyncio.Task[None] | None = None
    if settings.auto_trade_by_market:
        auto_trade_task = asyncio.create_task(_market_auto_trade_loop(auto_trade_stop))
    yield
    auto_trade_stop.set()
    if auto_trade_task is not None:
        auto_trade_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await auto_trade_task
    scheduler_manager.stop()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/traders", response_model=TraderListResponse)
async def list_traders() -> TraderListResponse:
    return TraderListResponse(traders=list_trader_summaries())


@app.get("/api/traders/{name}", response_model=TraderDetail)
async def get_trader(name: str, logs_limit: int = Query(default=50, ge=1, le=200)) -> TraderDetail:
    try:
        detail = get_trader_detail(name, limit=logs_limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TraderDetail(**detail)


@app.get("/api/traders/{name}/logs", response_model=list[LogEntry])
async def trader_logs(name: str, limit: int = Query(default=50, ge=1, le=200)) -> list[LogEntry]:
    try:
        logs = get_trader_logs(name, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to load logs: {exc}") from exc
    return [LogEntry(**item) for item in logs]


@app.post("/api/scheduler/start", response_model=SchedulerStatus)
async def start_scheduler(payload: StartSchedulerRequest | None = None) -> SchedulerStatus:
    if settings.read_only_mode:
        raise HTTPException(status_code=403, detail="Trade controls are disabled in READ_ONLY_MODE.")
    try:
        run_even_when_closed = payload.run_even_when_market_is_closed if payload else None
        run_every_n_minutes = payload.run_every_n_minutes if payload else None
        status = scheduler_manager.start(
            run_even_when_market_is_closed=run_even_when_closed,
            run_every_n_minutes=run_every_n_minutes,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to start scheduler: {exc}") from exc
    return SchedulerStatus(**_scheduler_payload(status))


@app.post("/api/scheduler/stop", response_model=SchedulerStatus)
async def stop_scheduler() -> SchedulerStatus:
    if settings.read_only_mode:
        raise HTTPException(status_code=403, detail="Trade controls are disabled in READ_ONLY_MODE.")
    return SchedulerStatus(**_scheduler_payload(scheduler_manager.stop()))


@app.get("/api/scheduler/status", response_model=SchedulerStatus)
async def scheduler_status() -> SchedulerStatus:
    return SchedulerStatus(**_scheduler_payload(scheduler_manager.status()))


@app.get("/api/market/status", response_model=MarketStatus)
async def market_status() -> MarketStatus:
    return MarketStatus(**get_market_status())


@app.post("/api/reset", response_model=MessageResponse)
async def reset_traders() -> MessageResponse:
    if settings.read_only_mode:
        raise HTTPException(status_code=403, detail="Trade controls are disabled in READ_ONLY_MODE.")
    try:
        reset_all_traders()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to reset traders: {exc}") from exc
    return MessageResponse(message="Trader accounts reset.")


STATIC_DIR = engine_static_dir()
if STATIC_DIR.exists():
    # Serve exported Next.js app from the same container and host.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
