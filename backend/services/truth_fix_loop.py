from typing import Any, Dict, Iterable, List, Optional, Set


AUTO_FIXABLE_ISSUE_CODES: Set[str] = {
    "SOURCE_LINK_MISSING",
    "SOURCE_URL_INVALID",
    "SOURCE_LINK_INLINE_MISSING",
    "SOURCE_LINK_INLINE_NONCANONICAL",
    "SOURCE_SECTION_DUPLICATE",
    "LINK_NOT_CANONICAL",
}

HARD_BLOCK_ISSUE_CODES: Set[str] = {
    "CLAIM_UNVERIFIED_EMAIL_SENT",
    "CLAIM_UNVERIFIED_PAGE_COUNT",
    "SEARCH_CONTEXT_EMPTY",
    "LINK_PLACEHOLDER",
}


def should_attempt_auto_fix(issue_codes: Iterable[str]) -> bool:
    codes = {str(code or "").strip() for code in issue_codes if str(code or "").strip()}
    if not codes:
        return False
    if codes.intersection(HARD_BLOCK_ISSUE_CODES):
        return False
    return codes.issubset(AUTO_FIXABLE_ISSUE_CODES)


def build_auto_fix_instructions(
    *,
    issue_codes: Iterable[str],
    issue_details: Optional[Iterable[Dict[str, Any]]] = None,
    truth_context: Dict[str, Any],
    attempt: int = 1,
    max_attempts: int = 1,
) -> str:
    codes = sorted({str(code or "").strip() for code in issue_codes if str(code or "").strip()})
    details: List[str] = []
    for issue in issue_details or []:
        if not isinstance(issue, dict):
            continue
        code = str(issue.get("code") or "UNKNOWN").strip()
        path = str(issue.get("path") or "").strip()
        detail = str(issue.get("detail") or "").strip()
        line = f"- {code}"
        if path:
            line += f" @ {path}"
        if detail:
            line += f": {detail}"
        details.append(line)
        if len(details) >= 12:
            break

    sources: List[str] = []
    for row in truth_context.get("search_results", []) or []:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip() or "Source"
        url = str(row.get("url") or "").strip()
        if url.startswith(("http://", "https://")):
            sources.append(f"- {title}: {url}")

    source_block = "\n".join(sources) if sources else "- (none)"
    issues = ", ".join(codes) if codes else "UNKNOWN"
    detail_block = "\n".join(details) if details else "- (none)"
    required_sources = None
    for issue in issue_details or []:
        if not isinstance(issue, dict):
            continue
        if str(issue.get("code") or "").strip() != "SOURCE_LINK_MISSING":
            continue
        try:
            required_sources = int(issue.get("required"))
        except Exception:
            required_sources = None
        if required_sources is not None:
            break

    source_target_line = ""
    if required_sources is not None and required_sources > 0:
        source_target_line = f"- Ensure at least {required_sources} canonical source URL(s) appear in the response.\n"

    return (
        f"Truth verification failed. Retry attempt {attempt} of {max_attempts}.\n"
        f"Issues: {issues}\n"
        "Missed checks:\n"
        f"{detail_block}\n"
        "Strict constraints:\n"
        "- Keep the same facts, numbers, claims, and ordering.\n"
        "- Do not add new claims or remove required claims.\n"
        "- Use only canonical source URLs listed below.\n"
        f"{source_target_line}"
        "- Do not fabricate claim-to-source mapping.\n"
        "- Do not append generic per-sentence links like `[source](url)`.\n"
        "- For citation-like claims, add inline markdown links with descriptive labels (for example `[Ozaki et al., 2025](url)`).\n"
        "- If claim-level mapping is uncertain, keep prose unchanged and place canonical links in a final `Sources:` section.\n"
        "- Remove any URL not present in canonical sources.\n"
        "Canonical sources:\n"
        f"{source_block}"
    )
