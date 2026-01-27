import re
from typing import List, Dict, Any, Iterable

# --- This function was missing ---
def _is_heading_sentence(sentence: str) -> bool:
    """Checks if a sentence is a common section heading."""
    normalized = sentence.strip().strip(":").lower()
    if not normalized:
        return True
    # A set of common headings found in clinical notes
    headings = {
        "summary of visit for the doctor's records",
        "summary of visit for the doctor’s records",
        "next steps for the doctor",
        "draft email for patient",
        "subjective",
        "objective",
        "assessment",
        "plan",
        "history of present illness",
        "review of systems",
        "past medical history",
        "physical examination",
        "medications",
        "allergies",
        "social history",
        "family history",
        "current medications",
        "changes made",
        "issues/side effects",
        "recommendations",
    }
    return normalized in headings
# ------------------------------------

def normalize_whitespace(text: str) -> str:
    if not text:
        return ""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    cleaned = []
    blank = False
    for line in lines:
        if not line.strip():
            if not blank:
                cleaned.append("")
                blank = True
            continue
        cleaned.append(line)
        blank = False
    return "\n".join(cleaned).strip()


ABBREVIATION_TOKENS = {
    "dr.",
    "mr.",
    "ms.",
    "mrs.",
    "prof.",
    "sr.",
    "jr.",
    "st.",
}


def split_sentences(text: str) -> List[str]:
    if not text:
        return []
    normalized = normalize_whitespace(text)
    if not normalized:
        return []
    sentences: List[str] = []
    for block in normalized.split("\n"):
        block = block.strip()
        if not block:
            continue
        parts = re.split(r"(?<=[.!?])\s+", block)
        for part in parts:
            piece = part.strip()
            if piece:
                sentences.append(piece)
    if not sentences:
        return []
    merged: List[str] = []
    for sentence in sentences:
        if not merged:
            merged.append(sentence)
            continue
        prev = merged[-1].strip()
        if prev.lower().endswith(tuple(ABBREVIATION_TOKENS)):
            merged[-1] = f"{prev} {sentence}".strip()
        else:
            merged.append(sentence)
    return merged


def _split_long_text(text: str, max_chars: int) -> Iterable[str]:
    if len(text) <= max_chars:
        yield text
        return
    words = text.split()
    current: List[str] = []
    length = 0
    for word in words:
        if length + len(word) + 1 > max_chars and current:
            yield " ".join(current)
            current = [word]
            length = len(word)
            continue
        current.append(word)
        length += len(word) + 1
    if current:
        yield " ".join(current)


def chunk_text(text: str, max_chars: int = 500) -> List[str]:
    if not text:
        return []
    normalized = normalize_whitespace(text)
    if not normalized:
        return []
    chunks: List[str] = []
    for paragraph in normalized.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        sentences = split_sentences(paragraph)
        if not sentences:
            continue
        current = ""
        for sentence in sentences:
            if not current:
                current = sentence
                continue
            if len(current) + 1 + len(sentence) <= max_chars:
                current = f"{current} {sentence}"
            else:
                if len(current) <= max_chars:
                    chunks.append(current.strip())
                else:
                    for chunk in _split_long_text(current, max_chars):
                        chunks.append(chunk.strip())
                current = sentence
        if current:
            if len(current) <= max_chars:
                chunks.append(current.strip())
            else:
                for chunk in _split_long_text(current, max_chars):
                    chunks.append(chunk.strip())
    return chunks


def build_source_chunks(context: Dict[str, Any], max_chars: int = 500) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    counters = {"N": 0, "A": 0, "H": 0, "R": 0, "G": 0}

    def add_chunks(prefix: str, source: str, label: str, text: str, sources: List[Dict[str, str]] | None = None):
        for chunk in chunk_text(text, max_chars=max_chars):
            counters[prefix] += 1
            chunks.append(
                {
                    "id": f"{prefix}{counters[prefix]}",
                    "source": source,
                    "label": label,
                    "text": chunk,
                    "sources": sources or [],
                }
            )

    notes = context.get("notes_text", "")
    if notes:
        add_chunks("N", "Notes", "Notes", notes)

    for label, text in context.get("attachments", []) or []:
        if text:
            add_chunks("A", "Upload", label, text)

    history = context.get("patient_history", "")
    if history:
        add_chunks("H", "History", "Patient History", history)

    for entry in _coerce_findings(context.get("research_findings")):
        if entry["text"]:
            add_chunks("R", "Research", "Research Findings", entry["text"], entry["sources"])

    for entry in _coerce_findings(context.get("guideline_findings")):
        if entry["text"]:
            add_chunks("G", "Guidelines", "Guideline Findings", entry["text"], entry["sources"])

    return chunks


def _coerce_findings(value: Any) -> List[Dict[str, Any]]:
    if not value:
        return []
    items = value if isinstance(value, list) else [value]
    normalized: List[Dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            summary = str(item.get("summary") or item.get("text") or "").strip()
            sources = item.get("sources") or []
            normalized.append({"text": summary, "sources": _normalize_sources(sources)})
        else:
            text = str(item).strip()
            if text:
                normalized.append({"text": text, "sources": []})
    return normalized


def _normalize_sources(sources: Any) -> List[Dict[str, str]]:
    if not sources:
        return []
    cleaned: List[Dict[str, str]] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        url = str(source.get("url") or "").strip()
        if not url:
            continue
        title = str(source.get("title") or "").strip()
        cleaned.append({"title": title, "url": url})
    return cleaned