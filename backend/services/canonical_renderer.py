import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from services.url_utils import normalize_url

_PDF_INTENT_RE = re.compile(r"\b(pdf|download|export|report)\b", re.IGNORECASE)
_EMAIL_INTENT_RE = re.compile(r"\b(email|mail|send|resend)\b", re.IGNORECASE)
_SOURCE_HEADER_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*)?\s*sources\b(?!\s+of\b)[^\n]*?(?:\*\*)?\s*$",
    re.IGNORECASE,
)
_SOURCE_ITEM_RE = re.compile(
    r"^\s*(?:[-*+]\s+|\d+\.\s+).+$"
    r"|^\s*\[[^\]]+\]\([^)]+\)\s*$"
    r"|^\s*https?://\S+\s*$",
    re.IGNORECASE,
)
_SOURCE_META_LINE_RE = re.compile(
    r"\b(?:source|sources|citation|citations|canonical|brave search|reference|references|inline)\b",
    re.IGNORECASE,
)
_MARKDOWN_URL_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+|/downloads/[^)\s]+)\)")
_RAW_URL_RE = re.compile(r"(?<!\]\()https?://[^\s<>()]+|(?<![A-Za-z0-9._-])/downloads/[^\s<>()]+")
NO_CANONICAL_SOURCES_MESSAGE = (
    "I couldn't include canonical web sources because no valid source URLs were returned by the search tool. "
    "Please retry the search request."
)


def _latest_pdf_artifact(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    artifacts = context.get("artifacts", []) or []
    for artifact in reversed(artifacts):
        if not isinstance(artifact, dict):
            continue
        if str(artifact.get("kind") or "").lower() != "pdf":
            continue
        url = str(artifact.get("download_url") or "").strip()
        if url:
            return artifact
    return None


def _latest_email_outcome(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    outcomes = context.get("outcomes", []) or []
    for outcome in reversed(outcomes):
        if not isinstance(outcome, dict):
            continue
        if outcome.get("tool") == "send_resend_email":
            return outcome
    return None


def _canonical_source_lines(context: Dict[str, Any]) -> List[str]:
    rows = context.get("search_results", []) or []
    max_sources = max(1, int(os.getenv("TRUTH_GATE_RENDER_MAX_SOURCES", "8")))
    lines: List[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw = str(row.get("url") or "").strip()
        if not raw.startswith(("http://", "https://")):
            continue
        url = normalize_url(raw)
        if url in seen:
            continue
        seen.add(url)
        title = str(row.get("title") or "").strip() or raw
        lines.append(f"- [{title}]({raw})")  # keep raw for display if you want
        if len(lines) >= max_sources:
            break
    return lines


def _canonical_urls(context: Dict[str, Any]) -> set[str]:
    urls: set[str] = set()
    for row in context.get("search_results", []) or []:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        if url.startswith(("http://", "https://")):
            urls.add(normalize_url(url))
    for artifact in context.get("artifacts", []) or []:
        if not isinstance(artifact, dict):
            continue
        url = str(artifact.get("download_url") or "").strip()
        if url.startswith(("http://", "https://", "/downloads/")):
            urls.add(normalize_url(url))
        filename = str(artifact.get("filename") or "").strip()
        if filename:
            safe_name = filename.split("/")[-1].split("\\")[-1].strip()
            if safe_name:
                urls.add(normalize_url(f"/downloads/{safe_name}"))
    return urls


def _strip_noncanonical_http_links(text: str, allowed_urls: set[str]) -> str:
    if not allowed_urls:
        return text

    def _md_repl(match: re.Match[str]) -> str:
        label = match.group(1)
        url = match.group(2)
        if normalize_url(url) in allowed_urls:
            return match.group(0)
        return f"{label} (link removed)"

    out = _MARKDOWN_URL_RE.sub(_md_repl, text)

    def _raw_repl(match: re.Match[str]) -> str:
        url = match.group(0)
        return url if normalize_url(url) in allowed_urls else "[unverified link removed]"

    return _RAW_URL_RE.sub(_raw_repl, out)


def _is_allowlisted_url(url: str, allowed_urls: set[str]) -> bool:
    raw = str(url or "").strip()
    if not raw.startswith(("http://", "https://", "/downloads/")):
        return False
    return normalize_url(raw) in allowed_urls


def _preferred_pdf_url(pdf: Dict[str, Any]) -> str:
    raw = str(pdf.get("download_url") or "").strip()
    if raw.startswith("/downloads/"):
        return raw
    if raw.startswith(("http://", "https://")):
        try:
            parsed = urlsplit(raw)
            path = parsed.path or ""
            host = (parsed.netloc or "").lower()
            public_hosts = set()
            for key in ("PUBLIC_BASE_URL", "API_PUBLIC_URL", "BASE_URL"):
                base = str(os.getenv(key) or "").strip()
                if not base:
                    continue
                try:
                    public_hosts.add((urlsplit(base).netloc or "").lower())
                except Exception:
                    continue

            can_rewrite_to_relative = (
                host.startswith("localhost")
                or host.startswith("127.0.0.1")
                or (host in public_hosts if host else False)
            )
            if path.startswith("/downloads/") and can_rewrite_to_relative:
                tail = path.split("/downloads/", 1)[1].strip("/")
                if tail:
                    return f"/downloads/{tail}"
        except Exception:
            pass
        # Preserve non-local absolute URLs (e.g. S3 pre-signed URLs).
        return raw

    filename = str(pdf.get("filename") or "").strip()
    if filename:
        safe_name = filename.split("/")[-1].split("\\")[-1].strip()
        if safe_name:
            return f"/downloads/{safe_name}"
    return raw


def _strip_existing_sources_blocks(text: str) -> str:
    lines = str(text or "").splitlines()
    out: List[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if not _SOURCE_HEADER_RE.match(line or ""):
            out.append(line)
            i += 1
            continue

        i += 1
        # Drop the source-list block under this heading (bullets, numbered items, links, blank separators).
        while i < n:
            cur = lines[i]
            if not str(cur or "").strip():
                i += 1
                continue
            if _SOURCE_HEADER_RE.match(cur or ""):
                i += 1
                continue
            if _SOURCE_ITEM_RE.match(cur or ""):
                i += 1
                continue
            if re.match(r"^\s{2,}\S", cur or ""):
                i += 1
                continue
            if _SOURCE_META_LINE_RE.search(cur or ""):
                i += 1
                continue
            break

    return "\n".join(out)


def render_high_risk_output(
    *,
    user_message: str,
    llm_output: str,
    context: Dict[str, Any],
    require_sources: bool = False,
) -> str:
    text = str(llm_output or "").strip()
    user_text = str(user_message or "")
    wants_pdf = bool(_PDF_INTENT_RE.search(user_text))
    wants_email = bool(_EMAIL_INTENT_RE.search(user_text))
    allowed_urls = _canonical_urls(context)

    def _clean(output: str) -> str:
        return _strip_noncanonical_http_links(str(output or ""), allowed_urls)

    pdf = _latest_pdf_artifact(context)
    email = _latest_email_outcome(context)

    if wants_email and email:
        if email.get("status") == "ok":
            email_id = str(email.get("email_id") or "").strip()
            line = "Email sent successfully."
            if email_id:
                line += f" ID: `{email_id}`."
            if pdf:
                download_url = _preferred_pdf_url(pdf)
                if _is_allowlisted_url(download_url, allowed_urls):
                    line += f" [Download PDF]({download_url})"
            return _clean(line)
        message = str(email.get("message") or "Email send failed.").strip()
        return _clean(f"Email send failed: {message}")

    if wants_pdf and pdf:
        line = "Your PDF is ready."
        download_url = _preferred_pdf_url(pdf)
        if _is_allowlisted_url(download_url, allowed_urls):
            line += f" [Download PDF]({download_url})"
        page_count = pdf.get("page_count")
        if isinstance(page_count, int) and page_count > 0:
            line += f"\n\nVerified page count: {page_count}."
        return _clean(line)

    if require_sources:
        source_lines = _canonical_source_lines(context)
        if not source_lines:
            return _clean(NO_CANONICAL_SOURCES_MESSAGE)
        base = _strip_existing_sources_blocks(text).rstrip()
        base = _clean(base)
        sources = "Sources:\n" + "\n".join(source_lines)
        if base:
            return _clean(f"{base}\n\n{sources}")
        return _clean(sources)

    return _clean(text)
