import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from observability import JOB_ID
from services.canonical_renderer import NO_CANONICAL_SOURCES_MESSAGE
from services.storage import _job_key, _upstash_enabled, _upstash_get, _upstash_set
from services.url_utils import normalize_url

_URL_RE = re.compile(r"https?://[^\s<>()]+|(?<![A-Za-z0-9._-])/downloads/[^\s<>()]+", re.IGNORECASE)
_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\((https?://[^)]+|/downloads/[^)]+)\)")
_PLACEHOLDER_RE = re.compile(
    r"\{\{[^}]+\}\}|\[\.\.\.PLACEHOLDER\.\.\.\]|URL_PARAMS_PLACEHOLDER|FILENAME_PLACEHOLDER",
    re.IGNORECASE,
)
_EMAIL_SENT_RE = re.compile(r"\b(email sent|sent successfully|delivery confirmed)\b", re.IGNORECASE)
_PAGE_CLAIM_RE = re.compile(r"\b(\d+)\s+pages?\b", re.IGNORECASE)
_NO_SOURCES_MARKER = "TRUTH_GATE_NO_SOURCES"
_SOURCES_SECTION_RE = re.compile(
    r"(?ims)^\s*(?:#{1,6}\s*)?(?:\*\*)?\s*sources\b(?!\s+of\b)[^\n]*?(?:\*\*)?\s*$([\s\S]*)\Z"
)
_SOURCE_HEADER_LINE_RE = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?(?:\*\*)?\s*sources\b(?!\s+of\b)[^\n]*?(?:\*\*)?\s*$"
)
_CITATION_NEEDS_SOURCE_RE = re.compile(
    r"\b(?:according to|as reported by|per)\b"
    r"|(?:\bet al\.?\b)"
    r"|(?:\barxiv(?::|\s)\d{4}\.\d{4,5}\b)"
    r"|(?:\bdoi:\s*10\.\d{4,9}/\S+)"
    r"|(?:\bpmid:\s*\d+\b)"
    r"|(?:\[\d+(?:\s*,\s*\d+)*\])",
    re.IGNORECASE,
)
_CITATION_PAREN_RE = re.compile(
    r"\((?=[^)]*(?:19|20)\d{2})(?=[^)]*(?:et al\.?|arxiv|doi|pmid|study|survey|paper|report|research))[^)]*\)",
    re.IGNORECASE,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text_for_compare(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _is_no_sources_fallback_message(output: str) -> bool:
    raw = str(output or "")
    if _NO_SOURCES_MARKER in raw:
        return True
    if NO_CANONICAL_SOURCES_MESSAGE in raw:
        return True
    normalized = _normalize_text_for_compare(output)
    canonical = _normalize_text_for_compare(NO_CANONICAL_SOURCES_MESSAGE)
    if normalized == canonical:
        return True
    # Tolerate minor wording/formatting drift while still enforcing intent.
    hints = (
        "no valid source urls were returned by the search tool",
        "retry the search request",
    )
    return all(h in normalized for h in hints)


def _extract_text_payload(payload: Any) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, dict):
        for key in ("text", "message", "output_text", "response"):
            val = payload.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        content = payload.get("content")
        if isinstance(content, list):
            for item in content:
                txt = _extract_text_payload(item)
                if txt:
                    return txt
        return ""
    if isinstance(payload, list):
        for item in payload:
            txt = _extract_text_payload(item)
            if txt:
                return txt
        return ""
    return str(payload).strip()


def _get_field(raw: Any, name: str) -> Any:
    if isinstance(raw, dict):
        return raw.get(name)
    return getattr(raw, name, None)


def _parse_json_string(text: str) -> Optional[Any]:
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("{") or raw.startswith("["):
        try:
            return json.loads(raw)
        except Exception:
            return None
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.IGNORECASE | re.DOTALL)
    if m:
        return _parse_json_string(m.group(1))
    return None


def _unwrap_payload(output: Any, depth: int = 0) -> Any:
    if output is None or depth > 6:
        return output

    for attr in ("structuredContent", "structured_content"):
        val = getattr(output, attr, None)
        if val is not None:
            return _unwrap_payload(val, depth + 1)

    if hasattr(output, "model_dump") and callable(getattr(output, "model_dump")):
        try:
            return _unwrap_payload(output.model_dump(), depth + 1)
        except Exception:
            pass

    if isinstance(output, dict):
        # MCP tool outputs are often wrapped as {"content":[{"type":"text","text":"...json..."}]}
        content = output.get("content")
        if isinstance(content, list) and content:
            unwrapped = _unwrap_payload(content, depth + 1)
            if unwrapped is not None:
                return unwrapped
        for key in (
            "structuredContent",
            "structured_content",
            "output",
            "result",
            "data",
            "payload",
            "value",
            "text",
        ):
            val = output.get(key)
            if isinstance(val, (dict, list)):
                return _unwrap_payload(val, depth + 1)
            if isinstance(val, str):
                parsed = _parse_json_string(val)
                if parsed is not None:
                    return _unwrap_payload(parsed, depth + 1)
        return output

    if isinstance(output, list):
        # Unwrap common MCP content arrays and return first parseable payload.
        for item in output:
            candidate = _unwrap_payload(item, depth + 1)
            if isinstance(candidate, dict) and candidate:
                return candidate
            if isinstance(candidate, str):
                parsed = _parse_json_string(candidate)
                if parsed is not None:
                    return _unwrap_payload(parsed, depth + 1)
        return output

    if isinstance(output, str):
        # Some tool wrappers expose JSON in plain text fields.
        parsed = _parse_json_string(output)
        if parsed is not None:
            return _unwrap_payload(parsed, depth + 1)

    return output


def extract_tool_events(run_result: Any) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    by_call_id: Dict[str, str] = {}
    pending_names: List[str] = []

    for item in getattr(run_result, "new_items", []) or []:
        item_type = getattr(item, "type", "")

        if item_type == "tool_call_item":
            raw = getattr(item, "raw_item", None)
            tool_name = str(_get_field(raw, "name") or "unknown")
            call_id = _get_field(raw, "call_id") or _get_field(raw, "id")
            if call_id:
                by_call_id[str(call_id)] = tool_name
            pending_names.append(tool_name)
            inline_output = _get_field(raw, "output")
            if inline_output is not None:
                events.append({"tool_name": tool_name, "output": inline_output})
            continue

        if item_type == "tool_call_output_item":
            raw = getattr(item, "raw_item", None)
            output = getattr(item, "output", None)
            if output is None:
                output = _get_field(raw, "output")
            call_id = _get_field(raw, "call_id") or _get_field(raw, "id")
            tool_name = by_call_id.get(str(call_id)) if call_id else None
            if not tool_name and pending_names:
                tool_name = pending_names.pop(0)
            events.append({"tool_name": tool_name or "unknown", "output": output})
            continue

        if item_type == "response_output_item":
            raw = getattr(item, "raw_item", None)
            raw_type = str(_get_field(raw, "type") or "").lower()
            if raw_type in {"mcp_call", "function_call"}:
                output = _get_field(raw, "output")
                if output is not None:
                    tool_name = str(_get_field(raw, "name") or "unknown")
                    events.append({"tool_name": tool_name, "output": output})

    return events


def _find_search_rows(payload: Any, depth: int = 0) -> List[Dict[str, Any]]:
    if payload is None or depth > 6:
        return []
    if isinstance(payload, list):
        if payload and all(isinstance(x, dict) for x in payload):
            if any(any(k in row for k in ("url", "link", "href")) for row in payload):
                return [x for x in payload if isinstance(x, dict)]
        rows: List[Dict[str, Any]] = []
        for item in payload:
            rows.extend(_find_search_rows(item, depth + 1))
        return rows
    if isinstance(payload, dict):
        for key in ("results", "web_results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                rows = _find_search_rows(value, depth + 1)
                if rows:
                    return rows
        if isinstance(payload.get("web"), dict):
            rows = _find_search_rows(payload.get("web"), depth + 1)
            if rows:
                return rows
        rows: List[Dict[str, Any]] = []
        for value in payload.values():
            rows.extend(_find_search_rows(value, depth + 1))
        return rows
    if isinstance(payload, str):
        parsed = _parse_json_string(payload)
        if parsed is not None:
            return _find_search_rows(parsed, depth + 1)
    return []


def _normalize_pdf_artifact(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    payload = _unwrap_payload(event.get("output"))
    if not isinstance(payload, dict):
        return None
    status = str(payload.get("status") or "").lower()
    if status and status != "ok":
        return None

    url = payload.get("download_url") or payload.get("public_url")
    filename = payload.get("filename")
    if not url and filename:
        url = f"/downloads/{filename}"
    if not url:
        return None

    return {
        "artifact_id": f"artf_{uuid.uuid4().hex[:12]}",
        "kind": "pdf",
        "source_tool": event.get("tool_name"),
        "download_url": str(url),
        "filename": filename,
        "storage": payload.get("storage"),
        "bucket": payload.get("bucket"),
        "key": payload.get("key"),
        "file_path": payload.get("file_path"),
        "size_bytes": payload.get("size_bytes"),
        "page_count": payload.get("page_count"),
        "status": "ok",
        "created_at": _now_iso(),
    }


def _normalize_email_outcome(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    tool_name = str(event.get("tool_name") or "")
    if "send_resend_email" not in tool_name:
        return None
    payload = _unwrap_payload(event.get("output"))
    text = _extract_text_payload(payload)
    ok = False
    email_id = None

    if isinstance(payload, dict):
        status = str(payload.get("status") or "").strip().lower()
        if status in {"ok", "success", "sent"}:
            ok = True
        email_id = (
            str(payload.get("email_id") or "").strip()
            or str(payload.get("id") or "").strip()
            or None
        )

    if not ok:
        ok = bool(re.search(r"\bemail sent successfully\b", text, re.IGNORECASE))
    if ok and not email_id:
        m = re.search(r"ID:\s*([^\s]+)", text, re.IGNORECASE)
        email_id = m.group(1) if m else None
    return {
        "tool": "send_resend_email",
        "status": "ok" if ok else "error",
        "email_id": email_id,
        "message": text or str(payload or ""),
        "created_at": _now_iso(),
    }


def _normalize_search_results(event: Dict[str, Any]) -> List[Dict[str, str]]:
    payload = _unwrap_payload(event.get("output"))
    rows = _find_search_rows(payload)
    out: List[Dict[str, str]] = []
    seen = set()
    for row in rows:
        url = str(row.get("url") or row.get("link") or row.get("href") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        normalized = normalize_url(url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        title = str(row.get("title") or row.get("name") or "").strip() or url
        out.append({"title": title, "url": normalized})
    return out


def normalize_truth_context(tool_events: List[Dict[str, Any]]) -> Dict[str, Any]:
    artifacts: List[Dict[str, Any]] = []
    outcomes: List[Dict[str, Any]] = []
    search_results: List[Dict[str, str]] = []

    for event in tool_events:
        name = str(event.get("tool_name") or "")
        if "generate_pdf_from_text" in name or "download_pdf" in name:
            artifact = _normalize_pdf_artifact(event)
            if artifact:
                artifacts.append(artifact)
        if "send_resend_email" in name:
            outcome = _normalize_email_outcome(event)
            if outcome:
                outcomes.append(outcome)
        if "brave_web_search" in name or name == "brave_web_search":
            search_results.extend(_normalize_search_results(event))
        else:
            rows = _normalize_search_results(event)
            if rows:
                search_results.extend(rows)

    deduped: List[Dict[str, str]] = []
    seen = set()
    for row in search_results:
        key = normalize_url(str(row.get("url") or "").strip())
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append({"title": str(row.get("title") or key), "url": key})

    return {"artifacts": artifacts, "outcomes": outcomes, "search_results": deduped}


def _source_url_scope(require_sources: bool) -> str:
    if not require_sources:
        return "any"
    scope = str(os.getenv("TRUTH_GATE_SOURCE_URL_SCOPE", "any")).strip().lower()
    if scope in {"sources_section", "sources-only", "sources_only"}:
        return "sources_section"
    return "any"


def _extract_scope_urls(output: str, *, scope: str) -> set[str]:
    text = str(output or "")
    if scope == "sources_section":
        match = _SOURCES_SECTION_RE.search(text)
        if not match:
            return set()
        text = match.group(1) or ""
    urls = {normalize_url(u) for u in _MARKDOWN_LINK_RE.findall(text)}
    urls.update(normalize_url(u) for u in _URL_RE.findall(text))
    return {u for u in urls if u}


def _require_inline_citations(require_sources: bool) -> bool:
    if not require_sources:
        return False
    raw = str(os.getenv("TRUTH_GATE_REQUIRE_INLINE_CITATIONS", "true")).strip().lower()
    return raw not in {"0", "false", "off", "no"}


def _line_needs_inline_source(line: str) -> bool:
    txt = str(line or "").strip()
    if not txt:
        return False
    return bool(_CITATION_NEEDS_SOURCE_RE.search(txt) or _CITATION_PAREN_RE.search(txt))


def _extract_http_urls(text: str) -> set[str]:
    out = set()
    for u in _URL_RE.findall(str(text or "")):
        raw = str(u or "").strip()
        if raw.startswith(("http://", "https://")):
            out.add(normalize_url(raw))
    return out


def _body_without_sources_section(output: str) -> str:
    text = str(output or "")
    match = _SOURCES_SECTION_RE.search(text)
    if not match:
        return text
    return text[: match.start()].rstrip()


def find_pdf_input_invalid_error(tool_events: List[Dict[str, Any]]) -> Optional[str]:
    for event in tool_events:
        if str(event.get("tool_name") or "") != "generate_pdf_from_text":
            continue
        payload = _unwrap_payload(event.get("output"))
        if not isinstance(payload, dict):
            continue
        if str(payload.get("status") or "").lower() != "error":
            continue
        if str(payload.get("code") or "").upper() == "PDF_INPUT_INVALID":
            return str(payload.get("message") or payload.get("error") or "PDF_INPUT_INVALID")
    return None


def persist_truth_context(*, trace_id: Optional[str], session_id: Optional[str], context: Dict[str, Any]) -> None:
    if not trace_id or trace_id == "-" or not _upstash_enabled():
        return
    try:
        ttl = int(os.getenv("TRUTH_GATE_TTL_SECONDS", "86400"))
        key = f"truth_gate:{trace_id}"
        payload = {
            "trace_id": trace_id,
            "job_id": JOB_ID.get(),
            "session_id": session_id,
            "artifacts": context.get("artifacts", []),
            "outcomes": context.get("outcomes", []),
            "search_results": context.get("search_results", []),
            "updated_at": _now_iso(),
        }
        _upstash_set(key, payload, ttl)

        job_id = JOB_ID.get()
        if job_id and job_id != "-":
            job = _upstash_get(_job_key(job_id)) or {"job_id": job_id}
            job["truth_gate_key"] = key
            job["artifact_count"] = len(payload["artifacts"])
            job["outcome_count"] = len(payload["outcomes"])
            job["search_result_count"] = len(payload["search_results"])
            job["updated_at"] = _now_iso()
            _upstash_set(_job_key(job_id), job, int(os.getenv("ASYNC_JOB_TTL_SECONDS", "3600")))
    except Exception:
        return


def persist_truth_gate_verdict(trace_id: Optional[str], verdict: Dict[str, Any]) -> None:
    if not trace_id or trace_id == "-" or not _upstash_enabled():
        return
    try:
        ttl = int(os.getenv("TRUTH_GATE_TTL_SECONDS", "86400"))
        key = f"truth_gate_verdict:{trace_id}"
        payload = {
            "trace_id": trace_id,
            "status": verdict.get("status"),
            "issues": verdict.get("issues", []),
            "message": verdict.get("message"),
            "updated_at": _now_iso(),
        }
        _upstash_set(key, payload, ttl)
    except Exception:
        return


def _artifact_urls(context: Dict[str, Any]) -> List[str]:
    urls: List[str] = []
    seen = set()
    for artifact in context.get("artifacts", []) or []:
        if not isinstance(artifact, dict):
            continue

        url = str(artifact.get("download_url") or "").strip()
        if url.startswith(("http://", "https://", "/downloads/")):
            normalized = normalize_url(url)
            if normalized not in seen:
                seen.add(normalized)
                urls.append(normalized)

        # Allow local download path when filename is explicitly emitted by the tool.
        filename = str(artifact.get("filename") or "").strip()
        if filename:
            safe_name = filename.split("/")[-1].split("\\")[-1].strip()
            if safe_name:
                local_url = normalize_url(f"/downloads/{safe_name}")
                if local_url not in seen:
                    seen.add(local_url)
                    urls.append(local_url)
    return urls


def _search_results(context: Dict[str, Any]) -> List[Dict[str, str]]:
    rows = context.get("search_results")
    if not isinstance(rows, list):
        return []
    out: List[Dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        title = str(row.get("title") or "").strip() or url
        out.append({"title": title, "url": normalize_url(url)})
    return out


def _search_urls(context: Dict[str, Any]) -> List[str]:
    return [r["url"] for r in _search_results(context)]


def _has_email_success(context: Dict[str, Any]) -> bool:
    for outcome in context.get("outcomes", []) or []:
        if outcome.get("tool") == "send_resend_email" and outcome.get("status") == "ok":
            return True
    return False


def _artifact_like_url(url: str) -> bool:
    lower = (url or "").lower()
    return "/downloads/" in lower or ".pdf" in lower or "x-amz-signature" in lower


def _validate_output(
    text: str,
    context: Dict[str, Any],
    *,
    require_sources: bool,
    enforce_canonical_links: bool,
) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    output = str(text or "")
    canonical_artifact_urls = set(_artifact_urls(context))
    canonical_search_urls = set(_search_urls(context))
    present_urls = _URL_RE.findall(output)
    normalized_present_http_urls = {
        normalize_url(u) for u in present_urls if str(u or "").startswith(("http://", "https://"))
    }

    if _PLACEHOLDER_RE.search(output):
        issues.append(
            {
                "code": "LINK_PLACEHOLDER",
                "severity": "error",
                "path": "output",
                "detail": "Placeholder/template link token detected.",
            }
        )

    bad_artifact_urls = [
        u
        for u in present_urls
        if _artifact_like_url(u)
        and canonical_artifact_urls
        and normalize_url(u) not in canonical_artifact_urls
        and normalize_url(u) not in canonical_search_urls
    ]
    if bad_artifact_urls:
        issues.append(
            {
                "code": "LINK_NOT_CANONICAL",
                "severity": "error",
                "path": "output.links",
                "detail": "Output contains artifact-like links not present in canonical tool results.",
                "invalid_urls": bad_artifact_urls,
            }
        )

    if _EMAIL_SENT_RE.search(output) and not _has_email_success(context):
        issues.append(
            {
                "code": "CLAIM_UNVERIFIED_EMAIL_SENT",
                "severity": "error",
                "path": "output.claims.email",
                "detail": "Email delivery claim is not backed by successful send_resend_email outcome.",
            }
        )

    page_claims = [int(v) for v in _PAGE_CLAIM_RE.findall(output)]
    if page_claims and "pdf" in output.lower():
        verified_counts = [
            int(a.get("page_count"))
            for a in (context.get("artifacts", []) or [])
            if isinstance(a.get("page_count"), int) and a.get("page_count") > 0
        ]
        if not verified_counts or not any(c in verified_counts for c in page_claims):
            issues.append(
                {
                    "code": "CLAIM_UNVERIFIED_PAGE_COUNT",
                    "severity": "error",
                    "path": "output.claims.page_count",
                    "detail": "Page-count claim is not backed by canonical artifact metadata.",
                }
            )

    enforce_source_rules = require_sources
    allowed_http_urls = set(canonical_artifact_urls).union(canonical_search_urls)
    if enforce_canonical_links:
        disallowed_http = [
            u
            for u in present_urls
            if u.startswith(("http://", "https://")) and normalize_url(u) not in allowed_http_urls
        ]
        if disallowed_http:
            issues.append(
                {
                    "code": "SOURCE_URL_INVALID",
                    "severity": "error",
                    "path": "output.links",
                    "detail": "Output contains URL(s) not present in canonical tool results.",
                    "invalid_urls": disallowed_http,
                }
            )

    if enforce_source_rules:
        scope = _source_url_scope(require_sources)
        scope_urls = _extract_scope_urls(output, scope=scope)
        header_count = len(_SOURCE_HEADER_LINE_RE.findall(output))
        if header_count > 1:
            issues.append(
                {
                    "code": "SOURCE_SECTION_DUPLICATE",
                    "severity": "error",
                    "path": "output.sources",
                    "detail": "Output contains multiple Sources sections; only one canonical Sources block is allowed.",
                    "count": header_count,
                }
            )
        if not canonical_search_urls:
            if not _is_no_sources_fallback_message(output):
                issues.append(
                    {
                        "code": "SEARCH_CONTEXT_EMPTY",
                        "severity": "error",
                        "path": "context.search_results",
                        "detail": "Search/research response requires canonical source URLs.",
                    }
                )
        else:
            if scope == "sources_section":
                candidate_urls = scope_urls
            else:
                candidate_urls = normalized_present_http_urls
            present = canonical_search_urls.intersection(candidate_urls)
            min_sources_cfg = max(1, int(os.getenv("TRUTH_GATE_MIN_SOURCES", "2")))
            required_sources = min(min_sources_cfg, len(canonical_search_urls))
            if len(present) < required_sources:
                issues.append(
                    {
                        "code": "SOURCE_LINK_MISSING",
                        "severity": "error",
                        "path": "output.sources",
                        "detail": "Insufficient canonical source URLs in output.",
                        "required": required_sources,
                        "present": len(present),
                    }
                )

            if _require_inline_citations(require_sources):
                body = _body_without_sources_section(output)
                for idx, line in enumerate(body.splitlines(), start=1):
                    if not _line_needs_inline_source(line):
                        continue
                    inline_urls = _extract_http_urls(line)
                    if not inline_urls:
                        issues.append(
                            {
                                "code": "SOURCE_LINK_INLINE_MISSING",
                                "severity": "error",
                                "path": f"output.line:{idx}",
                                "detail": "Citation-like claim requires an inline canonical source URL.",
                            }
                        )
                        continue
                    if not canonical_search_urls.intersection(inline_urls):
                        issues.append(
                            {
                                "code": "SOURCE_LINK_INLINE_NONCANONICAL",
                                "severity": "error",
                                "path": f"output.line:{idx}",
                                "detail": "Inline citation URL is not in canonical search sources.",
                            }
                        )

    return issues


def apply_truth_gate(
    output: str,
    context: Dict[str, Any],
    risk_tier: str,
    *,
    require_sources: bool = False,
    enforce_canonical_links: Optional[bool] = None,
) -> Dict[str, Any]:
    normalized = str(output or "")

    if risk_tier != "high":
        return {"status": "pass", "output": normalized, "issues": []}

    if enforce_canonical_links is None:
        enforce_canonical_links = risk_tier == "high"

    issues = _validate_output(
        normalized,
        context,
        require_sources=require_sources,
        enforce_canonical_links=bool(enforce_canonical_links),
    )
    if issues:
        return {
            "status": "block",
            "output": normalized,
            "issues": issues,
            "message": "truth gate blocked unverified action output",
        }
    return {"status": "pass", "output": normalized, "issues": []}
