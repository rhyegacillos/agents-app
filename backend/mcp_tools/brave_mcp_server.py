import os
from typing import Dict, Any

import logging
import requests
from functools import wraps
from mcp.server.fastmcp import FastMCP

from mcp_tools.bootstrap import bootstrap_mcp_process
from mcp_tools.status import update_job_status
from mcp_tools.tracing import annotate_tool_result, start_mcp_tool_span
from otel_observability import get_tracer as get_otel_tracer, set_current_span_attributes
from secret_env import get_secret_env
from tool_instructions import tool_instructions_for

bootstrap_mcp_process(log_level_env="BRAVE_LOG_LEVEL", service_label="mcp-brave")


mcp = FastMCP("Brave-Search-Service")

BRAVE_API_KEY = get_secret_env("BRAVE_API_KEY", "")

if not BRAVE_API_KEY:
    raise RuntimeError("BRAVE_API_KEY is required for Brave MCP server")

def _tool(name: str):
    def decorator(func):
        @wraps(func)
        async def wrapped(*args, **kwargs):
            with start_mcp_tool_span(name) as span:
                result = await func(*args, **kwargs)
                annotate_tool_result(span, result)
                return result
        doc = tool_instructions_for(name)
        if doc:
            wrapped.__doc__ = doc
        return mcp.tool()(wrapped)
    return decorator


@_tool("brave_web_search")
async def brave_web_search(query: str, count: int = 5) -> Dict[str, Any]:
    """
    Search the web with Brave Search API.
    Args:
        query: Search query string.
        count: Number of results (1-10).
    """
    tracer = get_otel_tracer("digital_assistant.mcp.brave")
    with tracer.start_as_current_span("brave.search.http"):
        update_job_status("Tool: Brave Search", 40)
        count = max(1, min(int(count), 10))
        set_current_span_attributes({"search.query_chars": len(query or ""), "search.count": count})
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
        set_current_span_attributes({"search.result_count": len(results)})
        logging.info("[brave] search success results=%d", len(results))
        return {"query": query, "count": count, "results": results}


if __name__ == "__main__":
    try:
        mcp.run(transport="stdio")
    except TypeError:
        mcp.run()
