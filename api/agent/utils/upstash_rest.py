# /app/api/agent/utils/upstash_rest.py
import asyncio
import json
import logging
import os
from functools import lru_cache
from typing import Any, Optional

import httpx

log = logging.getLogger(__name__)


class UpstashError(RuntimeError):
    pass


class UpstashRest:
    """
    Upstash Redis REST API client using POST Command-in-Body semantics:
      POST REST_URL with JSON array: ["HSET","k","f","v"]
    Docs: Upstash Redis REST API "POST Command in Body" :contentReference[oaicite:2]{index=2}
    """

    def __init__(self, base_url: str, token: str, timeout_s: float = 10.0):
        self.base_url = base_url.rstrip("/")  # REST_URL
        self.token = token
        self.timeout = httpx.Timeout(timeout_s)

    async def execute(self, command: str, *args: Any, max_retries: int = 4) -> Any:
        """
        Sends one Redis command and returns the Upstash 'result'.
        POST REST_URL with JSON array body: ["CMD", arg1, arg2, ...] :contentReference[oaicite:3]{index=3}
        """
        url = self.base_url  # IMPORTANT: no "/{command}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        payload = [command, *args]

        last_err: Optional[Exception] = None

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(max_retries + 1):
                try:
                    resp = await client.post(url, headers=headers, json=payload)
                    body_text = (resp.text or "").strip()

                    # Retry on rate limit / transient server error
                    if resp.status_code == 429 or 500 <= resp.status_code <= 599:
                        raise UpstashError(
                            f"Upstash transient HTTP {resp.status_code}. body='{body_text[:500]}'"
                        )

                    # Hard fail on non-2xx
                    if resp.status_code < 200 or resp.status_code >= 300:
                        raise UpstashError(
                            f"Upstash HTTP {resp.status_code}. body='{body_text[:500]}'"
                        )

                    if not body_text:
                        raise UpstashError("Upstash returned empty body for 2xx response.")

                    try:
                        data = resp.json()
                    except json.JSONDecodeError:
                        raise UpstashError(
                            f"Upstash returned non-JSON body for 2xx response. body='{body_text[:500]}'"
                        )

                    # Upstash error shape: {"error": "..."} :contentReference[oaicite:4]{index=4}
                    if isinstance(data, dict) and "error" in data:
                        raise UpstashError(f"Upstash error: {data.get('error')}")

                    # Success shape: {"result": ...} :contentReference[oaicite:5]{index=5}
                    if isinstance(data, dict) and "result" in data:
                        return data["result"]

                    return data

                except Exception as e:
                    last_err = e
                    if attempt >= max_retries:
                        break
                    await asyncio.sleep(0.25 * (2 ** attempt))

        raise UpstashError(f"Upstash execute failed after retries: {last_err}")

    async def pipeline(self, commands: list[list[Any]], max_retries: int = 4) -> Any:
        """
        Optional: pipelining endpoint is REST_URL/pipeline :contentReference[oaicite:6]{index=6}
        Body: [[CMD,A1,...],[CMD2,B1,...],...]
        """
        url = f"{self.base_url}/pipeline"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        last_err: Optional[Exception] = None

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(max_retries + 1):
                try:
                    resp = await client.post(url, headers=headers, json=commands)
                    body_text = (resp.text or "").strip()

                    if resp.status_code == 429 or 500 <= resp.status_code <= 599:
                        raise UpstashError(
                            f"Upstash transient HTTP {resp.status_code}. body='{body_text[:500]}'"
                        )
                    if resp.status_code < 200 or resp.status_code >= 300:
                        raise UpstashError(
                            f"Upstash HTTP {resp.status_code}. body='{body_text[:500]}'"
                        )
                    if not body_text:
                        raise UpstashError("Upstash returned empty body for 2xx response.")

                    try:
                        return resp.json()
                    except json.JSONDecodeError:
                        raise UpstashError(
                            f"Upstash returned non-JSON body for 2xx response. body='{body_text[:500]}'"
                        )

                except Exception as e:
                    last_err = e
                    if attempt >= max_retries:
                        break
                    await asyncio.sleep(0.25 * (2 ** attempt))

        raise UpstashError(f"Upstash pipeline failed after retries: {last_err}")


@lru_cache(maxsize=1)
def get_upstash() -> UpstashRest:
    """
    Singleton factory used by summary_agent.py.
    This fixes your ImportError: cannot import name 'get_upstash'.
    """
    url = (os.getenv("UPSTASH_REDIS_REST_URL") or "").strip()
    token = (os.getenv("UPSTASH_REDIS_REST_TOKEN") or "").strip()
    if not url or not token:
        raise UpstashError("Upstash env vars missing: UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN")
    return UpstashRest(url, token)
