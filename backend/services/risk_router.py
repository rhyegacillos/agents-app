import os
import re
from typing import Dict, List, Optional


_HIGH_RISK_PATTERNS = [
    r"\b(pdf|download|export|report)\b",
    r"\b(email|mail|send)\b",
    r"\b(upload|file|attachment|attach)\b",
    r"\b(search|web|news|latest|research|paper|papers|survey|benchmark|eval|evaluation|cite|citation|source|sources)\b",
    r"\b(link|url|presign|presigned)\b",
    r"\b(generate|create)\s+(a\s+)?(pdf|report|email)\b",
]
_HIGH_RISK_REGEX = re.compile("|".join(_HIGH_RISK_PATTERNS), re.IGNORECASE)
_EMAIL_ADDRESS_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_EMAIL_ACTION_RE = re.compile(r"\b(send|resend|email|mail)\b", re.IGNORECASE)
_PDF_ACTION_RE = re.compile(r"\b(pdf|download|export|report)\b", re.IGNORECASE)
_FOLLOWUP_ACTION_RE = re.compile(
    r"\b("
    r"resend|retry|try again|send again|email again|mail again|"
    r"send it again|send that again|send this again|"
    r"did(?:n't| not)\s+(?:get|receive)\s+it|"
    r"haven(?:'t| not)\s+received\s+it|"
    r"still\s+(?:did(?:n't| not)\s+(?:get|receive)\s+it|haven(?:'t| not)\s+received\s+it)|"
    r"still\s+not(?:\s+\w+){0,2}\s+receive|"
    r"check\s+(?:my\s+)?(?:inbox|spam)"
    r")\b",
    re.IGNORECASE,
)
_PRIOR_ACTION_CONTEXT_RE = re.compile(
    r"\b("
    r"pdf|download|export|report|"
    r"email|mail|inbox|spam|"
    r"send_resend_email|generate_pdf_from_text|"
    r"send to|email to|mail to"
    r")\b",
    re.IGNORECASE,
)

def _recent_conversation_text(conversation: Optional[List[Dict]]) -> str:
    if not conversation:
        return ""
    lines = []
    for item in conversation[-6:]:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "")).strip()
        if content:
            lines.append(content)
    return "\n".join(lines)


def classify_risk(
    message: str,
    file_id: Optional[str] = None,
    conversation: Optional[List[Dict]] = None,
) -> Dict[str, str]:
    text = (message or "").strip()
    if file_id:
        return {"tier": "high", "reason": "file_attached"}

    # Raw email addresses are high-risk because they usually indicate a tool action
    # (send/resend email), even when no explicit verb is present.
    if _EMAIL_ADDRESS_RE.search(text):
        return {"tier": "high", "reason": "email_address"}

    match = _HIGH_RISK_REGEX.search(text)
    if match:
        return {"tier": "high", "reason": f"keyword:{match.group(0).lower()}"}

    recent_context = _recent_conversation_text(conversation)
    if recent_context and _FOLLOWUP_ACTION_RE.search(text) and _PRIOR_ACTION_CONTEXT_RE.search(recent_context):
        return {"tier": "high", "reason": "followup_prior_action_context"}

    # Optional fail-safe mode: default unknown content to high risk.
    strict = os.getenv("RISK_ROUTER_FAILSAFE_HIGH_DEFAULT", "false").lower() == "true"
    if strict and not text:
        return {"tier": "high", "reason": "empty_or_unknown"}

    return {"tier": "low", "reason": "conversational"}


def requires_email_tool_action(
    message: str,
    conversation: Optional[List[Dict]] = None,
) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if _EMAIL_ADDRESS_RE.search(text):
        return True
    if _EMAIL_ACTION_RE.search(text):
        return True
    recent_context = _recent_conversation_text(conversation)
    if recent_context and _FOLLOWUP_ACTION_RE.search(text):
        return bool(
            re.search(
                r"\b(email|mail|inbox|spam|send_resend_email|send to|email to|mail to)\b",
                recent_context,
                re.IGNORECASE,
            )
        )
    return False


def required_tool_sequence(
    message: str,
    conversation: Optional[List[Dict]] = None,
) -> List[str]:
    text = (message or "").strip()
    required: List[str] = []
    if _PDF_ACTION_RE.search(text):
        required.append("generate_pdf_from_text")
    if requires_email_tool_action(text, conversation):
        required.append("send_resend_email")
    return required
