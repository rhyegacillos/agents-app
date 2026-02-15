import re
from typing import Any, Dict, List


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
_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\((https?://[^)\s]+)\)")
_RAW_URL_RE = re.compile(r"(?<!\]\()https?://[^\s<>()]+")
_SRC_REF_RE = re.compile(r"\[src:(S\d+)\]\((https?://[^)\s]+)\)", re.IGNORECASE)


def _line_has_link(line: str) -> bool:
    return bool(_MARKDOWN_LINK_RE.search(line or "") or _RAW_URL_RE.search(line or ""))


def _line_needs_source_mapping(line: str) -> bool:
    txt = str(line or "")
    if not txt.strip():
        return False
    if _line_has_link(txt):
        return False
    return bool(_CITATION_NEEDS_SOURCE_RE.search(txt) or _CITATION_PAREN_RE.search(txt))


def prepare_sources(search_results: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    seen = set()
    for row in search_results or []:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        if url in seen:
            continue
        seen.add(url)
        title = str(row.get("title") or "").strip() or url
        rows.append({"source_id": f"S{len(rows)+1}", "title": title, "url": url})
    return rows


def build_claim_source_map(text: str, sources: List[Dict[str, str]]) -> Dict[int, Dict[str, str]]:
    # Hard-disabled: heuristic claim->source mapping is not evidence-backed and
    # violates no-fabricated-attribution requirements.
    _ = text
    _ = sources
    return {}


def inject_claim_source_refs(text: str, mappings: Dict[int, Dict[str, str]]) -> str:
    # Hard-disabled: no automatic inline source injection.
    _ = mappings
    return str(text or "")


def extract_used_source_ids(text: str) -> List[str]:
    seen = set()
    out: List[str] = []
    for match in _SRC_REF_RE.finditer(str(text or "")):
        sid = str(match.group(1) or "").strip()
        if sid and sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out


def build_sources_section(sources: List[Dict[str, str]], used_source_ids: List[str]) -> str:
    if not sources:
        return ""
    by_id = {row.get("source_id"): row for row in sources if isinstance(row, dict)}
    ordered_ids = [sid for sid in used_source_ids if sid in by_id]
    if not ordered_ids:
        ordered_ids = [row["source_id"] for row in sources[: max(1, min(5, len(sources)))]]

    lines = ["Sources:"]
    for sid in ordered_ids:
        row = by_id.get(sid) or {}
        title = row.get("title") or sid
        url = row.get("url") or ""
        lines.append(f"- [{sid}]({url}) {title}")
    return "\n".join(lines)
