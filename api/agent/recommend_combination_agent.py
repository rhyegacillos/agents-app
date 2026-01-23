# agent/recommend_combination_agent.py

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple


logger = logging.getLogger(__name__)

GenerateFn = Callable[[Any, str, str, str], Awaitable[str]]
ExtractJsonFn = Callable[[str], Optional[Dict[str, Any]]]


_REQUIRED_SECTION_RE = re.compile(
    r"<section[^>]*data-section=['\"]recommendation_reason['\"][^>]*>.*?</section>",
    re.IGNORECASE | re.DOTALL,
)
_LI_RE = re.compile(r"<li\b", re.IGNORECASE)


def _count_li(html: str) -> int:
    return len(_LI_RE.findall(html or ""))


def _normalize_constraints(
    raw_constraints: Any, allowed_constraints: Sequence[str], max_items: int = 2
) -> List[str]:
    if isinstance(raw_constraints, str):
        raw_constraints = [raw_constraints]
    if not isinstance(raw_constraints, list):
        raw_constraints = []

    seen = set()
    out: List[str] = []
    for c in raw_constraints:
        c = str(c).strip()
        if c in allowed_constraints and c not in seen:
            seen.add(c)
            out.append(c)
        if len(out) >= max_items:
            break
    return out


def _validate_reason_html(reason_html: str) -> Tuple[bool, List[str]]:
    errs: List[str] = []
    html = (reason_html or "").strip()

    if not html:
        errs.append("reason_html is empty.")
        return False, errs

    if not _REQUIRED_SECTION_RE.search(html):
        errs.append(
            "reason_html must contain a <section data-section='recommendation_reason'>...</section> wrapper."
        )

    li_count = _count_li(html)
    if li_count < 3 or li_count > 5:
        errs.append(f"reason_html must contain 3–5 <li> bullets; found {li_count}.")

    return (len(errs) == 0), errs


def _fallback_reason_html() -> str:
    return (
        "<section data-section='recommendation_reason'>"
        "<h3>Why this combination</h3>"
        "<ul>"
        "<li>Fallback selection applied due to validation failure.</li>"
        "<li>Chosen options are the first allowed items to guarantee exact-match validity.</li>"
        "<li>Tradeoff: may be less tailored than a fully optimized selection.</li>"
        "</ul>"
        "</section>"
    )


async def recommend_combination_agent(
    *,
    generate: GenerateFn,
    extract_json: ExtractJsonFn,
    client: Any,
    model: str,
    industry: str,
    allowed_constraints: Sequence[str],
    personas: Sequence[Dict[str, Any]],
    max_attempts: int = 3,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Agentic recommend-combination:
    - Plan/select -> validate -> retry with error feedback -> fallback.
    Monitoring logs include: request_id, model, attempt, latency_ms, validation_errors, fallback_used.
    """

    t0 = time.perf_counter()

    allowed_persona_ids = [str(p.get("id", "")).strip() for p in personas]
    allowed_persona_ids = [p for p in allowed_persona_ids if p]

    logger.info(
        "recommend_combination.start",
        extra={
            "request_id": request_id,
            "industry": industry,
            "model": model,
            "max_attempts": max_attempts,
            "allowed_constraints_count": len(allowed_constraints),
            "allowed_personas_count": len(allowed_persona_ids),
        },
    )

    system_prompt = """
You are a product strategist selecting the best configuration for generating a high-quality AI agent business idea.

STRICT RULES (DO NOT VIOLATE):
- You MUST select constraints ONLY from the provided "Allowed constraints" list.
- You MUST select persona ONLY from the provided "Allowed personas" list (use the persona id exactly).
- You MUST NOT invent, paraphrase, shorten, or modify any option text.
- All selected strings MUST match the allowed options EXACTLY (character-for-character).
- Choose 1 or 2 constraints only. NEVER choose more than 2.
- If unsure, choose the FIRST option(s) from the allowed lists.
- Return ONLY valid JSON. No prose, no markdown, no explanation outside JSON.

OPTIMIZATION GOALS:
- Fastest path to validation
- Clear economic ROI
- Strong workflow alignment in the selected industry
- Practical execution feasibility for a small team

SELECTION GUIDELINES:
- Prefer constraints that force concrete workflows and measurable outcomes.
- Avoid combinations that contradict each other.
- If multiple options are plausible, choose the one that reduces ambiguity and increases execution clarity.
""".strip()

    base_user_prompt = f"""
Industry: "{industry}"

Allowed constraints (use EXACT strings from this list only):
{json.dumps(list(allowed_constraints), ensure_ascii=False)}
IMPORTANT: Copy the chosen constraint strings exactly as they appear in the Allowed constraints list.

Allowed personas (use EXACT persona id from this list only):
{json.dumps(list(personas), ensure_ascii=False)}

Return ONLY valid JSON with this exact schema:
{{
  "recommended_constraints": ["string", "string"],
  "recommended_persona": "string",
  "reason_html": "<section data-section='recommendation_reason'><h3>Why this combination</h3><ul><li>...</li></ul></section>"
}}

Rules:
- recommended_constraints MUST be an array with 1 or 2 items.
- Each item in recommended_constraints MUST exactly match one item in Allowed constraints.
- recommended_persona MUST exactly match one persona id in Allowed personas.
- Do NOT output any constraint/persona that is not in the allowed lists.
- If you are unsure, choose the FIRST constraint and FIRST persona from the allowed lists.

Rules for reason_html:
- Must be semantic HTML only.
- Must contain 3–5 <li> bullet points explaining:
  1) why the chosen constraints fit the industry's workflows,
  2) why the chosen persona lens is best for producing useful output,
  3) one explicit tradeoff/risk of this choice.
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
            "recommend_combination.attempt",
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
                "recommend_combination.generate_error",
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

        # Extract fields
        raw_constraints = obj.get("recommended_constraints", [])
        recommended_persona = str(obj.get("recommended_persona", "")).strip()
        reason_html = str(obj.get("reason_html", "")).strip()

        # Validate constraints
        recommended_constraints = _normalize_constraints(raw_constraints, allowed_constraints, max_items=2)

        errors: List[str] = []

        if len(recommended_constraints) < 1 or len(recommended_constraints) > 2:
            errors.append("recommended_constraints must contain 1–2 exact-match items from Allowed constraints.")

        if recommended_persona not in allowed_persona_ids:
            errors.append("recommended_persona must exactly match one persona id from Allowed personas.")

        ok_html, html_errors = _validate_reason_html(reason_html)
        if not ok_html:
            errors.extend(html_errors)

        latency_ms = int((time.perf_counter() - attempt_t0) * 1000)

        if not errors:
            total_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                "recommend_combination.success",
                extra={
                    "request_id": request_id,
                    "attempt": attempt,
                    "model": model,
                    "latency_ms": latency_ms,
                    "total_ms": total_ms,
                    "recommended_constraints": recommended_constraints,
                    "recommended_persona": recommended_persona,
                    "reason_li_count": _count_li(reason_html),
                    "fallback_used": False,
                },
            )
            return {
                "recommended_constraints": recommended_constraints,
                "recommended_persona": recommended_persona,
                "reason_html": reason_html,
                "meta": {"attempts": attempt, "fallback_used": False},
                "usage": usage,
            }

        # Log validation failure (don’t log full raw to avoid noise/secrets)
        logger.warning(
            "recommend_combination.validation_failed",
            extra={
                "request_id": request_id,
                "attempt": attempt,
                "model": model,
                "latency_ms": latency_ms,
                "validation_errors": errors,
                "parsed_constraints": recommended_constraints,
                "parsed_persona": recommended_persona,
                "reason_li_count": _count_li(reason_html),
            },
        )
        last_errors = errors

    # Deterministic fallback
    fallback_constraints = [allowed_constraints[0]] if allowed_constraints else ["None"]
    fallback_persona = allowed_persona_ids[0] if allowed_persona_ids else "Neutral"

    total_ms = int((time.perf_counter() - t0) * 1000)
    logger.error(
        "recommend_combination.fallback",
        extra={
            "request_id": request_id,
            "model": model,
            "total_ms": total_ms,
            "fallback_used": True,
            "errors": last_errors,
            "fallback_constraints": fallback_constraints,
            "fallback_persona": fallback_persona,
        },
    )

    return {
        "recommended_constraints": fallback_constraints,
        "recommended_persona": fallback_persona,
        "reason_html": _fallback_reason_html(),
        "meta": {"attempts": max_attempts, "fallback_used": True, "errors": last_errors},
        "usage": usage,
    }
