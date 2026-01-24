from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

GenerateFn = Callable[[Any, str, str, str], Awaitable[Tuple[str, Dict[str, Any]]]]
ExtractJsonFn = Callable[[str], Optional[Dict[str, Any]]]

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", value)).strip()


def _coerce_text(value: Any, max_len: int = 4000) -> str:
    text = _strip_html(str(value)) if value is not None else ""
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _fallback_report() -> Dict[str, Any]:
    return {
        "summary": "The runs show multiple viable directions with different tradeoffs.",
        "ranked_runs": [],
        "key_insights": [
            "Different constraints shift the scope and complexity of execution.",
            "Persona choice significantly changes go-to-market framing.",
            "Risk profiles vary by buyer type and compliance assumptions.",
        ],
        "risks": ["No clear winner without stronger market evidence."],
        "next_steps": ["Validate buyer pain with 3-5 interviews before committing."],
    }


def _validate(obj: Dict[str, Any], expected_ids: List[int]) -> Tuple[bool, List[str]]:
    errs: List[str] = []
    summary = str(obj.get("summary", "")).strip()
    if not summary:
        errs.append("summary is required.")
    ranked_runs = obj.get("ranked_runs", [])
    if not isinstance(ranked_runs, list):
        errs.append("ranked_runs must be an array.")
    else:
        found_ids = []
        for item in ranked_runs:
            try:
                found_ids.append(int(item.get("run_id")))
            except Exception:
                continue
        missing = [rid for rid in expected_ids if rid not in found_ids]
        if missing:
            errs.append("ranked_runs must include every run_id.")
    key_insights = obj.get("key_insights", [])
    if not isinstance(key_insights, list) or not key_insights:
        errs.append("key_insights must be a non-empty array.")
    return (len(errs) == 0), errs


async def rank_report_agent(
    *,
    generate: GenerateFn,
    extract_json: ExtractJsonFn,
    client: Any,
    model: str,
    runs: List[Dict[str, Any]],
    max_attempts: int = 2,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Rank report for multiple saved runs.
    Returns summary + ranked runs + insights, with logging + usage metrics.
    """
    t0 = time.perf_counter()
    logger.info(
        "rank_report.start",
        extra={
            "request_id": request_id,
            "model": model,
            "runs_count": len(runs),
            "max_attempts": max_attempts,
        },
    )
    expected_ids = [int(r.get("id")) for r in runs if r.get("id") is not None]

    def to_prompt(run: Dict[str, Any]) -> Dict[str, Any]:
        results = run.get("results") or {}
        cleaned_results = {str(k): _coerce_text(v) for k, v in results.items()}
        return {
            "id": run.get("id"),
            "industry": run.get("industry") or "",
            "persona": run.get("tone") or "",
            "constraints": run.get("constraints") or [],
            "models": run.get("models") or list(results.keys()),
            "outputs": cleaned_results,
        }

    system_prompt = """
You are an expert startup analyst preparing a decision-ready report across multiple idea runs.
Return ONLY valid JSON. Do not include markdown or commentary outside JSON.
""".strip()

    base_user_prompt = f"""
Create a ranked, decision-ready report based on these saved runs.

Runs:
{json.dumps([to_prompt(r) for r in runs], ensure_ascii=False)}

Return JSON with this schema:
{{
  "summary": "2-4 sentences summary of the overall landscape",
  "ranked_runs": [
    {{"run_id": 1, "score": 0-100, "rationale": "1-2 sentences"}},
    {{"run_id": 2, "score": 0-100, "rationale": "1-2 sentences"}}
  ],
  "key_insights": ["3-6 bullets of the most important differences"],
  "risks": ["1-3 bullets of major risks"],
  "next_steps": ["2-4 bullets of recommended next actions"]
}}

Rules:
- Scores must be 0-100.
- ranked_runs must include every run_id provided.
- Be concise and specific.
""".strip()

    last_errors: List[str] = []
    usage: Dict[str, Any] = {}

    for attempt in range(1, max_attempts + 1):
        attempt_t0 = time.perf_counter()
        correction = ""
        if last_errors:
            correction = (
                "\n\nVALIDATION ERRORS FROM YOUR LAST OUTPUT (fix them and output corrected JSON only):\n"
                + "\n".join(f"- {e}" for e in last_errors)
            )

        logger.info(
            "rank_report.attempt",
            extra={
                "request_id": request_id,
                "attempt": attempt,
                "model": model,
                "has_corrections": bool(last_errors),
            },
        )

        try:
            result = await generate(client, model, system_prompt, base_user_prompt + correction)
            if isinstance(result, tuple):
                raw, usage = result
            else:
                raw, usage = result, {}
        except Exception as e:
            latency_ms = int((time.perf_counter() - attempt_t0) * 1000)
            logger.exception(
                "rank_report.generate_error",
                extra={
                    "request_id": request_id,
                    "attempt": attempt,
                    "model": model,
                    "latency_ms": latency_ms,
                    "error_type": type(e).__name__,
                },
            )
            last_errors = [f"generate() raised {type(e).__name__}: {e}"]
            continue

        obj = extract_json(raw) or {}
        ok, errors = _validate(obj, expected_ids)
        if ok:
            latency_ms = int((time.perf_counter() - attempt_t0) * 1000)
            logger.info(
                "rank_report.success",
                extra={
                    "request_id": request_id,
                    "attempt": attempt,
                    "model": model,
                    "latency_ms": latency_ms,
                },
            )
            return {"report": obj, "usage": usage}

        last_errors = errors

    latency_ms = int((time.perf_counter() - t0) * 1000)
    logger.warning(
        "rank_report.fallback",
        extra={
            "request_id": request_id,
            "model": model,
            "latency_ms": latency_ms,
            "errors": last_errors,
        },
    )
    return {"report": _fallback_report(), "usage": usage}
