from pydantic import BaseModel
from typing import Optional, List

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
    uploaded_files: Optional[List[Base64File]] = None
    audio_file_b64: Optional[str] = None
    audio_filename: Optional[str] = None
    audio_mime: Optional[str] = None
    audio_files: Optional[List[Base64File]] = None
    image_file_b64: Optional[str] = None
    image_filename: Optional[str] = None
    image_mime: Optional[str] = None
    image_files: Optional[List[Base64File]] = None


class SendEmailRequest(BaseModel):
    to: str
    subject: str
    html: str
    reply_to: str
    clinic_name: str
    language: Optional[str] = "English"
