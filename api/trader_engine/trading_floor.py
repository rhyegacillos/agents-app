from traders import Trader
from typing import List
import asyncio
from datetime import datetime, timezone
from tracers import LogTracer
from agents import add_trace_processor
from market import is_market_open
from runtime_status import write_runtime_status
from dotenv import load_dotenv
import os

load_dotenv(override=True)

RUN_EVERY_N_MINUTES = int(os.getenv("RUN_EVERY_N_MINUTES", "60"))
RUN_EVEN_WHEN_MARKET_IS_CLOSED = (
    os.getenv("RUN_EVEN_WHEN_MARKET_IS_CLOSED", "false").strip().lower() == "true"
)
USE_MANY_MODELS = os.getenv("USE_MANY_MODELS", "false").strip().lower() == "true"

names = ["Warren", "George", "Ray", "Cathie"]
lastnames = ["Patience", "Bold", "Systematic", "Crypto"]

if USE_MANY_MODELS:
    model_names = [
        "gpt-5-nano",
        "deepseek-chat",
        "gemini-2.5-flash",
        "grok-4-1-fast",
    ]
    short_model_names = ["OpenAI", "DeepSeek", "Gemini", "Grok"]
else:
    model_names = ["gpt-4o-mini"] * 4
    short_model_names = ["OpenAI"] * 4


def create_traders() -> List[Trader]:
    traders = []
    for name, lastname, model_name in zip(names, lastnames, model_names):
        traders.append(Trader(name, lastname, model_name))
    return traders


async def run_every_n_minutes():
    add_trace_processor(LogTracer())
    traders = create_traders()
    write_runtime_status(run_in_progress=False)
    try:
        while True:
            if RUN_EVEN_WHEN_MARKET_IS_CLOSED or is_market_open():
                cycle_started_at = datetime.now(timezone.utc).isoformat()
                write_runtime_status(
                    run_in_progress=True,
                    last_run_started_at=cycle_started_at,
                )
                try:
                    await asyncio.gather(*[trader.run() for trader in traders])
                finally:
                    cycle_ended_at = datetime.now(timezone.utc).isoformat()
                    write_runtime_status(
                        run_in_progress=False,
                        last_run_ended_at=cycle_ended_at,
                    )
            else:
                write_runtime_status(run_in_progress=False)
                print("Market is closed, skipping run")
            await asyncio.sleep(RUN_EVERY_N_MINUTES * 60)
    finally:
        await asyncio.gather(*(trader.close_mcp_servers() for trader in traders), return_exceptions=True)


if __name__ == "__main__":
    print(f"Starting scheduler to run every {RUN_EVERY_N_MINUTES} minutes")
    asyncio.run(run_every_n_minutes())
