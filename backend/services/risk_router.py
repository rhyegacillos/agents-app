import os
import re
from typing import Dict, Optional


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


def classify_risk(message: str, file_id: Optional[str] = None) -> Dict[str, str]:
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

    # Optional fail-safe mode: default unknown content to high risk.
    strict = os.getenv("RISK_ROUTER_FAILSAFE_HIGH_DEFAULT", "false").lower() == "true"
    if strict and not text:
        return {"tier": "high", "reason": "empty_or_unknown"}

    return {"tier": "low", "reason": "conversational"}
