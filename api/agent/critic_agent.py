import json
import os
import re
from typing import Dict, Any, List

from openai import AsyncOpenAI

from .utils.provider_clients import get_gemini_client
from .utils import generate_with_fallback, get_logger

logger = get_logger(__name__)

DEFAULT_MIN_SCORE = 0.8
# Use a fast model for the critic, as it's a frequent, analytical task
CRITIC_MODEL = ["gemini-2.5-flash"]
DEFAULT_MAX_RETRIES = 1
MIN_SCORE_REGEN = 0.85


def critic_enabled() -> bool:
    return True


def critic_min_score() -> float:
    return DEFAULT_MIN_SCORE


def critic_max_retries() -> int:
    return DEFAULT_MAX_RETRIES


def critic_models() -> List[str]:
    return list(CRITIC_MODEL)


def build_critic_client(default_client: AsyncOpenAI) -> AsyncOpenAI:
    """Return a Gemini client for critic calls.

    Uses the cached client when GEMINI_API_KEY is configured.
    Falls back to the passed-in default client otherwise.
    """
    cached = get_gemini_client()
    return cached or default_client


def _extract_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return {}
        return {}


def _normalize_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_review(data: Dict[str, Any]) -> Dict[str, Any]:
    score = data.get("score", 1.0)
    try:
        score = float(score)
    except (TypeError, ValueError):
        score = 1.0
    needs_fix = bool(data.get("needs_fix", False))
    issues = _normalize_list(data.get("issues"))
    missing = _normalize_list(data.get("missing"))
    hallucinations = _normalize_list(data.get("hallucinations"))
    return {
        "score": max(0.0, min(1.0, score)),
        "needs_fix": needs_fix,
        "issues": issues,
        "missing": missing,
        "hallucinations": hallucinations,
    }


def review_requires_regen(review: Dict[str, Any]) -> bool:
    min_score = critic_min_score()
    if review.get("hallucinations"):
        return True
    if review.get("missing"):
        return True
    if review.get("issues"):
        return True
    return review.get("score", 1.0) < min_score or review.get("needs_fix", False)


def format_issue_lines(review: Dict[str, Any]) -> List[str]:
    lines = []
    for label in ("hallucinations", "missing", "issues"):
        for item in review.get(label, []):
            lines.append(f"{label}: {item}")
    return lines


async def review_summary(
    summary_html: str,
    source_text: str,
    patient_history: str,
    research_findings: str,
    guideline_findings: str,
    client: AsyncOpenAI,
) -> Dict[str, Any]:
    system_prompt = (
        "You are an expert Medical Director reviewing a clinical summary for safety and accuracy. "
        "Strictly compare the summary against the provided source text, history, and research findings. "
        "\n\nCRITICAL CHECKS:\n"
        "1. HALLUCINATIONS: Does the summary invent diagnoses, medications, or vitals not in the source?\n"
        "2. OMISSIONS: Are major allergies, abnormal vitals, or the primary diagnosis missing?\n"
        "3. SAFETY: Are drug interactions or guideline warnings (from Research Findings) missing from the summary?\n"
        "4. CONTRADICTIONS: Does the summary contradict the doctor's notes?\n\n"
        "Return JSON only with keys: score (0.0-1.0), needs_fix (bool), issues (list of strings), "
        "missing (list of strings), hallucinations (list of strings)."
    )

    user_prompt = (
        "Summary (HTML):\n"
        f"{summary_html}\n\n"
        "Source text:\n"
        f"{source_text}\n\n"
        "Patient history:\n"
        f"{patient_history}\n\n"
        "Research findings:\n"
        f"{research_findings}\n\n"
        "Guideline findings:\n"
        f"{guideline_findings}\n\n"
        "Evaluate for factual accuracy and completeness. "
        "If the summary is safe and accurate, set needs_fix=false."
    )

    try:
        response = await generate_with_fallback(
            client=client,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            models=CRITIC_MODEL,
        )
    except Exception as exc:
        logger.warning(f"Critic review failed: {exc}")
        return {"score": 1.0, "needs_fix": False, "issues": [], "missing": [], "hallucinations": []}

    raw = response.choices[0].message.content or ""
    review = _normalize_review(_extract_json(raw))
    logger.info(
        "Critic review completed: score=%s issues=%s missing=%s hallucinations=%s",
        review["score"],
        len(review["issues"]),
        len(review["missing"]),
        len(review["hallucinations"]),
    )
    return review
