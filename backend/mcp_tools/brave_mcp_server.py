import os
import atexit
from typing import Dict, Any

import sys
import logging
import requests
from mcp.server.fastmcp import FastMCP

from mcp_tools.status import update_job_status
from tool_instructions import tool_instructions_for

try:
    from otel_observability import init_otel, flush_otel
except Exception:  # pragma: no cover
    init_otel = None
    flush_otel = None

logging.basicConfig(stream=sys.stderr, level=os.getenv("BRAVE_LOG_LEVEL", "INFO").upper())
logging.getLogger("mcp.server.lowlevel.server").setLevel(logging.WARNING)
logging.getLogger("mcp.server.fastmcp").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
if init_otel:
    try:
        init_otel()
        if flush_otel:
            atexit.register(flush_otel)
    except Exception:
        logging.exception("[otel] mcp-brave init failed")


mcp = FastMCP("Brave-Search-Service")

BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "").strip()

if not BRAVE_API_KEY:
    raise RuntimeError("BRAVE_API_KEY is required for Brave MCP server")

def _tool(name: str):
    def decorator(func):
        doc = tool_instructions_for(name)
        if doc:
            func.__doc__ = doc
        return mcp.tool()(func)
    return decorator


@_tool("brave_web_search")
async def brave_web_search(query: str, count: int = 5) -> Dict[str, Any]:
    """
    Search the web with Brave Search API.
    Args:
        query: Search query string.
        count: Number of results (1-10).
    """
    update_job_status("Tool: Brave Search", 40)
    count = max(1, min(int(count), 10))
    logging.info("[brave] search start q=%s count=%s", query, count)
    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": BRAVE_API_KEY,
        "User-Agent": "DigitalAssistant/1.0",
    }
    params = {"q": query, "count": count}
    response = requests.get(url, headers=headers, params=params, timeout=20)
    response.raise_for_status()
    data = response.json()
    results = []
    for item in (data.get("web", {}) or {}).get("results", [])[:count]:
        results.append(
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "description": item.get("description"),
            }
        )
    logging.info("[brave] search success results=%d", len(results))
    return {"query": query, "count": count, "results": results}


if __name__ == "__main__":
    try:
        mcp.run(transport="stdio")
    except TypeError:
        mcp.run()
