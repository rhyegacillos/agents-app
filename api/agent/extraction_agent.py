import base64
import io
import json
import os
import re
from pathlib import Path
from typing import List, Optional, Tuple, Any

from fastapi import HTTPException
from pypdf import PdfReader
from docx import Document
from openai import AsyncOpenAI

from .models import Visit, Base64File
from .utils import get_logger

logger = get_logger(__name__)


def collect_files(
    primary: Optional[List[Base64File]],
    legacy_filename: Optional[str],
    legacy_b64: Optional[str],
    legacy_mime: Optional[str],
    default_name: str,
) -> List[Base64File]:
    files = list(primary or [])
    if legacy_b64 and not files:
        filename = legacy_filename or default_name
        files.append(Base64File(filename=filename, file_b64=legacy_b64, mime=legacy_mime))
    return files


def extract_uploaded_text_from_file(file: Base64File) -> Tuple[str, str]:
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

    if ext in {'.txt', '.md', '.markdown'} or mime.startswith("text/"):
        try:
            return ensure_text(raw_bytes.decode("utf-8", errors="ignore")), filename
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Unable to read text file {filename}.") from exc

    if ext == ".pdf" or mime == "application/pdf":
        try:
            reader = PdfReader(io.BytesIO(raw_bytes))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            # Collapse multiple newlines into single newlines, preserving paragraph breaks
            text = re.sub(r'(\n\s*){2,}', '\n', text).strip()
            return ensure_text(text), filename
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Unable to read PDF file {filename}.") from exc

    if ext in {'.docx', '.doc'} or mime in {
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


def extract_uploaded_texts(visit: Visit) -> List[Tuple[str, str]]:
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


async def extract_audio_transcript_from_file(file: Base64File, client: AsyncOpenAI) -> Tuple[str, str]:
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
    allowed_ext = {'.mp3', '.m4a', '.wav', '.webm', '.ogg', '.mp4', '.aac'}

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
        transcription = await client.audio.translations.create(
            model="whisper-1",
            file=audio_buffer,
        )
        text = (transcription.text or "").strip()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to transcribe audio {filename}.") from exc

    if not text:
        raise HTTPException(status_code=400, detail=f"Audio transcript is empty for {filename}.")

    return text, filename


async def extract_audio_transcripts(visit: Visit, client: AsyncOpenAI) -> List[Tuple[str, str]]:
    files = collect_files(
        visit.audio_files,
        visit.audio_filename,
        visit.audio_file_b64,
        visit.audio_mime,
        "audio",
    )
    results = []
    for file in files:
        text, filename = await extract_audio_transcript_from_file(file, client)
        if text:
            results.append((text, filename))
    return results


async def extract_image_text_from_file(file: Base64File, client: AsyncOpenAI) -> Tuple[str, str]:
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
    allowed_ext = {'.png', '.jpg', '.jpeg', '.webp'}

    if ext and ext not in allowed_ext and not mime.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type for {filename}. Please upload PNG, JPG, or WEBP.",
        )

    if not mime.startswith("image/"):
        if ext == ".png":
            mime = "image/png"
        elif ext in {'.jpg', '.jpeg'}:
            mime = "image/jpeg"
        elif ext == ".webp":
            mime = "image/webp"
        else:
            mime = "image/png"

    data_url = f"data:{mime};base64,{file.file_b64}"
    system = (
        "You are a medical transcription assistant. "
        "Extract text from a handwritten prescription image and translate to English. "
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
        response = await client.chat.completions.create(
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


async def extract_image_texts(visit: Visit, client: AsyncOpenAI) -> List[Tuple[str, str]]:
    files = collect_files(
        visit.image_files,
        visit.image_filename,
        visit.image_file_b64,
        visit.image_mime,
        "prescription",
    )
    results = []
    for file in files:
        text, filename = await extract_image_text_from_file(file, client)
        if text:
            results.append((text, filename))
    return results


async def extract_doctor_info(source_text: str, client: AsyncOpenAI) -> dict:
    if not source_text.strip():
        return {
            "doctor_name": "",
            "doctor_phone": "",
            "clinic_name": "",
            "doctor_email": "",
            "patient_name": "",
            "patient_email": "",
        }

    system = (
        "You extract doctor contact details from clinical notes. "
        "Return ONLY valid JSON with keys: doctor_name, doctor_phone, clinic_name, doctor_email, "
        "patient_name, patient_email. "
        "Use the exact substrings from the source. "
        "If a value is not explicitly present, return an empty string for that key. "
        "Do not guess or fabricate."
    )
    user = f"Source text:\n{source_text}\n\nReturn JSON only."

    try:
        response = await client.chat.completions.create(
            model="gpt-5-nano",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],

        )
        content = response.choices[0].message.content or ""
    except Exception:
        return {
            "doctor_name": "",
            "doctor_phone": "",
            "clinic_name": "",
            "doctor_email": "",
            "patient_name": "",
            "patient_email": "",
        }

    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {
            "doctor_name": "",
            "doctor_phone": "",
            "clinic_name": "",
            "doctor_email": "",
            "patient_name": "",
            "patient_email": "",
        }

    try:
        data = json.loads(content[start : end + 1])
    except Exception:
        return {
            "doctor_name": "",
            "doctor_phone": "",
            "clinic_name": "",
            "doctor_email": "",
            "patient_name": "",
            "patient_email": "",
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
    patient_name = normalize(str(data.get("patient_name", "")))
    patient_email = normalize(str(data.get("patient_email", "")))

    def normalize_email(value: str) -> str:
        return value.strip().strip(".,;:")

    email_pattern = re.compile(r"^[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}$")
    patient_email = normalize_email(patient_email)

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
    if patient_name and not matches_text(patient_name, source_normalized):
        patient_name = ""
    if patient_email:
        if not email_pattern.match(patient_email):
            patient_email = ""
        elif patient_email.lower() not in source_lower:
            patient_email = ""

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

    if not patient_name:
        label_patterns = [
            r"(?:Patient Name|Patient)\s*[:\-]\s*([^\n\r]+)",
        ]
        for pattern in label_patterns:
            match = re.search(pattern, source_text, re.IGNORECASE)
            if not match:
                continue
            candidate = match.group(1).strip()
            candidate = re.split(r"\s{2,}", candidate)[0].strip()
            candidate = re.split(r"\s+(?:Patient\s+ID|ID|Age|Gender)\b", candidate, flags=re.IGNORECASE)[0].strip()
            if matches_text(candidate, source_normalized):
                patient_name = candidate
                break

    if not patient_email:
        match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", source_text)
        if match:
            candidate = normalize_email(match.group(0))
            if email_pattern.match(candidate):
                patient_email = candidate

    return {
        "doctor_name": doctor_name,
        "doctor_phone": doctor_phone,
        "clinic_name": clinic_name,
        "doctor_email": doctor_email,
        "patient_name": patient_name,
        "patient_email": patient_email,
    }


async def build_visit_context(visit: Visit, client: AsyncOpenAI) -> dict:
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

    for audio_text, audio_name in await extract_audio_transcripts(visit, client):
        display_name = audio_name or "audio recording"
        attachments.append((f"Audio transcript (English) ({display_name})", audio_text))

    for image_text, image_name in await extract_image_texts(visit, client):
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
