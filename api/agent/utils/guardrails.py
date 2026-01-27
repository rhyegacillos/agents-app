import json
from pathlib import Path
from typing import Dict, Any, List

from openai import AsyncOpenAI

from . import generate_with_fallback, get_logger

logger = get_logger(__name__)

GUARDRAILS_PATH = Path("data/critic_guardrails.json")
DEFAULT_REPEAT_THRESHOLD = 3
DEFAULT_MAX_GUARDRAILS = 8
MAX_TRACKED_ISSUES = 50


def _load_state() -> Dict[str, Any]:
    if not GUARDRAILS_PATH.exists():
        return {"issue_counts": {}, "guardrails": [], "promoted": []}
    try:
        data = json.loads(GUARDRAILS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"issue_counts": {}, "guardrails": [], "promoted": []}
    return {
        "issue_counts": data.get("issue_counts", {}),
        "guardrails": data.get("guardrails", []),
        "promoted": data.get("promoted", []),
    }


def _save_state(state: Dict[str, Any]) -> None:
    GUARDRAILS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "issue_counts": state.get("issue_counts", {}),
        "guardrails": state.get("guardrails", []),
        "promoted": state.get("promoted", []),
    }
    GUARDRAILS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def get_guardrails() -> List[str]:
    state = _load_state()
    return [str(rule).strip() for rule in state.get("guardrails", []) if str(rule).strip()]


async def record_critic_issues(
    issues: List[str],
    client: AsyncOpenAI,
    repeat_threshold: int = DEFAULT_REPEAT_THRESHOLD,
    max_guardrails: int = DEFAULT_MAX_GUARDRAILS,
) -> List[str]:
    cleaned = [str(issue).strip() for issue in issues if str(issue).strip()]
    if not cleaned:
        return get_guardrails()

    state = _load_state()
    issue_counts = state.get("issue_counts", {})
    guardrails = [str(rule).strip() for rule in state.get("guardrails", []) if str(rule).strip()]
    promoted = set(state.get("promoted", []))

    seen = set()
    for issue in cleaned:
        if issue in seen:
            continue
        seen.add(issue)
        issue_counts[issue] = int(issue_counts.get(issue, 0)) + 1

    if len(issue_counts) > MAX_TRACKED_ISSUES:
        sorted_items = sorted(issue_counts.items(), key=lambda item: item[1], reverse=True)
        issue_counts = dict(sorted_items[:MAX_TRACKED_ISSUES])

    for issue, count in issue_counts.items():
        if len(guardrails) >= max_guardrails:
            break
        if issue in promoted or count < repeat_threshold:
            continue
        guardrail = await _rewrite_issue(issue, client)
        promoted.add(issue)
        if guardrail and guardrail not in guardrails and len(guardrails) < max_guardrails:
            guardrails.append(guardrail)
            logger.info("Added guardrail: %s", guardrail)

    state["issue_counts"] = issue_counts
    state["guardrails"] = guardrails
    state["promoted"] = list(promoted)
    _save_state(state)
    return guardrails


async def _rewrite_issue(issue: str, client: AsyncOpenAI) -> str:
    prompt = (
        "Rewrite the issue into a short, neutral formatting or structure rule for a clinical summary. "
        "Only produce a format/structure/clarity rule. "
        "If the issue is clinical or patient-specific, return an empty string."
    )
    try:
        response = await generate_with_fallback(
            client=client,
            messages=[
                {"role": "system", "content": "You turn critic issues into formatting guardrails."},
                {"role": "user", "content": f"Issue: {issue}\nRule:"},
            ],
            models=["gpt-5-nano"],
            max_retries=0,
        )
    except Exception as exc:
        logger.warning("Guardrail rewrite failed: %s", exc)
        return ""

    text = (response.choices[0].message.content or "").strip()
    if not text:
        return ""
    text = text.strip("`").strip().strip('"')
    first_line = text.splitlines()[0].strip()
    if not first_line:
        return ""
    if first_line.lower() in {"none", "n/a", "not applicable"}:
        return ""
    return first_line[:160]
