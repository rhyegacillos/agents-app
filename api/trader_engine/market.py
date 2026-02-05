from polygon import RESTClient
from dotenv import load_dotenv
import os
from datetime import datetime
import re
import sys
import httpx
from database import write_market, read_market
from functools import lru_cache
from datetime import timezone

load_dotenv(override=True)

polygon_api_key = os.getenv("POLYGON_API_KEY")
polygon_plan = os.getenv("POLYGON_PLAN")
brave_api_key = os.getenv("BRAVE_API_KEY")
brave_price_timeout_seconds = float(os.getenv("BRAVE_PRICE_TIMEOUT_SECONDS", "8"))

is_paid_polygon = polygon_plan == "paid"
is_realtime_polygon = polygon_plan == "realtime"

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


def _extract_price_candidates(text: str) -> list[tuple[float, int]]:
    """Extract (price, score) candidates from free-form web text."""
    if not text:
        return []

    lowered = text.lower()
    candidates: list[tuple[float, int]] = []

    for match in re.finditer(r"\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?)", text):
        value_text = match.group(1).replace(",", "")
        try:
            price = float(value_text)
        except ValueError:
            continue
        if price <= 0 or price > 10000:
            continue
        candidates.append((price, 5))

    for match in re.finditer(
        r"(?:price|close|last|quote)\s*[:=]?\s*\$?\s*([0-9]{1,4}(?:\.[0-9]+)?)",
        lowered,
    ):
        value_text = match.group(1).replace(",", "")
        try:
            price = float(value_text)
        except ValueError:
            continue
        if price <= 0 or price > 10000:
            continue
        candidates.append((price, 4))

    for match in re.finditer(r"\b([0-9]{1,4}(?:\.[0-9]+)?)\b", text):
        value_text = match.group(1)
        try:
            price = float(value_text)
        except ValueError:
            continue
        if price <= 0 or price > 10000:
            continue
        start = max(0, match.start() - 24)
        end = min(len(lowered), match.end() + 24)
        context = lowered[start:end]
        if any(token in context for token in ("price", "close", "last", "quote", "usd")):
            candidates.append((price, 2))

    return candidates


def get_share_price_brave(symbol: str) -> float:
    if not brave_api_key:
        raise RuntimeError("BRAVE_API_KEY is not set")

    query = f"{symbol.upper()} stock price previous close"
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": brave_api_key,
    }
    params = {
        "q": query,
        "count": 8,
        "country": "US",
        "search_lang": "en",
        "safesearch": "off",
    }

    with httpx.Client(timeout=brave_price_timeout_seconds) as client:
        response = client.get("https://api.search.brave.com/res/v1/web/search", headers=headers, params=params)
        response.raise_for_status()
        payload = response.json()

    results = (payload.get("web") or {}).get("results") or []
    scored_candidates: list[tuple[int, float]] = []
    for result in results:
        texts: list[str] = []
        title = result.get("title")
        description = result.get("description")
        extra_snippets = result.get("extra_snippets") or []
        if isinstance(title, str):
            texts.append(title)
        if isinstance(description, str):
            texts.append(description)
        if isinstance(extra_snippets, list):
            texts.extend([snippet for snippet in extra_snippets if isinstance(snippet, str)])

        for text in texts:
            for price, score in _extract_price_candidates(text):
                scored_candidates.append((score, price))

    if not scored_candidates:
        raise RuntimeError(f"No parseable Brave price found for {symbol.upper()}")

    scored_candidates.sort(key=lambda item: item[0], reverse=True)
    return float(scored_candidates[0][1])


def get_share_price_with_source(symbol: str) -> tuple[float, str]:
    normalized_symbol = symbol.upper()
    if polygon_api_key:
        try:
            price = float(get_share_price_polygon(symbol))
            if price > 0:
                _last_known_prices[normalized_symbol] = price
            return price, "POLYGON"
        except Exception as e:
            print(f"Polygon Exception: {e}", file=sys.stderr, flush=True)
    else:
        print(f"Polygon Not found: {polygon_api_key}", file=sys.stderr, flush=True)

    last_known_price = _last_known_prices.get(normalized_symbol)
    if last_known_price is not None and last_known_price > 0:
        print(
            f"Using cached last known price for {normalized_symbol}: {last_known_price}",
            file=sys.stderr,
            flush=True,
        )
        return float(last_known_price), "CACHE"

    try:
        brave_price = float(get_share_price_brave(normalized_symbol))
        if brave_price > 0:
            _last_known_prices[normalized_symbol] = brave_price
            return brave_price, "WEB"
    except Exception as e:
        print(f"Brave Exception: {e}", file=sys.stderr, flush=True)

    print(
        f"Unable to find market price for {normalized_symbol} via Polygon/Cache/Web",
        file=sys.stderr,
        flush=True,
    )
    return 0.0, "UNAVAILABLE"


def get_share_price(symbol) -> float:
    price, _source = get_share_price_with_source(symbol)
    return price
