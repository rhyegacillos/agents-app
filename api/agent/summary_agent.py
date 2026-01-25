import json
from html import escape
from typing import AsyncGenerator, Dict, Any

from openai import AsyncOpenAI
from .models import Visit
from .utils import generate_with_fallback, get_logger
from . import extraction_agent, coordinator_agent

logger = get_logger(__name__)


system_prompt = """
You are provided with notes written by a doctor from a patient's visit.
Your job is to summarize the visit for the doctor and provide an email.
You may receive extracted text from uploaded files, audio transcripts, or prescription images.
Use that material to improve accuracy, but do not invent details that are not explicitly present.
Reply with exactly three sections in HTML only using this structure:
<section data-section="summary"><h3>Summary of visit for the doctor's records</h3>...</section>
<section data-section="next_steps"><h3>Next steps for the doctor</h3><ul><li>...</li></ul></section>
<section data-section="patient_email"><h3>Draft Email for Patient</h3><p>...</p></section>
Do not include any signature or sign-off in the draft email.
Do not include any text outside the three sections.
"""

TEMPLATES = {
    "generic": {
        "label": "Generic Summary",
        "headings": ["Visit Summary", "Key Findings", "Assessment"],
        "summary_html": (
            "Use this HTML inside the Summary section:\n"
            "<h4>Visit Summary</h4>\n"
            "<p>...</p>\n"
            "<h4>Key Findings</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Assessment</h4>\n"
            "<p>...</p>"
        ),
    },
    "soap": {
        "label": "SOAP",
        "headings": ["Subjective", "Objective", "Assessment", "Plan"],
        "summary_html": (
            "Use this HTML inside the Summary section:\n"
            "<h4>Subjective</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Objective</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Assessment</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Plan</h4>\n"
            "<ul><li>...</li></ul>"
        ),
    },
    "discharge": {
        "label": "Discharge Summary",
        "headings": [
            "Primary Diagnosis",
            "Treatment Provided",
            "Medications",
            "Discharge Instructions",
            "Follow-up & Red Flags",
        ],
        "summary_html": (
            "Use this HTML inside the Summary section:\n"
            "<h4>Primary Diagnosis</h4>\n"
            "<p>...</p>\n"
            "<h4>Treatment Provided</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Medications</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Discharge Instructions</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Follow-up & Red Flags</h4>\n"
            "<ul><li>...</li></ul>"
        ),
    },
    "referral": {
        "label": "Referral Letter",
        "headings": [
            "Reason for Referral",
            "Key Findings",
            "Tests/Imaging",
            "Assessment",
            "Requested Action",
        ],
        "summary_html": (
            "Use this HTML inside the Summary section:\n"
            "<h4>Reason for Referral</h4>\n"
            "<p>...</p>\n"
            "<h4>Key Findings</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Tests/Imaging</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Assessment</h4>\n"
            "<p>...</p>\n"
            "<h4>Requested Action</h4>\n"
            "<ul><li>...</li></ul>"
        ),
    },
    "follow_up": {
        "label": "Follow-Up Visit",
        "headings": [
            "Progress Since Last Visit",
            "Current Symptoms",
            "Medications/Changes",
            "Updated Plan",
            "Next Visit",
        ],
        "summary_html": (
            "Use this HTML inside the Summary section:\n"
            "<h4>Progress Since Last Visit</h4>\n"
            "<p>...</p>\n"
            "<h4>Current Symptoms</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Medications/Changes</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Updated Plan</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Next Visit</h4>\n"
            "<p>...</p>"
        ),
    },
    "surgery": {
        "label": "Surgery Note",
        "headings": ["Procedure", "Findings", "Complications", "Post-Op Plan"],
        "summary_html": (
            "Use this HTML inside the Summary section:\n"
            "<h4>Procedure</h4>\n"
            "<p>...</p>\n"
            "<h4>Findings</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Complications</h4>\n"
            "<p>...</p>\n"
            "<h4>Post-Op Plan</h4>\n"
            "<ul><li>...</li></ul>"
        ),
    },
    "med_review": {
        "label": "Medication Review",
        "headings": ["Current Medications", "Changes Made", "Issues/Side Effects", "Recommendations"],
        "summary_html": (
            "Use this HTML inside the Summary section:\n"
            "<h4>Current Medications</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Changes Made</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Issues/Side Effects</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Recommendations</h4>\n"
            "<ul><li>...</li></ul>"
        ),
    },
}

SECTION_HEADINGS = {
    "summary": "Summary of visit for the doctor's records",
    "next_steps": "Next steps for the doctor",
    "patient_email": "Draft Email for Patient",
}


def get_template(visit: Visit) -> dict:
    template_id = (visit.template_id or "generic").strip()
    return TEMPLATES.get(template_id, TEMPLATES["generic"])


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
        stripped = stripped.lstrip("0123456789. ").strip()
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
    if looks_like_html(cleaned):
        return cleaned

    sections = split_sections(cleaned)
    summary_html = render_summary_section(sections["summary"], template)
    next_steps_html = render_list(sections["next_steps"])
    patient_email_html = render_paragraphs(sections["patient_email"])

    return (
        f"<section data-section=\"summary\"><h3>{SECTION_HEADINGS['summary']}</h3>{summary_html}</section>"
        f"<section data-section=\"next_steps\"><h3>{SECTION_HEADINGS['next_steps']}</h3>{next_steps_html}</section>"
        f"<section data-section=\"patient_email\"><h3>{SECTION_HEADINGS['patient_email']}</h3>{patient_email_html}</section>"
    )


def summary_prompt_for(visit: Visit, context: dict) -> str:
    attachment_block = ""
    if context["attachments"]:
        attachment_block = "\n\n" + "\n\n".join(
            f"{label}:\n{text}" for label, text in context["attachments"]
        )

    template = get_template(visit)

    return f"""Create the summary, next steps and draft email for:
Patient Name: {visit.patient_name}
Date of Visit: {visit.date_of_visit}
Notes:
{context["notes_text"]}{attachment_block}

Template: {template["label"]}
{template["summary_html"]}
Follow the template exactly and do not add or remove headings.
For the Next steps section, use a <ul> list with clear, actionable items.
For the patient email section, use short <p> paragraphs in patient-friendly language."""


async def generate_summary_stream(
    visit: Visit,
    context: Dict[str, Any],
    doctor_info: Dict[str, Any],
    client: AsyncOpenAI,
) -> AsyncGenerator[str, None]:
    
    user_prompt = summary_prompt_for(visit, context)
    prompt = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        # Use fallback logic
        response = await generate_with_fallback(
            client=client,
            messages=prompt,
            # We can override the default chain here if needed
            # models=["gpt-5-nano", "gpt-4o-mini"] 
        )
        raw_text = response.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"Failed to generate summary: {e}")
        # In a real app, you might yield an error event or fallback text
        raw_text = "<p>Error generating summary. Please check logs.</p>"

    template = get_template(visit)
    final_html = ensure_html_summary(raw_text, template)
    
    # Coordinator Agent: Extract actions
    actions = await coordinator_agent.extract_actions(final_html, client)
    
    # Metadata event
    metadata = json.dumps(
        {
            **doctor_info,
            "prescription_text": context.get("prescription_text", ""),
            "prescription_filename": context.get("prescription_filename", ""),
            "prescription_texts": context.get("prescription_texts", []),
            "prescription_filenames": context.get("prescription_filenames", []),
        }
    )
    yield f"event: metadata\ndata: {metadata}\n\n"

    # Actions event
    if actions:
        yield f"event: actions\ndata: {json.dumps(actions)}\n\n"
    
    # Stream the HTML
    lines = final_html.split("\n")
    for line in lines[:-1]:
        yield f"data: {line}\n\n"
        yield "data:  \n"
    if lines:
        yield f"data: {lines[-1]}\n\n"


async def run_summary_pipeline(
    visit: Visit,
    client: AsyncOpenAI,
) -> AsyncGenerator[str, None]:
    """
    Orchestrates the full summary generation pipeline:
    1. Extract text/data from visit files.
    2. Extract doctor info.
    3. Generate and stream summary.
    """
    logger.info(f"Starting summary pipeline for patient: {visit.patient_name}")
    
    # 1. Extraction Phase
    context = await extraction_agent.build_visit_context(visit, client)
    doctor_info = await extraction_agent.extract_doctor_info(context["combined_text"], client)

    # 2. Generation Phase
    async for chunk in generate_summary_stream(visit, context, doctor_info, client):
        yield chunk
