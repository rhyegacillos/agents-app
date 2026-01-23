import asyncio
import re
import time
import logging
from typing import Any, Awaitable, Callable, Dict, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)
GenerateFn = Callable[[Any, str, str, str], Awaitable[str]]

_TRANSIENT_PATTERNS = [
    r"\b429\b",
    r"rate limit",
    r"too many requests",
    r"capacity",
    r"overloaded",
    r"\b503\b",
    r"\b502\b",
    r"\b504\b",
    r"service unavailable",
    r"temporarily unavailable",
    r"connect",
    r"connection",
    r"network",
]

def _is_transient_non_timeout(exc: Exception) -> bool:
    msg = (str(exc) or "").lower()
    return any(re.search(p, msg) for p in _TRANSIENT_PATTERNS)

async def generate_with_fallback(
    *,
    provider: str,
    generate: GenerateFn,
    client: Any,
    models: Sequence[str],
    system_instruction: str,
    user_content: str,
    timeout_s: float = 120.0,
    request_id: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    last_exc: Optional[Exception] = None

    for idx, model in enumerate(models, start=1):
        t0 = time.perf_counter()
        logger.info(f"llm.try provider={provider} model={model} try_index={idx} request_id={request_id}")

        try:
            result = await asyncio.wait_for(
                generate(client, model, system_instruction, user_content),
                timeout=timeout_s,
            )
            
            # handle tuple (text, usage) or string (legacy/error)
            if isinstance(result, tuple) and len(result) == 2:
                text, usage = result
            else:
                text, usage = result, {}

            latency_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                f"llm.success provider={provider} model={model} try_index={idx} "
                f"fallback_used={idx>1} request_id={request_id}"
            )

            return text, {"provider": provider, "model_used": model, "fallback_used": idx > 1, "try_index": idx, "usage": usage}

        except Exception as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)

            # TIMEOUT => DO NOT FALLBACK. Let caller retry same model.
            if isinstance(e, (TimeoutError, asyncio.TimeoutError)):
                logger.warning(f"llm.timeout provider={provider} model={model} try_index={idx} request_id={request_id} timeout_s={timeout_s}")

                raise

            transient = _is_transient_non_timeout(e)
            logger.warning(f"llm.error provider={provider} model={model} try_index={idx} request_id={request_id} err={type(e).__name__}: {e}")

            last_exc = e
            if not transient:
                raise  # fail fast

            # transient non-timeout error => fallback to next model
            continue

    raise RuntimeError(f"All models failed (provider={provider}). Last error: {last_exc}")
