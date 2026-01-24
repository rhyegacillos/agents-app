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
        "risks": [
            "Insufficient buyer validation to confirm priority pain points.",
            "Unclear implementation scope for the most promising run.",
            "Limited proof of differentiation versus common market approaches.",
            "Execution timeline may exceed current team capacity.",
            "Regulatory or compliance assumptions are not fully validated.",
        ],
        "next_steps": ["Validate buyer pain with 3-5 interviews before committing."],
        "email_brief": {
            "subject": "IdeaGen Rank Report",
            "summary": "Your rank report is ready with the top runs and key insights.",
            "highlights": [
                "Top run identified with a score and rationale.",
                "Key differences and risks summarized for quick review.",
            ],
        },
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
    risks = obj.get("risks", [])
    cleaned_risks = [str(item).strip() for item in risks if str(item).strip()] if isinstance(risks, list) else []
    if len(cleaned_risks) < 5:
        errs.append("risks must include at least 5 bullets.")
    email_brief = obj.get("email_brief")
    if not isinstance(email_brief, dict):
        errs.append("email_brief must be an object.")
    else:
        subject = str(email_brief.get("subject", "")).strip()
        brief_summary = str(email_brief.get("summary", "")).strip()
        highlights = email_brief.get("highlights", [])
        if not subject:
            errs.append("email_brief.subject is required.")
        if not brief_summary:
            errs.append("email_brief.summary is required.")
        if not isinstance(highlights, list) or not highlights:
            errs.append("email_brief.highlights must be a non-empty array.")
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
        "rank_report.start request_id=%s model=%s runs_count=%s max_attempts=%s",
        request_id,
        model,
        len(runs),
        max_attempts,
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
Use only information present in the provided runs. Do not assume, infer, or add external facts.
If a detail is missing, omit it or say "Not specified."
Return ONLY valid JSON. Do not include markdown or commentary outside JSON.
""".strip()

    base_user_prompt = (
        "Create a ranked, decision-ready report based on these saved runs.\n\n"
        "Runs:\n"
        f"{json.dumps([to_prompt(r) for r in runs], ensure_ascii=False)}\n\n"
        "Return JSON with this schema:\n"
        "{\n"
        '  "summary": "2-4 sentences summary of the overall landscape",\n'
        '  "ranked_runs": [\n'
        '    {"run_id": 1, "score": 0-100, "rationale": "1-2 sentences"},\n'
        '    {"run_id": 2, "score": 0-100, "rationale": "1-2 sentences"}\n'
        "  ],\n"
        '  "key_insights": ["3-6 bullets of the most important differences"],\n'
        '  "risks": ["5-7 bullets of major risks"],\n'
        '  "next_steps": ["2-4 bullets of recommended next actions"],\n'
        '  "email_brief": {\n'
        '    "subject": "Short subject line for a report email",\n'
        '    "summary": "1-2 sentence summary for the email body",\n'
        '    "highlights": ["2-4 short bullets"]\n'
        "  }\n"
        "}\n\n"
        "Rules:\n"
        "- Scores must be 0-100.\n"
        "- ranked_runs must include every run_id provided.\n"
        "- Risks must include at least 5 bullets.\n"
        "- Be concise and specific.\n"
        "- Use only facts present in the runs; do not add assumptions or outside details.\n"
        "- email_brief must be ready for a customer email (no AI mentions).\n"
    )

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
            "rank_report.attempt request_id=%s attempt=%s model=%s has_corrections=%s",
            request_id,
            attempt,
            model,
            bool(last_errors),
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
                "rank_report.generate_error request_id=%s attempt=%s model=%s latency_ms=%s error_type=%s",
                request_id,
                attempt,
                model,
                latency_ms,
                type(e).__name__,
            )
            last_errors = [f"generate() raised {type(e).__name__}: {e}"]
            continue

        obj = extract_json(raw) or {}
        ok, errors = _validate(obj, expected_ids)
        if ok:
            latency_ms = int((time.perf_counter() - attempt_t0) * 1000)
            logger.info(
                "rank_report.success request_id=%s attempt=%s model=%s latency_ms=%s",
                request_id,
                attempt,
                model,
                latency_ms,
            )
            return {"report": obj, "usage": usage}

        logger.warning(
            "rank_report.validation_failed request_id=%s attempt=%s model=%s errors=%s",
            request_id,
            attempt,
            model,
            errors,
        )
        last_errors = errors

    latency_ms = int((time.perf_counter() - t0) * 1000)
    logger.warning(
        "rank_report.fallback request_id=%s model=%s latency_ms=%s errors=%s",
        request_id,
        model,
        latency_ms,
        last_errors,
    )
    return {"report": _fallback_report(), "usage": usage}
