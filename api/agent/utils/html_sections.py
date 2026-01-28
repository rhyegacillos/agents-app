from html import escape, unescape
import re
from typing import Dict

SECTION_HEADINGS: Dict[str, str] = {
    "summary": "Summary of visit for the doctor's records",
    "next_steps": "Next steps for the doctor",
    "patient_email": "Draft Email for Patient",
}


def looks_like_html(text: str) -> bool:
    return "<section" in text and 'data-section="summary"' in text


def normalize_heading(text: str) -> str:
    return text.strip().rstrip(":").lower()


def split_sections(text: str) -> dict:
    sections = {key: [] for key in SECTION_HEADINGS}
    current = None
    for line in (text or "").splitlines():
        stripped = line.strip()
        matched = None
        if stripped:
            for key, heading in SECTION_HEADINGS.items():
                if normalize_heading(stripped) == normalize_heading(heading):
                    matched = key
                    current = key
                    break
        if matched:
            continue
        if current is None:
            sections["summary"].append(line)
        else:
            sections[current].append(line)
    return sections


def render_paragraphs(lines: list[str]) -> str:
    paragraphs = []
    buffer = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if buffer:
                paragraphs.append(" ".join(buffer))
                buffer = []
            continue
        buffer.append(stripped)
    if buffer:
        paragraphs.append(" ".join(buffer))

    if not paragraphs:
        return "<p></p>"

    return "".join(f"<p>{escape(p)}</p>" for p in paragraphs)


def render_list(lines: list[str]) -> str:
    items = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        stripped = stripped.lstrip("-•*").strip()
        stripped = stripped.lstrip("0123456789. )").strip()
        items.append(stripped)
    if not items:
        return "<ul><li></li></ul>"
    return "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in items) + "</ul>"


def render_summary_section(lines: list[str], template: dict) -> str:
    headings = template.get("headings", [])
    buckets = {heading: [] for heading in headings}
    current = None

    for line in lines:
        stripped = line.strip()
        matched = None
        if stripped:
            for heading in headings:
                if normalize_heading(stripped) == normalize_heading(heading):
                    matched = heading
                    current = heading
                    break
        if matched:
            continue
        if current is None and headings:
            current = headings[0]
        if current:
            buckets[current].append(line)

    parts = []
    for heading in headings:
        parts.append(f"<h4>{escape(heading)}</h4>")
        content_lines = buckets.get(heading, [])
        has_bullets = any(line.strip().startswith(("-", "•", "*")) for line in content_lines)
        if has_bullets:
            parts.append(render_list(content_lines))
        else:
            parts.append(render_paragraphs(content_lines))
    return "".join(parts)


def ensure_html_summary(raw: str, template: dict) -> str:
    cleaned = (raw or "").strip()
    
    # If it's not HTML at all, convert the whole thing from markdown-like text
    if not looks_like_html(cleaned):
        sections = split_sections(cleaned)
        summary_html = render_summary_section(sections["summary"], template)
        next_steps_html = render_list(sections["next_steps"])
        patient_email_html = render_paragraphs(sections["patient_email"])

        return (
            f"<section data-section=\"summary\"><h3>{SECTION_HEADINGS['summary']}</h3>{summary_html}</section>"
            f"<section data-section=\"next_steps\"><h3>{SECTION_HEADINGS['next_steps']}</h3>{next_steps_html}</section>"
            f"<section data-section=\"patient_email\"><h3>{SECTION_HEADINGS['patient_email']}</h3>{patient_email_html}</section>"
        )

    # If it is HTML, ensure all three sections are present, appending if necessary.
    final_html = cleaned
    if 'data-section="summary"' not in final_html:
        final_html += f"<section data-section=\"summary\"><h3>{SECTION_HEADINGS['summary']}</h3><p>Not documented.</p></section>"
    if 'data-section="next_steps"' not in final_html:
        final_html += f"<section data-section=\"next_steps\"><h3>{SECTION_HEADINGS['next_steps']}</h3><ul><li>Not documented.</li></ul></section>"
    if 'data-section="patient_email"' not in final_html:
        final_html += f"<section data-section=\"patient_email\"><h3>{SECTION_HEADINGS['patient_email']}</h3><p>Not documented.</p></section>"
        
    return final_html


def html_to_text(html: str) -> str:
    if not html:
        return ""

    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</(h[1-6]|p|li|ul|ol|section)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)

    lines = [line.strip() for line in text.splitlines()]
    cleaned_lines = []
    last_blank = False
    for line in lines:
        if not line:
            if not last_blank:
                cleaned_lines.append("")
                last_blank = True
            continue
        cleaned_lines.append(line)
        last_blank = False

    return "\n".join(cleaned_lines).strip()
