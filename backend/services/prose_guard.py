import re
from typing import List, Tuple


_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_SENSITIVE_URL_RE = re.compile(
    r"https?://\S*(?:x-amz-signature|x-amz-credential|x-amz-expires|presign|presigned)\S*|/downloads/\S+",
    re.IGNORECASE,
)
_ACTION_CLAIM_RE = re.compile(
    r"\b(email sent|sent successfully|download ready|pdf generated|presigned)\b",
    re.IGNORECASE,
)


def apply_low_risk_prose_guard(text: str) -> Tuple[str, List[str]]:
    output = str(text or "")
    issues: List[str] = []

    if _SENSITIVE_URL_RE.search(output):
        issues.append("sensitive_url_removed")
        output = _SENSITIVE_URL_RE.sub("[link withheld in low-risk mode]", output)
    elif _URL_RE.search(output):
        issues.append("raw_url_present")

    if _ACTION_CLAIM_RE.search(output):
        issues.append("action_claim_removed")
        output = _ACTION_CLAIM_RE.sub("requested action", output)

    return output, issues
