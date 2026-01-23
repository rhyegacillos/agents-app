# agent/idea_generation_agent.py

from __future__ import annotations

import logging
import re
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple
import asyncio

from agent.model_fallback import generate_with_fallback

logger = logging.getLogger(__name__)

GenerateFn = Callable[[Any, str, str, str], Awaitable[str]]

_CODEFENCE_RE = re.compile(r"```")
_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
_SECTION_RE = re.compile(r"<section\b", re.IGNORECASE)
_HTML_FENCE_RE = re.compile(r"^\s*```(?:html)?\s*|\s*```\s*$", re.IGNORECASE)

def _strip_code_fences(text: str) -> str:
    if not text:
        return ""
    t = text.strip()
    if t.startswith("```"):
        # Remove opening ``` or ```html and closing ```
        t = re.sub(r"^\s*```(?:html)?\s*\n?", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\n?\s*```\s*$", "", t)
    return t.strip()


def _validate_idea_output_html(text: str) -> tuple[bool, list[str]]:
    t = (text or "").strip()
    if not t:
        return False, ["empty output"]
    if "```" in t:
        return False, ["contains code fences"]
    if len(t) < 120:
        return False, ["too short"]
    return True, []



async def generate_idea_agentic(
    *,
    generate: GenerateFn,
    client: Any,
    provider: str,
    model_chain: Sequence[str],
    system_instruction: str,
    user_content: str,
    max_attempts: int = 3,
    request_id: Optional[str] = None,
    timeout_s: float = 120.0,
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    last_errors: List[str] = []
    last_text: str = ""

    primary_model = model_chain[0] if model_chain else "unknown"

    for attempt in range(1, max_attempts + 1):
        correction = ""
        if last_errors:
            correction = (
                "\n\nIMPORTANT: Your previous output failed validation.\n"
                "Fix the issues below and output ONLY HTML (no markdown, no backticks, no extra commentary).\n"
                "Validation errors:\n- " + "\n- ".join(last_errors)
            )

        logger.info(
            f"idea_agent.attempt request_id={request_id} provider={provider} model={primary_model} "
            f"attempt={attempt}/{max_attempts}"
        )

        try:
            text, fb_meta = await generate_with_fallback(
                provider=provider,
                generate=generate,
                client=client,
                models=model_chain,
                system_instruction=system_instruction,
                user_content=user_content + correction,
                timeout_s=timeout_s,
                request_id=request_id,
            )
            last_text = _strip_code_fences(text or "")

        except (TimeoutError, asyncio.TimeoutError) as e:
            logger.warning(
                f"idea_agent.timeout_reached_retrying request_id={request_id} provider={provider} "
                f"model={primary_model} attempt={attempt} timeout_s={timeout_s} next_attempt={attempt+1}/{max_attempts}"
            )
            await asyncio.sleep(0.5)
            last_errors = [f"timeout after {timeout_s}s"]
            continue

        except Exception as e:
            logger.exception(
                f"idea_agent.generate_error request_id={request_id} provider={provider} "
                f"model={primary_model} attempt={attempt} error_type={type(e).__name__} error={e}"
            )
            last_errors = [f"{type(e).__name__}: {e}"]
            continue

        ok, errors = _validate_idea_output_html(last_text)
        if ok:
            total_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                f"idea_agent.success request_id={request_id} provider={provider} model={primary_model} "
                f"attempt={attempt} total_ms={total_ms}"
            )
            return {
                "text": last_text, 
                "meta": {"attempts": attempt, "fallback_used": fb_meta.get("fallback_used", False)},
                "usage": fb_meta.get("usage", {})
            }

        logger.warning(
            f"idea_agent.validation_failed request_id={request_id} provider={provider} model={primary_model} "
            f"attempt={attempt} errors={errors}"
        )
        last_errors = errors

    total_ms = int((time.perf_counter() - t0) * 1000)
    logger.error(
        f"idea_agent.fallback request_id={request_id} provider={provider} model={primary_model} total_ms={total_ms} errors={last_errors}"
    )
    return {"text": "Error: No valid HTML produced.", "meta": {"attempts": max_attempts, "errors": last_errors}}
