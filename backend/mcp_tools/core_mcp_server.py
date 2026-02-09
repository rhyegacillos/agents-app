import os
import re
import uuid
import logging
import tempfile
import urllib.request
from typing import Optional, Dict, Any
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError
from mcp.server.fastmcp import FastMCP
from pypdf import PdfReader
from docx import Document
import resend
import markdown as md
from mcp_tools.status import update_job_status


mcp = FastMCP("Core-Tools-Service")

logging.basicConfig(stream=os.sys.stderr, level=os.getenv("CORE_LOG_LEVEL", "INFO").upper())

# ---- Resend email ----
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
RESEND_FROM = os.getenv("RESEND_FROM", "no-reply@agentairg.site").strip()
if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY


# ---- PDF tools ----
_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")
_MAX_PDF_MB = int(os.getenv("PDF_MAX_MB", "50"))
_MAX_PDF_BYTES = _MAX_PDF_MB * 1024 * 1024
_MAX_PDF_CHARS = int(os.getenv("PDF_MAX_CHARS", "200000"))


def _sanitize_filename(name: str) -> str:
    cleaned = _FILENAME_RE.sub("_", name).strip("._")
    if not cleaned:
        cleaned = f"download-{uuid.uuid4().hex}"
    if not cleaned.lower().endswith(".pdf"):
        cleaned = f"{cleaned}.pdf"
    return cleaned


def _guess_filename(url: str, filename: Optional[str]) -> str:
    if filename:
        return _sanitize_filename(filename)
    parsed = urlparse(url)
    tail = os.path.basename(parsed.path) or ""
    return _sanitize_filename(tail or f"download-{uuid.uuid4().hex}.pdf")


def _get_download_bucket() -> Optional[str]:
    if os.getenv("USE_S3", "false").lower() != "true":
        return None
    return os.getenv("DOWNLOADS_BUCKET") or os.getenv("S3_BUCKET")


def _get_public_base_url() -> Optional[str]:
    return (
        os.getenv("PUBLIC_BASE_URL")
        or os.getenv("API_PUBLIC_URL")
        or os.getenv("BASE_URL")
    )


def _get_downloads_dir() -> str:
    return os.getenv("DOWNLOADS_DIR", "/tmp/downloads")


def _get_signed_url_expires() -> int:
    value = os.getenv("PDF_URL_EXPIRES_SECONDS", "86400").strip()
    try:
        seconds = int(value)
    except ValueError:
        seconds = 86400
    return max(60, seconds)


def _parse_s3_url(url: str) -> Optional[tuple[str, str]]:
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    host = parsed.netloc or ""
    path = (parsed.path or "").lstrip("/")
    if not host or not path or "amazonaws.com" not in host:
        return None
    if host.startswith("s3.") or host.startswith("s3-") or host == "s3.amazonaws.com":
        parts = path.split("/", 1)
        if len(parts) < 2:
            return None
        return parts[0], parts[1]
    if ".s3." in host or ".s3-" in host or host.endswith(".s3.amazonaws.com"):
        bucket = host.split(".s3")[0]
        return bucket, path
    return None


def _stream_download(url: str, target_path: str) -> int:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "DigitalAssistant/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        content_type = (response.headers.get("Content-Type") or "").lower()
        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                if int(content_length) > _MAX_PDF_BYTES:
                    raise ValueError("PDF exceeds size limit")
            except ValueError:
                raise ValueError("Invalid Content-Length header")

        bytes_written = 0
        with open(target_path, "wb") as handle:
            first_chunk = response.read(5)
            if not first_chunk.startswith(b"%PDF") and "application/pdf" not in content_type:
                raise ValueError("URL does not appear to be a PDF")
            handle.write(first_chunk)
            bytes_written += len(first_chunk)
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > _MAX_PDF_BYTES:
                    raise ValueError("PDF exceeds size limit")
                handle.write(chunk)
        return bytes_written


def _store_pdf(tmp_path: str, safe_name: str, size_bytes: int) -> Dict:
    bucket = _get_download_bucket()
    if bucket:
        key = f"downloads/{uuid.uuid4().hex}/{safe_name}"
        s3_client = boto3.client("s3")
        try:
            s3_client.upload_file(
                tmp_path,
                bucket,
                key,
                ExtraArgs={"ContentType": "application/pdf"},
            )
            signed_url = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=_get_signed_url_expires(),
            )
            return {
                "status": "ok",
                "storage": "s3",
                "download_url": signed_url,
                "bucket": bucket,
                "key": key,
                "filename": safe_name,
                "size_bytes": size_bytes,
            }
        except ClientError as exc:
            return {"status": "error", "error": str(exc)}
    else:
        downloads_dir = _get_downloads_dir()
        os.makedirs(downloads_dir, exist_ok=True)
        final_path = os.path.join(downloads_dir, safe_name)
        os.replace(tmp_path, final_path)
        public_base = _get_public_base_url()
        download_url = (
            f"{public_base.rstrip('/')}/downloads/{safe_name}" if public_base else None
        )
        return {
            "status": "ok",
            "storage": "local",
            "file_path": final_path,
            "download_url": download_url,
            "filename": safe_name,
            "size_bytes": size_bytes,
        }


def _wrap_html(content: str, title: Optional[str]) -> str:
    if "<html" in content.lower():
        return content
    safe_title = title or "Document"
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8"/>
    <title>{safe_title}</title>
    <style>
      body {{ font-family: Helvetica, Arial, sans-serif; font-size: 11pt; line-height: 1.4; color: #0f172a; }}
      h1 {{ font-size: 20pt; margin: 0 0 0.5em 0; }}
      h2 {{ font-size: 16pt; margin: 1em 0 0.4em 0; }}
      h3 {{ font-size: 13pt; margin: 0.8em 0 0.3em 0; }}
      p {{ margin: 0 0 0.6em 0; }}
      ul, ol {{ margin: 0.4em 0 0.6em 1.2em; }}
      table {{ width: 100%; border-collapse: collapse; margin: 0.6em 0; }}
      th, td {{ border: 1px solid #e2e8f0; padding: 6px; vertical-align: top; }}
      th {{ background: #f1f5f9; text-align: left; }}
    </style>
  </head>
  <body>
    {content}
  </body>
</html>
"""


def _markdown_to_html(content: str) -> str:
    return md.markdown(
        content or "",
        extensions=["extra", "tables", "fenced_code", "sane_lists"],
    )


def _prepare_fontconfig_cache() -> None:
    cache_root = "/tmp/.cache"
    font_cache = os.path.join(cache_root, "fontconfig")
    os.makedirs(font_cache, exist_ok=True)
    # Force writable cache location for Lambda.
    os.environ["XDG_CACHE_HOME"] = cache_root
    os.environ.setdefault("HOME", "/tmp")
    os.environ.setdefault("FONTCONFIG_PATH", "/etc/fonts")
    os.environ.setdefault("FONTCONFIG_FILE", "/etc/fonts/fonts.conf")


def _write_pdf_from_html(content: str, output_path: str, title: Optional[str] = None) -> None:
    _prepare_fontconfig_cache()
    try:
        from weasyprint import HTML
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("weasyprint is required for HTML-to-PDF rendering") from exc

    html_doc = _wrap_html(content, title)
    HTML(string=html_doc, base_url="").write_pdf(output_path)


@mcp.tool()
async def download_pdf(url: str, filename: Optional[str] = None) -> Dict[str, Any]:
    """
    Download a PDF from a URL and store it (local or S3).
    """
    update_job_status("Tool: Download PDF", 45)
    logging.info("[core/pdf] download start url=%s", url)
    if not url:
        return {"status": "error", "error": "url required"}
    safe_name = _guess_filename(url, filename)
    fd, tmp_path = tempfile.mkstemp(prefix="download-", suffix=".pdf")
    os.close(fd)
    try:
        s3_info = _parse_s3_url(url)
        if s3_info:
            bucket, key = s3_info
            s3_client = boto3.client("s3")
            head = s3_client.head_object(Bucket=bucket, Key=key)
            size_bytes = int(head.get("ContentLength") or 0)
            if size_bytes > _MAX_PDF_BYTES:
                raise ValueError("PDF exceeds size limit")
            s3_client.download_file(bucket, key, tmp_path)
        else:
            size_bytes = _stream_download(url, tmp_path)
        result = _store_pdf(tmp_path, safe_name, size_bytes)
        logging.info("[core/pdf] download success filename=%s", safe_name)
        return result
    except Exception as exc:
        logging.error("[core/pdf] download error: %s", exc)
        return {"status": "error", "error": str(exc)}
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


@mcp.tool()
async def generate_pdf_from_text(
    content: str, title: Optional[str] = None, filename: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate a PDF from markdown or HTML content.
    """
    update_job_status("Tool: Generate PDF", 55)
    logging.info("[core/pdf] generate start chars=%d", len(content or ""))
    if not content or not content.strip():
        return {"status": "error", "error": "content required"}
    if len(content) > _MAX_PDF_CHARS:
        return {"status": "error", "error": "content too large"}
    safe_name = _sanitize_filename(filename or (title or "download"))
    fd, tmp_path = tempfile.mkstemp(prefix="pdf-", suffix=".pdf")
    os.close(fd)
    try:
        html_doc = _markdown_to_html(content)
        _write_pdf_from_html(html_doc, tmp_path, title=title)
        size_bytes = os.path.getsize(tmp_path)
        if size_bytes > _MAX_PDF_BYTES:
            return {"status": "error", "error": "PDF exceeds size limit"}
        result = _store_pdf(tmp_path, safe_name, size_bytes)
        logging.info("[core/pdf] generate success filename=%s", safe_name)
        return result
    except Exception as exc:
        logging.error("[core/pdf] generate error: %s", exc)
        return {"status": "error", "error": str(exc)}
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


# ---- File reader ----
UPLOADS_DIR = os.getenv("UPLOADS_DIR", "/tmp/uploads")
USE_S3 = os.getenv("USE_S3", "false").lower() == "true"
UPLOADS_BUCKET = os.getenv("UPLOADS_BUCKET") or os.getenv("S3_BUCKET")
DEFAULT_REGION = os.getenv("DEFAULT_AWS_REGION", "us-east-1")
MAX_TEXT_CHARS = int(os.getenv("UPLOAD_TEXT_MAX_CHARS", "200000"))


def _find_local_file(file_id: str) -> Optional[str]:
    if not os.path.isdir(UPLOADS_DIR):
        return None
    for name in os.listdir(UPLOADS_DIR):
        if name.startswith(f"{file_id}."):
            return os.path.join(UPLOADS_DIR, name)
    return None


def _download_from_s3(file_id: str) -> Optional[tuple[str, str]]:
    if not UPLOADS_BUCKET:
        return None
    s3 = boto3.client("s3", region_name=DEFAULT_REGION)
    prefix = f"uploads/{file_id}/"
    try:
        response = s3.list_objects_v2(Bucket=UPLOADS_BUCKET, Prefix=prefix, MaxKeys=1)
        items = response.get("Contents") or []
        if not items:
            return None
        key = items[0]["Key"]
        suffix = os.path.basename(key)
        fd, tmp_path = tempfile.mkstemp(prefix="upload-", suffix=f"-{suffix}")
        os.close(fd)
        s3.download_file(UPLOADS_BUCKET, key, tmp_path)
        return tmp_path, suffix
    except ClientError as exc:
        logging.error("[core/upload] s3 error: %s", exc)
        return None


def _read_text_from_pdf(path: str) -> str:
    try:
        reader = PdfReader(path)
    except Exception as exc:
        raise ValueError("Invalid or corrupted PDF file") from exc
    if not getattr(reader, "pages", None):
        raise ValueError("Invalid or corrupted PDF file")
    parts = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text:
            parts.append(text)
        if sum(len(p) for p in parts) > MAX_TEXT_CHARS:
            break
    if not parts:
        raise ValueError("PDF has no extractable text")
    return "\n\n".join(parts)[:MAX_TEXT_CHARS]


def _read_text_from_docx(path: str) -> str:
    doc = Document(path)
    parts = [p.text for p in doc.paragraphs if p.text]
    text = "\n".join(parts)
    return text[:MAX_TEXT_CHARS]


def _read_text_from_plain(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        return handle.read(MAX_TEXT_CHARS)


def _extract_text(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return _read_text_from_pdf(path)
    if ext == ".docx":
        return _read_text_from_docx(path)
    return _read_text_from_plain(path)


@mcp.tool()
async def read_uploaded_file(file_id: str) -> Dict[str, Any]:
    """
    Retrieve and extract text from a previously uploaded file.
    """
    update_job_status("Tool: Read Uploaded File", 45)
    logging.info("[core/upload] read start file_id=%s", file_id)
    if not file_id or not file_id.strip():
        return {"status": "error", "error": "file_id required"}

    file_id = file_id.strip()
    tmp_path = None
    filename = None
    try:
        if USE_S3:
            result = _download_from_s3(file_id)
            if not result:
                return {"status": "error", "error": "file not found"}
            tmp_path, filename = result
        else:
            local_path = _find_local_file(file_id)
            if not local_path:
                return {"status": "error", "error": "file not found"}
            tmp_path = local_path
            filename = os.path.basename(local_path)

        try:
            text = _extract_text(tmp_path)
        except ValueError as exc:
            return {"status": "error", "error": str(exc)}
        if not text.strip():
            return {"status": "error", "error": "no text extracted"}
        logging.info("[core/upload] read success filename=%s", filename)
        return {
            "status": "ok",
            "file_id": file_id,
            "filename": filename,
            "text": text,
        }
    finally:
        if USE_S3 and tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


# ---- Resend email ----
@mcp.tool()
async def send_resend_email(to: str, subject: str, body: str) -> str:
    """
    Sends an email using Resend.
    """
    update_job_status("Tool: Send Email", 70)
    if not RESEND_API_KEY:
        return "Email failed: RESEND_API_KEY not configured"
    raw_body = body or ""
    if "<" not in raw_body and "&lt;" in raw_body and "&gt;" in raw_body:
        raw_body = html.unescape(raw_body)

    body = raw_body
    body_lower = body.lower()
    is_html = any(tag in body_lower for tag in ("<html", "<body", "<p", "<div", "<br", "<a "))
    if not is_html:
        safe = html.escape(body)
        body = (
            "<div style=\"font-family: Arial, sans-serif; font-size: 14px; line-height: 1.5; color: #111;\">"
            + safe.replace("\n", "<br/>")
            + "</div>"
        )

    logging.info("[core/resend] sending email to=%s subject=%s", to, subject)
    params = {
        "from": f"Digital Assistant <{RESEND_FROM}>",
        "to": [to],
        "subject": subject,
        "html": body,
    }
    email = resend.Emails.send(params)
    logging.info("[core/resend] sent email id=%s", email.get("id"))
    return f"Email sent successfully. ID: {email['id']}"


if __name__ == "__main__":
    try:
        mcp.run(transport="stdio")
    except TypeError:
        mcp.run()
