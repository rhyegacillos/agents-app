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


def _coerce_text(value: Any, max_len: int = 3500) -> str:
    text = _strip_html(str(value)) if value is not None else ""
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _fallback_comparison() -> Dict[str, Any]:
    return {
        "winner": "tie",
        "summary": "Both runs are close. A structured review is recommended before selecting a final direction.",
        "key_changes": [
            "Outputs differ across persona framing and constraints.",
            "Value propositions emphasize different buyer pain points.",
            "Execution steps vary in scope and risk appetite.",
        ],
        "winner_rationale": "No decisive edge without clearer market evidence.",
        "risks": ["Insufficient differentiation to call a clear winner."],
    }


def _build_decision_memo(comparison: Dict[str, Any]) -> Dict[str, Any]:
    winner = str(comparison.get("winner", "tie")).strip().upper()
    if winner not in {"A", "B"}:
        decision = "Tie"
    else:
        decision = f"Pick {winner}"
    memo = comparison.get("decision_memo") if isinstance(comparison.get("decision_memo"), dict) else {}
    summary = str(memo.get("summary") or comparison.get("summary", "")).strip()
    rationale = str(memo.get("rationale") or comparison.get("winner_rationale", "")).strip()
    key_changes = memo.get("key_changes") if isinstance(memo.get("key_changes"), list) else comparison.get("key_changes", [])
    if not isinstance(key_changes, list):
        key_changes = []
    risks = memo.get("risks") if isinstance(memo.get("risks"), list) else comparison.get("risks", [])
    if not isinstance(risks, list):
        risks = []
    next_steps = memo.get("next_steps") if isinstance(memo.get("next_steps"), list) else []
    return {
        "decision": decision,
        "summary": summary,
        "key_changes": key_changes,
        "rationale": rationale,
        "risks": risks,
        "next_steps": next_steps,
    }


def _validate(obj: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errs: List[str] = []
    winner = str(obj.get("winner", "")).strip().lower()
    if winner not in {"a", "b", "tie"}:
        errs.append("winner must be 'A', 'B', or 'tie'.")
    summary = str(obj.get("summary", "")).strip()
    if not summary:
        errs.append("summary is required.")
    key_changes = obj.get("key_changes", [])
    if not isinstance(key_changes, list) or not key_changes:
        errs.append("key_changes must be a non-empty array.")
    winner_rationale = str(obj.get("winner_rationale", "")).strip()
    if not winner_rationale:
        errs.append("winner_rationale is required.")
    return (len(errs) == 0), errs


async def compare_results_agent(
    *,
    generate: GenerateFn,
    extract_json: ExtractJsonFn,
    client: Any,
    model: str,
    run_a: Dict[str, Any],
    run_b: Dict[str, Any],
    max_attempts: int = 2,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Agentic comparison for saved results:
    - compare run A vs run B
    - return winner + rationale + key changes
    """

    t0 = time.perf_counter()
    logger.info(
        "compare_results.start",
        extra={
            "request_id": request_id,
            "model": model,
            "run_a_id": run_a.get("id"),
            "run_b_id": run_b.get("id"),
            "max_attempts": max_attempts,
        },
    )

    def to_prompt(run: Dict[str, Any]) -> Dict[str, Any]:
        results = run.get("results") or {}
        cleaned_results = {
            str(k): _coerce_text(v) for k, v in results.items()
        }
        return {
            "industry": run.get("industry") or "",
            "persona": run.get("tone") or "",
            "constraints": run.get("constraints") or [],
            "models": run.get("models") or list(results.keys()),
            "outputs": cleaned_results,
        }

    system_prompt = """
You are a startup analyst comparing two idea-generation runs.
Return ONLY valid JSON (no markdown, no extra text).
Be precise and decision-oriented.
""".strip()

    base_user_prompt = (
        "Compare Run A and Run B. Identify what changed, why it matters, and which run is stronger.\n\n"
        "Run A:\n"
        f"{json.dumps(to_prompt(run_a), ensure_ascii=False)}\n\n"
        "Run B:\n"
        f"{json.dumps(to_prompt(run_b), ensure_ascii=False)}\n\n"
        "Return JSON with this schema:\n"
        "{\n"
        '  "winner": "A" | "B" | "tie",\n'
        '  "summary": "2-4 sentences, decision-ready",\n'
        '  "key_changes": ["3-6 bullets with concrete differences"],\n'
        '  "winner_rationale": "1-2 sentences explaining the choice",\n'
        '  "risks": ["1-3 bullets of risks or tradeoffs"],\n'
        '  "decision_memo": {\n'
        '    "decision": "Pick A" | "Pick B" | "Tie",\n'
        '    "summary": "2-4 sentences",\n'
        '    "key_changes": ["3-6 bullets"],\n'
        '    "rationale": "1-2 sentences",\n'
        '    "risks": ["1-3 bullets"],\n'
        '    "next_steps": ["2-4 bullets"]\n'
        "  }\n"
        "}\n\n"
        "Rules:\n"
        "- winner must be A, B, or tie.\n"
        "- key_changes must be specific and reference content differences.\n"
        "- Be concise and avoid generic statements.\n"
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
            "compare_results.attempt",
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
                "compare_results.generate_error",
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
        ok, errors = _validate(obj)
        if ok:
            latency_ms = int((time.perf_counter() - attempt_t0) * 1000)
            logger.info(
                "compare_results.success",
                extra={
                    "request_id": request_id,
                    "attempt": attempt,
                    "model": model,
                    "latency_ms": latency_ms,
                    "winner": obj.get("winner"),
                },
            )
            obj["winner"] = str(obj.get("winner", "")).strip().upper()
            obj["decision_memo"] = _build_decision_memo(obj)
            return {"comparison": obj, "usage": usage}

        last_errors = errors

    latency_ms = int((time.perf_counter() - t0) * 1000)
    logger.warning(
        "compare_results.fallback",
        extra={
            "request_id": request_id,
            "model": model,
            "latency_ms": latency_ms,
            "errors": last_errors,
        },
    )
    comparison = _fallback_comparison()
    comparison["decision_memo"] = _build_decision_memo(comparison)
    return {"comparison": comparison, "usage": usage}
