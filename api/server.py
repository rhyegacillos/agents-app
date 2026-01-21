import os
import base64
import io
import json
import re
from html import escape
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi_clerk_auth import ClerkConfig, ClerkHTTPBearer, HTTPAuthorizationCredentials
from openai import OpenAI
from pypdf import PdfReader
from docx import Document
import resend
from typing import Optional

app = FastAPI()

# Add CORS middleware (allows frontend to call backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Clerk authentication setup
clerk_config = ClerkConfig(jwks_url=os.getenv("CLERK_JWKS_URL"))
clerk_guard = ClerkHTTPBearer(clerk_config)

class Base64File(BaseModel):
    filename: str
    file_b64: str
    mime: Optional[str] = None


class Visit(BaseModel):
    patient_name: str
    date_of_visit: str
    notes: str
    template_id: Optional[str] = "generic"
    uploaded_notes: Optional[str] = None
    uploaded_filename: Optional[str] = None
    uploaded_file_b64: Optional[str] = None
    uploaded_mime: Optional[str] = None
    uploaded_files: Optional[list[Base64File]] = None
    audio_file_b64: Optional[str] = None
    audio_filename: Optional[str] = None
    audio_mime: Optional[str] = None
    audio_files: Optional[list[Base64File]] = None
    image_file_b64: Optional[str] = None
    image_filename: Optional[str] = None
    image_mime: Optional[str] = None
    image_files: Optional[list[Base64File]] = None


class SendEmailRequest(BaseModel):
    to: str
    subject: str
    html: str
    reply_to: str
    clinic_name: str
    language: Optional[str] = "English"

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

def collect_files(
    primary: Optional[list[Base64File]],
    legacy_filename: Optional[str],
    legacy_b64: Optional[str],
    legacy_mime: Optional[str],
    default_name: str,
) -> list[Base64File]:
    files = list(primary or [])
    if legacy_b64 and not files:
        filename = legacy_filename or default_name
        files.append(Base64File(filename=filename, file_b64=legacy_b64, mime=legacy_mime))
    return files

def build_visit_context(visit: Visit, client: OpenAI) -> dict:
    notes_text = visit.notes.strip()
    attachments = []
    prescription_entries = []

    if visit.uploaded_notes:
        filename = visit.uploaded_filename or "consultation attachment"
        attachments.append((f"Uploaded file ({filename})", visit.uploaded_notes.strip()))
    else:
        for uploaded_text, filename in extract_uploaded_texts(visit):
            display_name = filename or "consultation attachment"
            attachments.append((f"Uploaded file ({display_name})", uploaded_text))

    for audio_text, audio_name in extract_audio_transcripts(visit, client):
        display_name = audio_name or "audio recording"
        attachments.append((f"Audio transcript (English) ({display_name})", audio_text))

    for image_text, image_name in extract_image_texts(visit, client):
        display_name = image_name or "prescription image"
        attachments.append((f"Prescription image text ({display_name})", image_text))
        prescription_entries.append((image_text, image_name))

    combined_parts = []
    if notes_text:
        combined_parts.append(notes_text)
    combined_parts.extend([f"{label}:\n{text}" for label, text in attachments])

    prescription_texts = [text for text, _ in prescription_entries]
    prescription_filenames = [name for _, name in prescription_entries]
    first_text = prescription_texts[0] if prescription_texts else ""
    first_filename = prescription_filenames[0] if prescription_filenames else ""

    return {
        "notes_text": notes_text,
        "attachments": attachments,
        "combined_text": "\n\n".join(combined_parts).strip(),
        "prescription_text": first_text,
        "prescription_filename": first_filename,
        "prescription_texts": prescription_texts,
        "prescription_filenames": prescription_filenames,
    }


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


def extract_uploaded_texts(visit: Visit) -> list[tuple[str, str]]:
    files = collect_files(
        visit.uploaded_files,
        visit.uploaded_filename,
        visit.uploaded_file_b64,
        visit.uploaded_mime,
        "attachment",
    )
    results = []
    for file in files:
        text, filename = extract_uploaded_text_from_file(file)
        if text:
            results.append((text, filename))
    return results


def extract_uploaded_text_from_file(file: Base64File) -> tuple[str, str]:
    """Decode and extract text from uploaded file types we support."""
    try:
        raw_bytes = base64.b64decode(file.file_b64)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file encoding for {file.filename or 'attachment'}.",
        ) from exc

    filename = file.filename or "attachment"
    ext = Path(filename).suffix.lower()
    mime = (file.mime or "").lower()

    def ensure_text(text: str) -> str:
        text = text.strip()
        if not text:
            raise HTTPException(
                status_code=400,
                detail=f"Uploaded file {filename} contains no extractable text.",
            )
        return text

    if ext in {".txt", ".md", ".markdown"} or mime.startswith("text/"):
        try:
            return ensure_text(raw_bytes.decode("utf-8", errors="ignore")), filename
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Unable to read text file {filename}.") from exc

    if ext == ".pdf" or mime == "application/pdf":
        try:
            reader = PdfReader(io.BytesIO(raw_bytes))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            return ensure_text(text), filename
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Unable to read PDF file {filename}.") from exc

    if ext in {".docx", ".doc"} or mime in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    }:
        try:
            document = Document(io.BytesIO(raw_bytes))
            text = "\n".join(p.text for p in document.paragraphs)
            return ensure_text(text), filename
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Unable to read Word document {filename}. Please upload a DOCX file.",
            ) from exc

    raise HTTPException(
        status_code=400,
        detail=f"Unsupported file type for {filename}. Please upload PDF, DOCX, or text.",
    )


def extract_audio_transcripts(visit: Visit, client: OpenAI) -> list[tuple[str, str]]:
    files = collect_files(
        visit.audio_files,
        visit.audio_filename,
        visit.audio_file_b64,
        visit.audio_mime,
        "audio",
    )
    results = []
    for file in files:
        text, filename = extract_audio_transcript_from_file(file, client)
        if text:
            results.append((text, filename))
    return results


def extract_audio_transcript_from_file(file: Base64File, client: OpenAI) -> tuple[str, str]:
    """Transcribe uploaded audio to English using Whisper."""
    try:
        raw_bytes = base64.b64decode(file.file_b64)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid audio encoding for {file.filename or 'audio'}.",
        ) from exc

    if len(raw_bytes) > 25 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Audio file {file.filename or 'audio'} is too large (max 25MB).",
        )

    filename = file.filename or "audio"
    ext = Path(filename).suffix.lower()
    mime = (file.mime or "").lower()
    allowed_ext = {".mp3", ".m4a", ".wav", ".webm", ".ogg", ".mp4", ".aac"}

    if ext and ext not in allowed_ext and not mime.startswith("audio/") and mime != "video/mp4":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported audio type for {filename}. "
                "Please upload MP3, M4A, WAV, WEBM, OGG, MP4, or AAC."
            ),
        )

    audio_buffer = io.BytesIO(raw_bytes)
    audio_buffer.name = filename

    try:
        transcription = client.audio.translations.create(
            model="whisper-1",
            file=audio_buffer,
        )
        text = (transcription.text or "").strip()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to transcribe audio {filename}.") from exc

    if not text:
        raise HTTPException(status_code=400, detail=f"Audio transcript is empty for {filename}.")

    return text, filename


def extract_image_texts(visit: Visit, client: OpenAI) -> list[tuple[str, str]]:
    files = collect_files(
        visit.image_files,
        visit.image_filename,
        visit.image_file_b64,
        visit.image_mime,
        "prescription",
    )
    results = []
    for file in files:
        text, filename = extract_image_text_from_file(file, client)
        if text:
            results.append((text, filename))
    return results


def extract_image_text_from_file(file: Base64File, client: OpenAI) -> tuple[str, str]:
    """Extract and translate handwritten prescription text to English."""
    try:
        raw_bytes = base64.b64decode(file.file_b64)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid image encoding for {file.filename or 'prescription'}.",
        ) from exc

    if len(raw_bytes) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Image file {file.filename or 'prescription'} is too large (max 10MB).",
        )

    filename = file.filename or "prescription"
    ext = Path(filename).suffix.lower()
    mime = (file.mime or "").lower()
    allowed_ext = {".png", ".jpg", ".jpeg", ".webp"}

    if ext and ext not in allowed_ext and not mime.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type for {filename}. Please upload PNG, JPG, or WEBP.",
        )

    if not mime.startswith("image/"):
        if ext == ".png":
            mime = "image/png"
        elif ext in {".jpg", ".jpeg"}:
            mime = "image/jpeg"
        elif ext == ".webp":
            mime = "image/webp"
        else:
            mime = "image/png"

    data_url = f"data:{mime};base64,{file.file_b64}"
    system = (
        "You are a medical transcription assistant. "
        "Extract text from a handwritten medical prescription image and translate to English. "
        "Do not guess any words or medications. "
        "If something is unclear, write [illegible]. "
        "Return plain text only."
    )
    user = (
        "Transcribe the prescription using this format:\n"
        "Medication: <name or [illegible]>\n"
        "Dose: <dose or [illegible]>\n"
        "Directions: <directions or [illegible]>\n"
        "Duration: <duration or [illegible]>\n"
        "Notes: <notes or [illegible]>\n\n"
        "Repeat for each medication, separated by a blank line."
    )

    try:
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            temperature=0,
        )
        text = (response.choices[0].message.content or "").strip()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unable to read prescription image {filename}.",
        ) from exc

    if not text:
        raise HTTPException(
            status_code=400,
            detail=f"Prescription image {filename} contains no extractable text.",
        )

    return text, filename


def extract_doctor_info(source_text: str, client: OpenAI) -> dict:
    if not source_text.strip():
        return {
            "doctor_name": "",
            "doctor_phone": "",
            "clinic_name": "",
            "doctor_email": "",
        }

    system = (
        "You extract doctor contact details from clinical notes. "
        "Return ONLY valid JSON with keys: doctor_name, doctor_phone, clinic_name, doctor_email. "
        "Use the exact substrings from the source. "
        "If a value is not explicitly present, return an empty string for that key. "
        "Do not guess or fabricate."
    )
    user = f"Source text:\n{source_text}\n\nReturn JSON only."

    try:
        response = client.chat.completions.create(
            model="gpt-5-nano",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
        )
        content = response.choices[0].message.content or ""
    except Exception:
        return {
            "doctor_name": "",
            "doctor_phone": "",
            "clinic_name": "",
            "doctor_email": "",
        }

    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {
            "doctor_name": "",
            "doctor_phone": "",
            "clinic_name": "",
            "doctor_email": "",
        }

    try:
        data = json.loads(content[start : end + 1])
    except Exception:
        return {
            "doctor_name": "",
            "doctor_phone": "",
            "clinic_name": "",
            "doctor_email": "",
        }

    def normalize(value: str) -> str:
        return value.strip()

    def normalize_space(value: str) -> str:
        return " ".join(value.lower().split())

    def normalize_no_punct(value: str) -> str:
        return re.sub(r"[^\w\s]", "", normalize_space(value))

    def matches_text(value: str, source: str) -> bool:
        if not value:
            return False
        value_norm = normalize_space(value)
        if value_norm and value_norm in source:
            return True
        value_no_punct = normalize_no_punct(value)
        if value_no_punct and value_no_punct in normalize_no_punct(source):
            return True
        return False

    source_lower = source_text.lower()
    source_normalized = normalize_space(source_text)
    source_digits = re.sub(r"\D", "", source_text)

    doctor_name = normalize(str(data.get("doctor_name", "")))
    doctor_phone = normalize(str(data.get("doctor_phone", "")))
    clinic_name = normalize(str(data.get("clinic_name", "")))
    doctor_email = normalize(str(data.get("doctor_email", "")))

    if doctor_name and not matches_text(doctor_name, source_normalized):
        doctor_name = ""
    if doctor_phone:
        phone_digits = re.sub(r"\D", "", doctor_phone)
        if phone_digits and phone_digits not in source_digits:
            doctor_phone = ""
    if clinic_name and not matches_text(clinic_name, source_normalized):
        clinic_name = ""
    if doctor_email and normalize_space(doctor_email) not in source_lower:
        doctor_email = ""

    if not doctor_name:
        label_patterns = [
            r"(?:Physician|Doctor|Provider|Clinician|Attending|Consultant)\s*[:\-]\s*([^\n\r]+)",
            r"(?:Physician|Doctor|Provider|Clinician|Attending|Consultant)\s+(Dr\.?\s+[^\n\r]+)",
        ]
        for pattern in label_patterns:
            match = re.search(pattern, source_text, re.IGNORECASE)
            if not match:
                continue
            candidate = match.group(1).strip()
            candidate = re.split(r"\s{2,}", candidate)[0].strip()
            candidate = re.split(r"\s+\w+\s*:", candidate)[0].strip()
            if matches_text(candidate, source_normalized):
                doctor_name = candidate
                break

    return {
        "doctor_name": doctor_name,
        "doctor_phone": doctor_phone,
        "clinic_name": clinic_name,
        "doctor_email": doctor_email,
    }


def translate_email_html(html: str, language: str, client: OpenAI) -> str:
    if not html.strip():
        return html
    system = (
        "You translate HTML email content. "
        "Translate only the human-readable text, not the HTML tags or attributes. "
        "Preserve formatting, links, emails, numbers, medication names, and proper nouns. "
        "Return HTML only, no extra commentary."
    )
    user = f"Target language: {language}\n\nHTML:\n{html}"

    try:
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_TRANSLATE_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
        )
        translated = (response.choices[0].message.content or "").strip()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to translate email.") from exc

    if not translated:
        raise HTTPException(status_code=502, detail="Translated email is empty.")

    return translated

@app.post("/api/consultation")
def consultation_summary(
    visit: Visit,
    creds: HTTPAuthorizationCredentials = Depends(clerk_guard),
):
    user_id = creds.decoded["sub"]
    client = OpenAI()
    
    context = build_visit_context(visit, client)
    doctor_info = extract_doctor_info(context["combined_text"], client)
    user_prompt = summary_prompt_for(visit, context)
    prompt = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    
    response = client.chat.completions.create(
        model="gpt-5-nano",
        messages=prompt,
    )
    raw_text = response.choices[0].message.content or ""
    template = get_template(visit)
    final_html = ensure_html_summary(raw_text, template)

    def event_stream():
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
        lines = final_html.split("\n")
        for line in lines[:-1]:
            yield f"data: {line}\n\n"
            yield "data:  \n"
        if lines:
            yield f"data: {lines[-1]}\n\n"
    
    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/send-email")
def send_email(
    payload: SendEmailRequest,
    creds: HTTPAuthorizationCredentials = Depends(clerk_guard),
):
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing RESEND_API_KEY.")

    if not payload.reply_to.strip():
        raise HTTPException(status_code=400, detail="Doctor email is required for reply-to.")
    if not payload.clinic_name.strip():
        raise HTTPException(status_code=400, detail="Clinic name is required for email header.")

    sender = os.getenv("RESEND_FROM", "no-reply@agentairg.site")
    sender_email = sender
    if "<" in sender and ">" in sender:
        sender_email = sender.split("<", 1)[1].split(">", 1)[0].strip()

    clinic_name = payload.clinic_name.strip().replace("\n", " ").replace("\r", " ")
    clinic_name = clinic_name.replace("<", "").replace(">", "")
    from_header = f"{clinic_name} <{sender_email}>"
    resend.api_key = api_key

    language = (payload.language or "English").strip()
    html = payload.html
    if language and language.lower() not in {"english", "en", "en-us", "en-gb"}:
        client = OpenAI()
        html = translate_email_html(html, language, client)

    try:
        response = resend.Emails.send(
            {
                "from": from_header,
                "to": payload.to,
                "subject": payload.subject,
                "html": html,
                "reply_to": payload.reply_to,
            }
        )
    except Exception as exc:
        detail = str(exc) or "Unable to send email."
        raise HTTPException(status_code=502, detail=detail) from exc

    email_id = None
    if isinstance(response, dict):
        email_id = response.get("id")

    return {"status": "sent", "id": email_id}

@app.get("/health")
def health_check():
    """Health check endpoint for AWS App Runner"""
    return {"status": "healthy"}

# Serve static files (our Next.js export) - MUST BE LAST!
static_path = Path("static")
if static_path.exists():
    # Serve index.html for the root path
    @app.get("/")
    async def serve_root():
        return FileResponse(static_path / "index.html")
    
    # Mount static files for all other routes
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
