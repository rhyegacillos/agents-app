import os
import re
import uuid
import tempfile
import urllib.request
from typing import Optional, Dict
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError
import markdown as md

try:
    from agents import function_tool
except Exception as exc:  # pragma: no cover - handled at runtime
    raise RuntimeError("openai-agents is required to use tools.") from exc


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


def _markdown_to_html(content: str) -> str:
    return md.markdown(
        content or "",
        extensions=["extra", "tables", "fenced_code", "sane_lists"],
    )


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


def _prepare_fontconfig_cache() -> None:
    cache_root = "/tmp/.cache"
    font_cache = os.path.join(cache_root, "fontconfig")
    os.makedirs(font_cache, exist_ok=True)
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


@function_tool
def download_pdf(url: str, filename: Optional[str] = None) -> Dict:
    """
    Download a PDF from a URL. Only use this tool when the user explicitly asks for a PDF download.
    Returns a local path (dev) or a signed URL (prod/S3) when successful.
    """
    if not url or not url.startswith(("http://", "https://")):
        return {"status": "error", "error": "URL must start with http:// or https://"}

    safe_name = _guess_filename(url, filename)
    tmp_dir = tempfile.mkdtemp(prefix="pdf-download-")
    tmp_path = os.path.join(tmp_dir, safe_name)

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
    except Exception as exc:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        finally:
            return {"status": "error", "error": str(exc)}

    return _store_pdf(tmp_path, safe_name, size_bytes)


@function_tool
def generate_pdf_from_text(content: str, filename: Optional[str] = None, title: Optional[str] = None) -> Dict:
    """
    Generate a PDF from markdown or HTML content. Only use this tool when the user explicitly asks
    to convert chat content or text into a PDF.
    """
    if not content or not content.strip():
        return {"status": "error", "error": "Content is empty"}

    if len(content) > _MAX_PDF_CHARS:
        return {"status": "error", "error": "Content is too long for PDF conversion"}

    safe_name = _sanitize_filename(filename or f"chat-{uuid.uuid4().hex}.pdf")
    tmp_dir = tempfile.mkdtemp(prefix="pdf-generate-")
    tmp_path = os.path.join(tmp_dir, safe_name)

    try:
        html_doc = _markdown_to_html(content)
        _write_pdf_from_html(html_doc, tmp_path, title=title)
        size_bytes = os.path.getsize(tmp_path)
        if size_bytes > _MAX_PDF_BYTES:
            return {"status": "error", "error": "Generated PDF exceeds size limit"}
    except Exception as exc:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        finally:
            return {"status": "error", "error": str(exc)}

    return _store_pdf(tmp_path, safe_name, size_bytes)
