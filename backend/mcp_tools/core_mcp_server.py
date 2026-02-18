import os
import re
import uuid
import json
import logging
import tempfile
import urllib.request
import html
import base64
import mimetypes
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError
from mcp.server.fastmcp import FastMCP
from pypdf import PdfReader
from docx import Document
import resend
import markdown as md
from mcp_tools.bootstrap import bootstrap_mcp_process
from mcp_tools.status import update_job_status
from tool_instructions import tool_instructions_for

mcp = FastMCP("Core-Tools-Service")

bootstrap_mcp_process(log_level_env="CORE_LOG_LEVEL", service_label="mcp-core")


def _suppress_noisy_pdf_loggers() -> None:
    # FontTools can emit very chatty table/glyph logs during PDF generation.
    noisy = (
        "fontTools",
        "fontTools.subset",
        "fontTools.ttLib",
        "fontTools.ttLib.ttFont",
        "fontTools.ttLib.tables",
        "weasyprint",
    )
    for name in noisy:
        logging.getLogger(name).setLevel(logging.ERROR)


_suppress_noisy_pdf_loggers()

# PDF debug logging (off by default)
PDF_DEBUG_LOG = os.getenv("PDF_DEBUG_LOG", "true").lower() == "true"

def _truncate_log(text: str, limit: int = 400) -> str:
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    head = text[:limit]
    tail = text[-limit:]
    return f"{head}…[truncated {len(text)-2*limit} chars]…{tail}"

# ---- Resend email ----
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
RESEND_FROM = os.getenv("RESEND_FROM", "no-reply@agentairg.site").strip()
if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

_EMAIL_PLACEHOLDER_RE = re.compile(
    r"\{\{[^}]+\}\}|\[\.\.\.PLACEHOLDER\.\.\.\]|URL_PARAMS_PLACEHOLDER|FILENAME_PLACEHOLDER",
    re.IGNORECASE,
)
_EMAIL_ANCHOR_RE = re.compile(
    r"<a[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
_EMAIL_BR_RE = re.compile(r"(?i)<br\s*/?>")
_EMAIL_TAG_RE = re.compile(r"<[^>]+>")


def _tool(name: str):
    def decorator(func):
        doc = tool_instructions_for(name)
        if doc:
            func.__doc__ = doc
        return mcp.tool()(func)
    return decorator


# ---- PDF tools ----
_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")
_MAX_PDF_MB = int(os.getenv("PDF_MAX_MB", "50"))
_MAX_PDF_BYTES = _MAX_PDF_MB * 1024 * 1024
_MAX_PDF_CHARS = int(os.getenv("PDF_MAX_CHARS", "200000"))
_MAX_PDF_IMAGE_MB = int(os.getenv("PDF_IMAGE_MAX_MB", "5"))
_MAX_PDF_IMAGE_BYTES = _MAX_PDF_IMAGE_MB * 1024 * 1024
_MAX_PDF_IMAGE_COUNT = int(os.getenv("PDF_IMAGE_MAX_COUNT", "20"))


def _sanitize_filename(name: str) -> str:
    cleaned = _FILENAME_RE.sub("_", name).strip("._")
    if not cleaned:
        cleaned = f"download-{uuid.uuid4().hex}"
    if not cleaned.lower().endswith(".pdf"):
        cleaned = f"{cleaned}.pdf"
    return cleaned


def _sanitize_download_name(name: str) -> str:
    cleaned = _FILENAME_RE.sub("_", name).strip("._")
    if not cleaned:
        cleaned = f"download-{uuid.uuid4().hex}"
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


def _read_image_bytes(url_or_path: str) -> tuple[bytes, str]:
    if not url_or_path:
        raise ValueError("image url required")
    if url_or_path.startswith("file://"):
        parsed = urlparse(url_or_path)
        local_path = parsed.path
        if not local_path or not os.path.exists(local_path):
            raise FileNotFoundError(f"missing local image: {local_path}")
        with open(local_path, "rb") as handle:
            data = handle.read()
        mime = mimetypes.guess_type(local_path)[0] or "application/octet-stream"
        return data, mime
    if url_or_path.startswith("/downloads/"):
        filename = os.path.basename(url_or_path)
        local_path = os.path.join(_get_downloads_dir(), filename)
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"missing local image: {filename}")
        with open(local_path, "rb") as handle:
            data = handle.read()
        mime = mimetypes.guess_type(local_path)[0] or "application/octet-stream"
        return data, mime

    s3_info = _parse_s3_url(url_or_path)
    if s3_info:
        bucket, key = s3_info
        s3_client = boto3.client("s3")
        head = s3_client.head_object(Bucket=bucket, Key=key)
        size_bytes = int(head.get("ContentLength") or 0)
        if size_bytes > _MAX_PDF_IMAGE_BYTES:
            raise ValueError("image exceeds size limit")
        obj = s3_client.get_object(Bucket=bucket, Key=key)
        data = obj["Body"].read()
        mime = (obj.get("ContentType") or "").strip() or "application/octet-stream"
        return data, mime

    request = urllib.request.Request(
        url_or_path,
        headers={"User-Agent": "DigitalAssistant/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                if int(content_length) > _MAX_PDF_IMAGE_BYTES:
                    raise ValueError("image exceeds size limit")
            except ValueError:
                raise ValueError("Invalid Content-Length header")
        data = response.read()
        if len(data) > _MAX_PDF_IMAGE_BYTES:
            raise ValueError("image exceeds size limit")
        mime = (response.headers.get("Content-Type") or "").split(";")[0].strip()
        if not mime:
            mime = mimetypes.guess_type(url_or_path)[0] or "application/octet-stream"
        return data, mime


def _image_data_uri(data: bytes, mime: str) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


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


PDF_ALLOWED_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")
PDF_MAX_BLOCKS = 300
_JSON_CODE_BLOCK_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.IGNORECASE | re.DOTALL)


class PdfValidationError(Exception):
    def __init__(self, errors: List[Dict[str, Any]], code: str = "PDF_INPUT_INVALID", message: str = "PDF input failed validation"):
        super().__init__(message)
        self.errors = errors
        self.code = code
        self.message = message


def _pdf_err(path: str, reason: str, expected: Any = None, received: Any = None, suggested_fix: Optional[str] = None) -> Dict[str, Any]:
    err = {"path": path, "reason": reason}
    if expected is not None:
        err["expected"] = expected
    if received is not None:
        err["received"] = received
    if suggested_fix:
        err["suggested_fix"] = suggested_fix
    return err


def _pdf_issue(
    path: str,
    code: str,
    severity: str = "warning",
    fixable: bool = True,
    expected: Any = None,
    received: Any = None,
    suggested_fix: Optional[str] = None,
) -> Dict[str, Any]:
    issue: Dict[str, Any] = {
        "path": path,
        "code": code,
        "severity": severity,
        "fixable": fixable,
    }
    if expected is not None:
        issue["expected"] = expected
    if received is not None:
        issue["received"] = received
    if suggested_fix:
        issue["suggested_fix"] = suggested_fix
    return issue


def _pdf_error_response(errors: List[Dict[str, Any]], code: str = "PDF_INPUT_INVALID", message: str = "PDF input failed validation", fixable: bool = True) -> Dict[str, Any]:
    return {"status": "error", "code": code, "message": message, "fixable": fixable, "errors": errors}


def _errs_to_issues(errors: List[Dict[str, Any]], severity: str = "error") -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    for err in errors:
        issues.append(
            _pdf_issue(
                err.get("path", ""),
                err.get("reason", "INVALID"),
                severity=severity,
                fixable=True,
                expected=err.get("expected"),
                received=err.get("received"),
                suggested_fix=err.get("suggested_fix"),
            )
        )
    return issues


def _looks_like_json(text: str) -> bool:
    t = (text or "").strip()
    m = _JSON_CODE_BLOCK_RE.match(t)
    if m:
        t = (m.group(1) or "").strip()
    t = t.lstrip()
    return t.startswith("{") or t.startswith("[")


def _extract_json_candidate(text: str) -> str:
    candidate = (text or "").strip()
    m = _JSON_CODE_BLOCK_RE.match(candidate)
    if m:
        candidate = (m.group(1) or "").strip()
    return candidate


def _strip_html_tags(text: str) -> str:
    if "<" in text and ">" in text:
        text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\\1>", "", text)
        text = re.sub(r"(?is)<[^>]+>", " ", text)
    return html.unescape(text)


_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
_CODE_START_RE = re.compile(
    r"^\s*(from\s+\w+\s+import\s+|import\s+\w+|def\s+\w+\s*\(|class\s+\w+|if\s+__name__\s*==\s*['\"]__main__['\"]\s*:|"
    r"for\s+\w+|while\s+|return\b|with\s+|try:|except\b|[A-Za-z_]\w*\s*=|#\s)",
    re.IGNORECASE,
)
_CODE_LINE_RE = re.compile(
    r"^\s*(from\s+\w+\s+import\s+|import\s+\w+|def\s+\w+\s*\(|class\s+\w+|if\s+|elif\s+|else:|for\s+|while\s+|"
    r"return\b|with\s+|try:|except\b|finally:|[A-Za-z_]\w*\s*=|#\s|@\w+)",
    re.IGNORECASE,
)
_MD_PLAIN_URL_RE = re.compile(r"(?<!\]\()https?://[^\s<>()]+", re.IGNORECASE)


def _is_table_row_candidate(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped or "|" not in stripped:
        return False
    if stripped.count("|") < 2:
        return False
    if stripped.startswith("http://") or stripped.startswith("https://"):
        return False
    return True


def _split_table_cells(line: str) -> List[str]:
    stripped = (line or "").strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [c.strip() for c in stripped.split("|")]


def _split_inline_bullet_table_line(line: str) -> tuple[str, str] | None:
    raw = str(line or "")
    stripped = raw.lstrip()
    prefix_len = len(raw) - len(stripped)
    if not stripped:
        return None
    marker_len = 0
    if stripped[:2] in {"- ", "* ", "+ "}:
        marker_len = 2
    else:
        m = re.match(r"\d+\.\s+", stripped)
        if m:
            marker_len = len(m.group(0))
    if marker_len == 0:
        return None
    body = stripped[marker_len:]
    pipe_idx = body.find("|")
    if pipe_idx <= 0:
        return None
    tail = body[pipe_idx:].strip()
    if tail.count("|") < 2:
        return None
    heading = body[:pipe_idx].strip()
    if heading.endswith(":"):
        heading = heading[:-1].strip()
    if not heading:
        return None
    indent = " " * prefix_len
    return indent + heading + ":", tail


def _is_code_line(line: str) -> bool:
    stripped = (line or "").rstrip()
    if not stripped:
        return False
    if stripped.startswith("```"):
        return False
    if _CODE_LINE_RE.match(stripped):
        return True
    if stripped.endswith(":"):
        return True
    if "(" in stripped and ")" in stripped and "=" in stripped:
        return True
    return False


def _normalize_markdown_for_pdf(content: str) -> str:
    text = str(content or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    out: List[str] = []
    in_fence = False
    i = 0

    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            i += 1
            continue
        if in_fence:
            out.append(line)
            i += 1
            continue

        inline_table = _split_inline_bullet_table_line(line)
        if inline_table:
            heading, row_part = inline_table
            out.append(heading)
            line = row_part

        if _is_table_row_candidate(line):
            block: List[str] = [line.strip()]
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if _is_table_row_candidate(nxt) or _TABLE_SEP_RE.match(nxt.strip()):
                    block.append(nxt.strip())
                    j += 1
                    continue
                break

            if len(block) >= 2:
                parsed_rows = [_split_table_cells(row) for row in block if not _TABLE_SEP_RE.match(row)]
                if parsed_rows:
                    col_count = max(len(r) for r in parsed_rows)
                    parsed_rows = [r + [""] * (col_count - len(r)) for r in parsed_rows]
                    header = parsed_rows[0]
                    sep = ["---"] * col_count
                    body_rows = parsed_rows[1:]
                    if out and out[-1].strip():
                        out.append("")
                    out.append("| " + " | ".join(header) + " |")
                    out.append("| " + " | ".join(sep) + " |")
                    for row_cells in body_rows:
                        out.append("| " + " | ".join(row_cells) + " |")
                    out.append("")
                    i = j
                    continue

        if _CODE_START_RE.match(line):
            block = [line]
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if not nxt.strip():
                    break
                if _is_code_line(nxt):
                    block.append(nxt)
                    j += 1
                    continue
                break

            code_like_count = sum(1 for b in block if _is_code_line(b))
            if len(block) >= 3 and code_like_count >= max(2, len(block) - 1):
                if out and out[-1].strip():
                    out.append("")
                out.append("```python")
                out.extend(block)
                out.append("```")
                out.append("")
                i = j
                continue

        out.append(line)
        i += 1

    return "\n".join(out)


def _linkify_plain_urls_in_markdown(content: str) -> str:
    text = str(content or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    out: List[str] = []
    in_fence = False

    for line in lines:
        if line.strip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue

        def _repl(match: re.Match[str]) -> str:
            raw = match.group(0)
            trimmed = raw.rstrip(".,;:")
            suffix = raw[len(trimmed):]
            if not trimmed:
                return raw
            return f"[{trimmed}]({trimmed}){suffix}"

        out.append(_MD_PLAIN_URL_RE.sub(_repl, line))

    return "\n".join(out)


def _markdown_to_html(content: str) -> str:
    normalized = _normalize_markdown_for_pdf(content or "")
    normalized = _linkify_plain_urls_in_markdown(normalized)
    return md.markdown(
        normalized,
        extensions=["extra", "tables", "fenced_code", "sane_lists"],
    )


def _sanitize_text(text: str) -> str:
    cleaned = re.sub(r"[\\x00-\\x08\\x0B\\x0C\\x0E-\\x1F]", " ", str(text or ""))
    return cleaned.strip()


def _extract_plain_text_from_json(parsed: Any) -> str:
    lines: List[str] = []

    def _walk(node: Any) -> None:
        if node is None:
            return
        if isinstance(node, str):
            if node.strip():
                lines.append(node)
            return
        if isinstance(node, list):
            for item in node:
                _walk(item)
            return
        if isinstance(node, dict):
            for key in ("title", "heading", "markdown", "text", "caption", "alt"):
                if key in node and node[key]:
                    _walk(node[key])
            if "items" in node:
                _walk(node["items"])
            if "rows" in node:
                _walk(node["rows"])
            if "blocks" in node:
                _walk(node["blocks"])
            if "content" in node:
                _walk(node["content"])

    _walk(parsed)
    # Preserve order; remove empty/duplicate adjacent lines.
    cleaned: List[str] = []
    last = None
    for line in lines:
        if line and line != last:
            cleaned.append(line)
        last = line
    return "\n".join(cleaned).strip()


def _resolve_pdf_image_src(src: str) -> str:
    raw = str(src or "").strip()
    if not raw:
        return ""
    if raw.startswith("/downloads/"):
        local = os.path.join(_get_downloads_dir(), os.path.basename(raw))
        if os.path.exists(local):
            return Path(local).resolve().as_uri()
        return raw
    if raw.startswith("downloads/"):
        local = os.path.join(_get_downloads_dir(), os.path.basename(raw))
        if os.path.exists(local):
            return Path(local).resolve().as_uri()
        return raw
    return raw


def _render_blocks_html_minimal(blocks: Any) -> str:
    if not isinstance(blocks, list):
        return ""
    parts: List[str] = []
    for blk in blocks:
        if isinstance(blk, str):
            parts.append(_markdown_to_html(blk))
            continue
        if not isinstance(blk, dict):
            continue
        btype = (blk.get("type") or "").strip().lower()
        if not btype:
            if "markdown" in blk:
                btype = "markdown"
            elif "text" in blk:
                btype = "text"
            elif "rows" in blk and "columns" in blk:
                btype = "table"
            elif "src" in blk:
                btype = "image"
            elif "blocks" in blk and ("title" in blk or "heading" in blk):
                btype = "section"
        if btype == "section":
            title = blk.get("title") or blk.get("heading") or "Section"
            parts.append(f"<h2>{html.escape(str(title))}</h2>")
            parts.append(_render_blocks_html_minimal(blk.get("blocks") or []))
            continue
        if btype == "markdown":
            parts.append(_markdown_to_html(blk.get("markdown") or ""))
            continue
        if btype == "text":
            parts.append(f"<p>{html.escape(str(blk.get('text') or ''))}</p>")
            continue
        if btype == "image":
            src = _resolve_pdf_image_src(blk.get("src") or "")
            if not src:
                continue
            alt = html.escape(str(blk.get("alt") or "Image"))
            caption = blk.get("caption") or ""
            parts.append(
                f"<figure><img src=\"{src}\" alt=\"{alt}\" style=\"max-width: 100%; height: auto; display: block; margin: 8px auto;\" />"
                f"{f'<figcaption>{html.escape(str(caption))}</figcaption>' if caption else ''}</figure>"
            )
            continue
        if btype == "table":
            columns = blk.get("columns") or []
            rows = blk.get("rows") or []
            parts.append("<table>")
            if columns:
                parts.append("<thead><tr>")
                for col in columns:
                    parts.append(f"<th>{html.escape(str(col))}</th>")
                parts.append("</tr></thead>")
            parts.append("<tbody>")
            for row in rows:
                parts.append("<tr>")
                if isinstance(row, dict) and columns:
                    for col in columns:
                        parts.append(f"<td>{html.escape(str(row.get(col, '')))}</td>")
                else:
                    cells = row if isinstance(row, list) else [row]
                    for cell in cells:
                        parts.append(f"<td>{html.escape(str(cell))}</td>")
                parts.append("</tr>")
            parts.append("</tbody></table>")
            continue
    return "\n".join(parts)

def _build_pdf_html(doc: Dict[str, Any]) -> str:
    title = str(doc.get("title") or "Document")
    body = doc.get("raw") or ""
    raw_html = doc.get("raw_html")
    body_html = raw_html if raw_html is not None else f'<pre class="plain-text">{html.escape(body)}</pre>'
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8"/>
    <title>{html.escape(title)}</title>
    <style>
      body {{ font-family: Helvetica, Arial, sans-serif; font-size: 11pt; line-height: 1.45; color: #0f172a; margin: 0; padding: 24px 28px; max-width: 760px; }}
      h1 {{ font-size: 21pt; margin: 0 0 0.45em 0; line-height: 1.2; }}
      h2 {{ font-size: 16pt; margin: 0.9em 0 0.35em 0; line-height: 1.25; }}
      h3 {{ font-size: 13pt; margin: 0.75em 0 0.3em 0; line-height: 1.3; }}
      p {{ margin: 0 0 0.5em 0; }}
      pre.plain-text {{ white-space: pre-wrap; margin: 0 0 0.6em 0; font-family: inherit; }}
      pre, code {{ font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace; }}
      pre {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; tab-size: 2; }}
      pre code {{ white-space: inherit; display: block; background: transparent; padding: 0; border-radius: 0; }}
      code {{ background: #f1f5f9; padding: 0.1em 0.25em; border-radius: 4px; overflow-wrap: anywhere; }}
      ul, ol {{ margin: 0.28em 0 0.5em 0; padding-left: 1.05em; }}
      ul ul, ul ol, ol ul, ol ol {{ margin: 0.15em 0 0.24em 0; padding-left: 0.9em; }}
      li {{ margin: 0.12em 0; }}
      table {{ width: 100%; border-collapse: collapse; margin: 0.6em 0; table-layout: fixed; }}
      th, td {{ border: 1px solid #e2e8f0; padding: 6px; vertical-align: top; overflow-wrap: anywhere; word-break: break-word; }}
      th {{ background: #f1f5f9; text-align: left; }}
      figure {{ margin: 0.6em 0; }}
      figcaption {{ font-size: 10pt; color: #475569; text-align: center; margin-top: 0.3em; }}
    </style>
  </head>
  <body>
    {body_html}
  </body>
</html>
"""


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
    _suppress_noisy_pdf_loggers()
    _prepare_fontconfig_cache()
    try:
        from weasyprint import HTML
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("weasyprint is required for HTML-to-PDF rendering") from exc

    local_base = Path(_get_downloads_dir()).resolve().as_uri() + "/"
    HTML(string=content, base_url=local_base).write_pdf(output_path)


@_tool("download_pdf")
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


@_tool("generate_pdf_from_text")
async def generate_pdf_from_text(
    content: str, title: Optional[str] = None, filename: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate a PDF from markdown or HTML content.
    """
    update_job_status("Tool: Generate PDF", 55)
    logging.info("[core/pdf] generate start chars=%d", len(content or ""))
    if PDF_DEBUG_LOG:
        logging.info(
            "[core/pdf] generate input title=%s filename=%s chars=%d preview=%r",
            title,
            filename,
            len(content or ""),
            _truncate_log(content or ""),
        )
    if not content or not content.strip():
        return {"status": "error", "error": "content required"}
    if len(content) > _MAX_PDF_CHARS:
        return {"status": "error", "error": "content too large"}
    safe_name = _sanitize_filename(filename or (title or "download"))
    fd, tmp_path = tempfile.mkstemp(prefix="pdf-", suffix=".pdf")
    os.close(fd)
    try:
        raw_text = str(content or "")
        raw_html = None
        if _looks_like_json(raw_text):
            try:
                parsed = json.loads(_extract_json_candidate(raw_text))
            except Exception as exc:
                return _pdf_error_response(
                    [
                        _pdf_err(
                            "content",
                            "INVALID_JSON",
                            expected="valid JSON object or array",
                            received=str(exc),
                            suggested_fix="Send valid JSON content (or fenced ```json) with a blocks array.",
                        )
                    ],
                    code="PDF_INPUT_INVALID",
                    message="Invalid JSON input for PDF generation",
                    fixable=True,
                )

            blocks = None
            if isinstance(parsed, dict):
                if isinstance(parsed.get("blocks"), list):
                    blocks = parsed.get("blocks") or []
                if not title:
                    parsed_title = parsed.get("title")
                    if isinstance(parsed_title, str) and parsed_title.strip():
                        title = parsed_title
            elif isinstance(parsed, list):
                blocks = parsed
            else:
                return _pdf_error_response(
                    [
                        _pdf_err(
                            "content",
                            "INVALID_TYPE",
                            expected="JSON object with blocks array or JSON array of blocks",
                            received=type(parsed).__name__,
                            suggested_fix="Provide `{ \"title\": \"...\", \"blocks\": [...] }` or an array of blocks.",
                        )
                    ],
                    code="PDF_INPUT_INVALID",
                    message="Invalid JSON payload type for PDF generation",
                    fixable=True,
                )

            if not isinstance(blocks, list) or not blocks:
                return _pdf_error_response(
                    [
                        _pdf_err(
                            "content.blocks",
                            "MISSING",
                            expected="non-empty blocks array",
                            received=list(parsed.keys()) if isinstance(parsed, dict) else type(parsed).__name__,
                            suggested_fix="Provide a non-empty blocks array.",
                        )
                    ],
                    code="PDF_INPUT_INVALID",
                    message="Missing blocks array in JSON input",
                    fixable=True,
                )
            if len(blocks) > PDF_MAX_BLOCKS:
                return _pdf_error_response(
                    [
                        _pdf_err(
                            "content.blocks",
                            "TOO_MANY_ITEMS",
                            expected=f"<= {PDF_MAX_BLOCKS}",
                            received=len(blocks),
                            suggested_fix="Split the report into smaller sections or fewer blocks.",
                        )
                    ],
                    code="PDF_INPUT_INVALID",
                    message="Too many blocks in JSON input",
                    fixable=True,
                )

            raw_html = _render_blocks_html_minimal(blocks)
            if not (raw_html or "").strip():
                return _pdf_error_response(
                    [
                        _pdf_err(
                            "content.blocks",
                            "UNRENDERABLE",
                            expected="renderable markdown/text/image/table/section blocks",
                            received="no renderable blocks",
                            suggested_fix="Use supported block types with valid fields.",
                        )
                    ],
                    code="PDF_INPUT_INVALID",
                    message="Blocks could not be rendered",
                    fixable=True,
                )
        else:
            raw_html = _markdown_to_html(raw_text)
        if PDF_DEBUG_LOG:
            logging.info("[core/pdf] simple render title=%r chars=%d preview=%r", title, len(raw_text), _truncate_log(raw_text))
        doc = {"title": title or "Document", "raw": raw_text, "raw_html": raw_html}
        html_doc = _build_pdf_html(doc)
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
        raise ValueError("PDF_CORRUPT") from exc
    if not getattr(reader, "pages", None):
        raise ValueError("PDF_CORRUPT")
    parts = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text:
            parts.append(text)
        if sum(len(p) for p in parts) > MAX_TEXT_CHARS:
            break
    if not parts:
        raise ValueError("PDF_NO_TEXT")
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


@_tool("read_uploaded_file")
async def read_uploaded_file(file_id: str) -> Dict[str, Any]:
    """
    Retrieve and extract text from a previously uploaded file.
    """
    update_job_status("Tool: Read Uploaded File", 45)
    logging.info("[core/upload] read start file_id=%s", file_id)
    if not file_id or not file_id.strip():
        return _pdf_error_response(
            [_pdf_err("file_id", "MISSING", expected="non-empty file_id")],
            code="FILE_ID_REQUIRED",
            message="file_id required",
            fixable=True,
        )

    file_id = file_id.strip()
    tmp_path = None
    filename = None
    try:
        if USE_S3:
            result = _download_from_s3(file_id)
            if not result:
                return _pdf_error_response(
                    [_pdf_err("file_id", "NOT_FOUND", expected="existing upload id", received=file_id, suggested_fix="Re-upload the file and use the new file_id")],
                    code="FILE_NOT_FOUND",
                    message="file not found",
                    fixable=True,
                )
            tmp_path, filename = result
        else:
            local_path = _find_local_file(file_id)
            if not local_path:
                return _pdf_error_response(
                    [_pdf_err("file_id", "NOT_FOUND", expected="existing upload id", received=file_id, suggested_fix="Re-upload the file and use the new file_id")],
                    code="FILE_NOT_FOUND",
                    message="file not found",
                    fixable=True,
                )
            tmp_path = local_path
            filename = os.path.basename(local_path)

        try:
            text = _extract_text(tmp_path)
        except ValueError as exc:
            err = str(exc)
            if err == "PDF_CORRUPT":
                return _pdf_error_response(
                    [_pdf_err("file_id", "PDF_CORRUPT", received=filename, suggested_fix="Re-upload a valid PDF or export as text-selectable PDF")],
                    code="FILE_UNREADABLE",
                    message="PDF is invalid or corrupted",
                    fixable=True,
                )
            if err == "PDF_NO_TEXT":
                return _pdf_error_response(
                    [_pdf_err("file_id", "PDF_NO_TEXT", received=filename, suggested_fix="Re-upload a text-selectable PDF or provide a .txt/.docx version")],
                    code="FILE_NO_TEXT",
                    message="PDF has no extractable text",
                    fixable=True,
                )
            return _pdf_error_response(
                [_pdf_err("file_id", "UNREADABLE", received=filename)],
                code="FILE_UNREADABLE",
                message="file could not be read",
                fixable=True,
            )
        if not text.strip():
            return _pdf_error_response(
                [_pdf_err("file_id", "NO_TEXT", received=filename, suggested_fix="Re-upload a text-selectable file")],
                code="FILE_NO_TEXT",
                message="no text extracted",
                fixable=True,
            )
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


def _normalize_email_url(url: str) -> Optional[str]:
    raw = (url or "").strip().rstrip(").,;")
    if not raw or _EMAIL_PLACEHOLDER_RE.search(raw):
        return None
    if raw.startswith("/downloads/"):
        base = _get_public_base_url()
        if base:
            return f"{base.rstrip('/')}{raw}"
        return raw
    if raw.startswith(("http://", "https://")):
        return raw
    return None


def _html_to_text_with_links(raw: str) -> str:
    text = html.unescape(str(raw or ""))
    text = _EMAIL_BR_RE.sub("\n", text)

    def _anchor_to_markdown(match: re.Match[str]) -> str:
        href = (match.group(1) or "").strip()
        label = _EMAIL_TAG_RE.sub("", match.group(2) or "").strip() or "Open Link"
        return f"[{label}]({href})"

    text = _EMAIL_ANCHOR_RE.sub(_anchor_to_markdown, text)
    text = _EMAIL_TAG_RE.sub("", text)
    return text


def _render_email_html(body: str) -> Tuple[Optional[str], Optional[str]]:
    text = _html_to_text_with_links(body)
    if _EMAIL_PLACEHOLDER_RE.search(text):
        return None, "placeholder link token detected in email body"

    pattern = re.compile(
        r"\[([^\]]{1,200})\]\(([^)\s]+)\)|"
        r"(https?://[^\s<>()]+|/downloads/[^\s<>()]+)",
        re.IGNORECASE,
    )
    out: List[str] = []
    last = 0
    for match in pattern.finditer(text):
        start, end = match.span()
        if start > last:
            out.append(html.escape(text[last:start]).replace("\n", "<br/>"))

        label = (match.group(1) or "").strip()
        raw_url = (match.group(2) or match.group(3) or "").strip()
        norm_url = _normalize_email_url(raw_url)
        if not norm_url:
            return None, f"invalid or non-canonical URL in email body: {raw_url}"

        if not label:
            lower = norm_url.lower()
            label = "Download PDF" if ".pdf" in lower or "/downloads/" in lower else "Open Link"

        href = html.escape(norm_url, quote=True)
        safe_label = html.escape(label)
        out.append(f'<a href="{href}" target="_blank" rel="noopener noreferrer">{safe_label}</a>')
        last = end

    if last < len(text):
        out.append(html.escape(text[last:]).replace("\n", "<br/>"))

    rendered = "".join(out).strip()
    if not rendered:
        rendered = html.escape(text).replace("\n", "<br/>")
    wrapped = (
        '<div style="font-family: Arial, sans-serif; font-size: 14px; '
        'line-height: 1.5; color: #111;">'
        + rendered
        + "</div>"
    )
    return wrapped, None


# ---- Resend email ----
@_tool("send_resend_email")
async def send_resend_email(to: str, subject: str, body: str) -> str:
    """
    Sends an email using Resend.
    """
    update_job_status("Tool: Send Email", 70)
    logging.info(
        "[core/resend] invoked to=%s subject=%s body_chars=%d",
        to,
        subject,
        len(body or ""),
    )
    if not RESEND_API_KEY:
        logging.error("[core/resend] RESEND_API_KEY not configured")
        return "Email failed: RESEND_API_KEY not configured"
    try:
        rendered_body, render_error = _render_email_html(body or "")
        if render_error:
            logging.error("[core/resend] body validation failed: %s", render_error)
            return f"Email failed: {render_error}"

        logging.info("[core/resend] sending email to=%s subject=%s", to, subject)
        params = {
            "from": f"Digital Assistant <{RESEND_FROM}>",
            "to": [to],
            "subject": subject,
            "html": rendered_body,
        }
        email = resend.Emails.send(params)
    except Exception as exc:
        # Resend errors can be transport, auth, domain verification, etc.
        logging.exception("[core/resend] send failed to=%s subject=%s", to, subject)
        return f"Email failed: {type(exc).__name__}: {exc}"

    if not isinstance(email, dict):
        logging.error("[core/resend] unexpected response type: %s value=%r", type(email), email)
        return "Email failed: unexpected response from Resend"

    email_id = email.get("id")
    if not email_id:
        logging.error("[core/resend] missing id in response: %r", email)
        return f"Email failed: unexpected response from Resend: {email}"

    logging.info("[core/resend] sent email id=%s", email_id)
    return f"Email sent successfully. ID: {email_id}"


if __name__ == "__main__":
    try:
        mcp.run(transport="stdio")
    except TypeError:
        mcp.run()
