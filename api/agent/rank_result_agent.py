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


def _fallback_ranking(model_ids: List[str], titles: Dict[str, str]) -> Dict[str, Any]:
    ranked = []
    for idx, model_id in enumerate(model_ids, start=1):
        ranked.append({
            "model_id": model_id,
            "rank": idx,
            "score": 50,
            "title": titles.get(model_id) or f"Model output {idx}",
            "rationale": "Automatic fallback ranking due to analysis issue.",
        })
    return {
        "summary": "Ranking generated with limited analysis. Review outputs directly to confirm.",
        "ranked_models": ranked,
        "highlights": [
            "Fallback ranking used due to analysis issue.",
            "Titles pulled from the generated outputs where available.",
            "Review clarity and structure across the top results.",
            "Check feasibility and execution steps for realism.",
            "Prefer the output with the most actionable plan.",
        ],
    }


def _validate(obj: Dict[str, Any], expected_ids: List[str]) -> Tuple[bool, List[str]]:
    errs: List[str] = []
    summary = str(obj.get("summary", "")).strip()
    if not summary:
        errs.append("summary is required.")
    ranked = obj.get("ranked_models", [])
    if not isinstance(ranked, list) or not ranked:
        errs.append("ranked_models must be a non-empty array.")
        return (len(errs) == 0), errs
    highlights = obj.get("highlights", [])
    if not isinstance(highlights, list) or len(highlights) < 5:
        errs.append("highlights must be an array with at least 5 bullets.")

    seen_ids: List[str] = []
    seen_ranks: List[int] = []
    for item in ranked:
        model_id = str(item.get("model_id", "")).strip()
        if model_id:
            seen_ids.append(model_id)
        else:
            errs.append("ranked_models entries must include model_id.")
        try:
            rank_value = int(item.get("rank"))
            seen_ranks.append(rank_value)
        except Exception:
            errs.append("ranked_models entries must include numeric rank.")
        title = str(item.get("title", "")).strip()
        if not title:
            errs.append("ranked_models entries must include title.")
        rationale = str(item.get("rationale", "")).strip()
        if not rationale:
            errs.append("ranked_models entries must include rationale.")

    missing = [mid for mid in expected_ids if mid not in seen_ids]
    if missing:
        errs.append("ranked_models must include every model_id.")
    if seen_ranks:
        unique_ranks = set(seen_ranks)
        if len(unique_ranks) != len(seen_ranks):
            errs.append("ranked_models ranks must be unique.")
        if min(seen_ranks, default=1) < 1 or max(seen_ranks, default=0) > len(expected_ids):
            errs.append("ranked_models ranks must be within 1..N.")

    return (len(errs) == 0), errs


async def rank_result_agent(
    *,
    generate: GenerateFn,
    extract_json: ExtractJsonFn,
    client: Any,
    model: str,
    run: Dict[str, Any],
    max_attempts: int = 2,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Rank multiple model outputs within a single run.
    Returns ranked models, summary, and usage metrics.
    """
    t0 = time.perf_counter()
    outputs = run.get("outputs") or {}
    titles = run.get("titles") or {}
    model_ids = [str(mid) for mid in outputs.keys()]

    logger.info(
        "rank_result.start request_id=%s model=%s model_count=%s",
        request_id,
        model,
        len(model_ids),
    )

    prompt_payload = {
        "industry": run.get("industry") or "",
        "persona": run.get("persona") or "",
        "constraints": run.get("constraints") or [],
        "titles": titles,
        "model_labels": run.get("model_labels") or {},
        "outputs": {mid: _coerce_text(outputs.get(mid)) for mid in model_ids},
    }

    system_prompt = """
You are an analyst ranking multiple model outputs for the same business idea configuration.
Return ONLY valid JSON. Do not include markdown or commentary outside JSON.
Use only the provided outputs and titles. Do not assume facts or invent details.
If something is not stated in the output, note that it is missing rather than guessing.
""".strip()

    base_user_prompt = (
        "Rank the model outputs for the same configuration using this rubric:\n"
        "- Clarity (easy to understand, organized)\n"
        "- Feasibility (realistic to build and execute)\n"
        "- Differentiation (stands out, clear advantage)\n"
        "- Actionability (concrete steps, executable)\n"
        "- Risk awareness (mentions risks or tradeoffs)\n"
        "- Stakeholder-readiness (polished for sharing)\n\n"
        "Configuration and outputs:\n"
        f"{json.dumps(prompt_payload, ensure_ascii=False)}\n\n"
        "Return JSON with this schema:\n"
        "{\n"
        '  "summary": "1-2 sentences on which model performed best and why",\n'
        '  "ranked_models": [\n'
        '    {\n'
        '      "model_id": "model-id",\n'
        '      "rank": 1,\n'
        '      "score": 0-100,\n'
        '      "title": "Exact title from titles map for this model",\n'
        '      "rationale": "1-2 sentences referencing the rubric"\n'
        "    }\n"
        "  ],\n"
        '  "highlights": ["At least 5 short bullets, factual and tied to the outputs"]\n'
        "}\n\n"
        "Rules:\n"
        "- ranked_models must include every model_id exactly once.\n"
        "- Use the provided titles exactly; do not invent new titles.\n"
        "- Refer to models using model_labels (not model_id strings).\n"
        "- Use the rubric explicitly in your rationale.\n"
        "- highlights must be factual and grounded in the outputs (no guesses).\n"
        "- Be concise and decision-ready.\n"
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
            "rank_result.attempt request_id=%s attempt=%s model=%s has_corrections=%s",
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
                "rank_result.generate_error request_id=%s attempt=%s model=%s latency_ms=%s error_type=%s",
                request_id,
                attempt,
                model,
                latency_ms,
                type(e).__name__,
            )
            last_errors = [f"generate() raised {type(e).__name__}: {e}"]
            continue

        obj = extract_json(raw) or {}
        ok, errors = _validate(obj, model_ids)
        if ok:
            latency_ms = int((time.perf_counter() - attempt_t0) * 1000)
            logger.info(
                "rank_result.success request_id=%s attempt=%s model=%s latency_ms=%s",
                request_id,
                attempt,
                model,
                latency_ms,
            )
            return {"rank_result": obj, "usage": usage}

        logger.warning(
            "rank_result.validation_failed request_id=%s attempt=%s model=%s errors=%s",
            request_id,
            attempt,
            model,
            errors,
        )
        last_errors = errors

    latency_ms = int((time.perf_counter() - t0) * 1000)
    logger.warning(
        "rank_result.fallback request_id=%s model=%s latency_ms=%s errors=%s",
        request_id,
        model,
        latency_ms,
        last_errors,
    )
    return {
        "rank_result": _fallback_ranking(
            model_ids,
            titles if isinstance(titles, dict) else {},
        ),
        "usage": usage,
    }
