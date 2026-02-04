from polygon import RESTClient
from dotenv import load_dotenv
import os
from datetime import datetime
import random
import threading
import time
from database import write_market, read_market
from functools import lru_cache
from datetime import timezone

load_dotenv(override=True)

polygon_api_key = os.getenv("POLYGON_API_KEY")
polygon_plan = os.getenv("POLYGON_PLAN")
polygon_failure_cooldown_seconds = int(os.getenv("POLYGON_FAILURE_COOLDOWN_SECONDS", "600"))

is_paid_polygon = polygon_plan == "paid"
is_realtime_polygon = polygon_plan == "realtime"

_polygon_state_lock = threading.RLock()
_polygon_cooldown_until_ts = 0.0
_polygon_last_skip_log_ts = 0.0
_last_known_prices: dict[str, float] = {}


def is_market_open() -> bool:
    client = RESTClient(polygon_api_key)
    market_status = client.get_market_status()
    return market_status.market == "open"


def get_all_share_prices_polygon_eod() -> dict[str, float]:
    """With much thanks to student Reema R. for fixing the timezone issue with this!"""
    client = RESTClient(polygon_api_key)

    probe = client.get_previous_close_agg("SPY")[0]
    last_close = datetime.fromtimestamp(probe.timestamp / 1000, tz=timezone.utc).date()

    results = client.get_grouped_daily_aggs(last_close, adjusted=True, include_otc=False)
    return {result.ticker: result.close for result in results}


@lru_cache(maxsize=2)
def get_market_for_prior_date(today):
    market_data = read_market(today)
    if not market_data:
        market_data = get_all_share_prices_polygon_eod()
        write_market(today, market_data)
    return market_data


def get_share_price_polygon_eod(symbol) -> float:
    today = datetime.now().date().strftime("%Y-%m-%d")
    market_data = get_market_for_prior_date(today)
    return market_data.get(symbol, 0.0)


def get_share_price_polygon_min(symbol) -> float:
    client = RESTClient(polygon_api_key)
    result = client.get_snapshot_ticker("stocks", symbol)
    return result.min.close or result.prev_day.close


def get_share_price_polygon(symbol) -> float:
    if is_paid_polygon:
        return get_share_price_polygon_min(symbol)
    else:
        return get_share_price_polygon_eod(symbol)


def get_share_price(symbol) -> float:
    global _polygon_cooldown_until_ts, _polygon_last_skip_log_ts
    normalized_symbol = symbol.upper()
    if polygon_api_key:
        now = time.time()
        with _polygon_state_lock:
            cooldown_until = _polygon_cooldown_until_ts
            last_skip_log = _polygon_last_skip_log_ts
            last_known_price = _last_known_prices.get(normalized_symbol)
        if now < cooldown_until:
            if now - last_skip_log >= 60:
                with _polygon_state_lock:
                    _polygon_last_skip_log_ts = now
                remaining = int(cooldown_until - now)
                if last_known_price is not None and last_known_price > 0:
                    print(f"Polygon cooldown active ({remaining}s remaining); using last known price")
                else:
                    print(f"Polygon cooldown active ({remaining}s remaining); using a random number")
            if last_known_price is not None and last_known_price > 0:
                return float(last_known_price)
            return float(random.randint(1, 100))
        try:
            price = float(get_share_price_polygon(symbol))
            if price > 0:
                with _polygon_state_lock:
                    _last_known_prices[normalized_symbol] = price
            return price
        except Exception as e:
            with _polygon_state_lock:
                _polygon_cooldown_until_ts = time.time() + polygon_failure_cooldown_seconds
                _polygon_last_skip_log_ts = time.time()
                last_known_price = _last_known_prices.get(normalized_symbol)
            if last_known_price is not None and last_known_price > 0:
                print(
                    f"Was not able to use the polygon API due to {e}; "
                    f"cooldown {polygon_failure_cooldown_seconds}s; using last known price"
                )
                return float(last_known_price)
            print(
                f"Was not able to use the polygon API due to {e}; "
                f"cooldown {polygon_failure_cooldown_seconds}s; using a random number"
            )
    return float(random.randint(1, 100))
