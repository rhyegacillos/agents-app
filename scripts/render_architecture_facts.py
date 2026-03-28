#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE_PATH = REPO_ROOT / "ARCHITECTURE.md"
CONFIG_PATH = REPO_ROOT / "backend" / "config.py"
RISK_ROUTER_PATH = REPO_ROOT / "backend" / "services" / "risk_router.py"
BEDROCK_RUNNER_PATH = REPO_ROOT / "backend" / "services" / "chat_runtime" / "bedrock_runner.py"
SERVER_PATH = REPO_ROOT / "backend" / "server.py"
CORE_MCP_PATH = REPO_ROOT / "backend" / "mcp_tools" / "core_mcp_server.py"
QUOTA_PATH = REPO_ROOT / "backend" / "services" / "quota.py"
ROUTER_PATHS = [
    REPO_ROOT / "backend" / "api" / "routers" / "core.py",
    REPO_ROOT / "backend" / "api" / "routers" / "chat.py",
    REPO_ROOT / "backend" / "api" / "routers" / "memory.py",
    REPO_ROOT / "backend" / "api" / "routers" / "files.py",
]

MARKER_START = "<!-- BEGIN GENERATED FACTS: AUTO -->"
MARKER_END = "<!-- END GENERATED FACTS: AUTO -->"


@dataclass(frozen=True)
class RouteFact:
    method: str
    path: str
    router_file: str
    function_name: str


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse(path: Path) -> ast.AST:
    return ast.parse(_read(path), filename=str(path))


def _literal_string(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        value = ast.literal_eval(node)
    except Exception:
        return None
    return value if isinstance(value, str) else None


def _find_os_getenv_call(node: ast.AST) -> ast.Call | None:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Attribute) and func.attr == "getenv":
            owner = func.value
            if isinstance(owner, ast.Name) and owner.id == "os":
                return child
    return None


def _extract_config_defaults() -> dict[str, str]:
    module = _parse(CONFIG_PATH)
    return _extract_getenv_defaults_from_module(module)


def _extract_getenv_defaults_from_module(module: ast.AST) -> dict[str, str]:
    defaults: dict[str, str] = {}

    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        getenv_call = _find_os_getenv_call(node.value)
        if getenv_call is None:
            continue
        if len(getenv_call.args) < 2:
            continue
        env_name = _literal_string(getenv_call.args[0])
        env_default = _literal_string(getenv_call.args[1])
        if env_name is None or env_default is None:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                defaults[target.id] = env_default
    return defaults


def _extract_module_getenv_defaults(path: Path) -> dict[str, str]:
    return _extract_getenv_defaults_from_module(_parse(path))


def _extract_routes() -> list[RouteFact]:
    facts: list[RouteFact] = []
    for path in ROUTER_PATHS:
        module = _parse(path)
        rel = str(path.relative_to(REPO_ROOT))
        for node in module.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                func = decorator.func
                if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
                    continue
                if func.value.id != "router":
                    continue
                if func.attr not in {"get", "post", "put", "patch", "delete"}:
                    continue
                route_path = _literal_string(decorator.args[0]) if decorator.args else None
                if not route_path:
                    continue
                facts.append(
                    RouteFact(
                        method=func.attr.upper(),
                        path=route_path,
                        router_file=rel,
                        function_name=node.name,
                    )
                )
    return facts


def _extract_name_constant(module: ast.AST, name: str) -> str | list[str] | None:
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                if (
                    isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Attribute)
                    and isinstance(node.value.func.value, ast.Name)
                    and node.value.func.value.id == "re"
                    and node.value.func.attr == "compile"
                    and node.value.args
                ):
                    return _literal_string(node.value.args[0])
                try:
                    return ast.literal_eval(node.value)
                except Exception:
                    return None
    return None


def _extract_regex_patterns() -> dict[str, str | list[str]]:
    module = _parse(RISK_ROUTER_PATH)
    names = [
        "_HIGH_RISK_PATTERNS",
        "_EMAIL_ADDRESS_RE",
        "_EMAIL_ACTION_RE",
        "_PDF_ACTION_RE",
        "_FOLLOWUP_ACTION_RE",
        "_PRIOR_ACTION_CONTEXT_RE",
    ]
    out: dict[str, str | list[str]] = {}
    for name in names:
        value = _extract_name_constant(module, name)
        if value is not None:
            out[name] = value
    return out


def _extract_model_candidate_rules() -> str:
    text = _read(BEDROCK_RUNNER_PATH)
    compact = " ".join(line.strip() for line in text.splitlines())
    if "if region.startswith(\"us-\")" not in compact:
        return "Fallback prefix rules could not be summarized automatically from `backend/services/chat_runtime/bedrock_runner.py`."
    return (
        "If the configured Bedrock model identifier does not already carry a dotted prefix in its leading segment, "
        "the runner tries the base identifier first and then derives region-prefixed candidates. "
        "For a `us-*` default region the current prefix order is `us`, `eu`, then `apac`; "
        "for an `eu-*` region it is `eu`, `us`, then `apac`; otherwise it is `apac`, `us`, then `eu`. "
        "If the configured model identifier already contains a dotted prefix or is an ARN-like path, "
        "the runner keeps it as-is and does not derive additional prefixed candidates."
    )


def _extract_env_default_from_text(path: Path, env_name: str) -> str:
    text = _read(path)
    pattern = re.compile(rf'{re.escape(env_name)}", "([^"]+)"')
    match = pattern.search(text)
    return match.group(1) if match else ""


def _upload_download_behavior_summary() -> list[str]:
    server_text = _read(SERVER_PATH)
    core_text = _read(CORE_MCP_PATH)

    bullets: list[str] = []

    if 'key = f"uploads/{file_id}/{safe_name}"' in server_text:
        bullets.append(
            "Direct uploads and presigned uploads both use the object-key shape "
            f"{_code('uploads/{file_id}/{safe_name}')} when S3-backed storage is active."
        )
    if "if USE_S3:" in server_text and 'final_path = os.path.join(UPLOADS_DIR, f"{file_id}.{ext}")' in server_text:
        bullets.append(
            "The direct `POST /uploads` route stores files in S3 when `USE_S3=true`; otherwise it writes local files "
            f"under {_code('UPLOADS_DIR')} as {_code('{file_id}.{ext}')}. "
        )
    if 'raise HTTPException(status_code=400, detail="S3 uploads are not enabled")' in server_text:
        bullets.append(
            "The `POST /uploads/presign` route is only valid in S3 mode and fails fast when `USE_S3` is disabled."
        )
    if 'downloads_dir = os.getenv("DOWNLOADS_DIR", "/tmp/downloads")' in server_text:
        bullets.append(
            "The `GET /downloads/{filename}` route only serves local artifacts from `DOWNLOADS_DIR`; it does not proxy S3 PDFs."
        )
    if 'return os.getenv("DOWNLOADS_BUCKET") or os.getenv("S3_BUCKET")' in core_text:
        bullets.append(
            "Generated PDFs use `DOWNLOADS_BUCKET` when set, otherwise they fall back to `S3_BUCKET` in S3 mode."
        )
    if 'PUBLIC_BASE_URL' in core_text and 'API_PUBLIC_URL' in core_text and 'BASE_URL' in core_text and '/downloads/{safe_name}' in core_text:
        bullets.append(
            "In local PDF mode, the core MCP server only emits a browser-download URL when one of "
            "`PUBLIC_BASE_URL`, `API_PUBLIC_URL`, or `BASE_URL` is configured."
        )

    return bullets


def _bedrock_candidate_chain(default_model_id: str, default_region: str) -> list[str]:
    model_id = default_model_id.strip()
    if not model_id:
        return []

    candidates = [model_id]
    if "." not in model_id.split("/")[0]:
        region = default_region or "us-east-1"
        if region.startswith("us-"):
            prefixes = ["us", "eu", "apac"]
        elif region.startswith("eu-"):
            prefixes = ["eu", "us", "apac"]
        else:
            prefixes = ["apac", "us", "eu"]
        candidates.extend(f"{prefix}.{model_id}" for prefix in prefixes)
    return candidates


def _markdown_table(headers: list[str], rows: Iterable[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _code(text: str) -> str:
    return f"`{text}`"


def render_generated_block() -> str:
    config_defaults = _extract_config_defaults()
    core_defaults = _extract_module_getenv_defaults(CORE_MCP_PATH)
    quota_defaults = _extract_module_getenv_defaults(QUOTA_PATH)
    routes = _extract_routes()
    regexes = _extract_regex_patterns()

    ai_provider_default = config_defaults.get("AI_PROVIDER", "")
    bedrock_model_default = config_defaults.get("BEDROCK_MODEL_ID", "")
    default_region = config_defaults.get("DEFAULT_AWS_REGION", "")
    grok_model_default = config_defaults.get("GROK_MODEL_ID", "")
    grok_api_url_default = config_defaults.get("GROK_API_URL", "")
    enable_search_default = config_defaults.get("ENABLE_MCP_SEARCH", "")
    async_chat_default = config_defaults.get("ASYNC_CHAT_ENABLED", "")
    upload_allowed_exts_default = config_defaults.get("UPLOAD_ALLOWED_EXTS", "")
    daily_token_limit = config_defaults.get("DAILY_TOKEN_LIMIT", "")
    daily_pdf_limit = config_defaults.get("DAILY_PDF_LIMIT", "")
    daily_email_limit = config_defaults.get("DAILY_EMAIL_LIMIT", "")
    uploads_dir_default = config_defaults.get("UPLOADS_DIR", "")
    quota_local_fallback_default = quota_defaults.get("QUOTA_LOCAL_FALLBACK", "")
    s3_quota_max_retries_default = quota_defaults.get("S3_QUOTA_MAX_RETRIES", "")
    quota_local_dir_default = quota_defaults.get("QUOTA_LOCAL_DIR", "")
    pdf_max_mb_default = core_defaults.get("_MAX_PDF_MB", "")
    pdf_max_chars_default = core_defaults.get("_MAX_PDF_CHARS", "")
    pdf_url_expires_default = ""
    downloads_dir_default = ""
    upload_presign_expires_default = ""

    # Fill values that are easier to identify directly from source strings than from assignment targets.
    if not quota_local_fallback_default:
        quota_local_fallback_default = _extract_env_default_from_text(QUOTA_PATH, "QUOTA_LOCAL_FALLBACK")
    if not quota_local_dir_default:
        quota_local_dir_default = _extract_env_default_from_text(QUOTA_PATH, "QUOTA_LOCAL_DIR")
    if not s3_quota_max_retries_default:
        s3_quota_max_retries_default = _extract_env_default_from_text(QUOTA_PATH, "S3_QUOTA_MAX_RETRIES")
    if not pdf_url_expires_default:
        pdf_url_expires_default = _extract_env_default_from_text(CORE_MCP_PATH, "PDF_URL_EXPIRES_SECONDS")
    if not downloads_dir_default:
        downloads_dir_default = _extract_env_default_from_text(CORE_MCP_PATH, "DOWNLOADS_DIR")
    if not upload_presign_expires_default:
        upload_presign_expires_default = _extract_env_default_from_text(SERVER_PATH, "UPLOAD_PRESIGN_EXPIRES_SECONDS")

    route_rows = [
        [_code(route.method), _code(route.path), _code(route.function_name), _code(route.router_file)]
        for route in routes
    ]
    runtime_rows = [
        [_code("AI_PROVIDER"), _code(ai_provider_default), "Default provider selection"],
        [_code("BEDROCK_MODEL_ID"), _code(bedrock_model_default), "Default Bedrock model identifier"],
        [_code("DEFAULT_AWS_REGION"), _code(default_region), "Default AWS region used by runtime clients"],
        [_code("GROK_MODEL_ID"), _code(grok_model_default), "Default Grok model identifier"],
        [_code("GROK_API_URL"), _code(grok_api_url_default), "Default Grok base URL"],
        [_code("ENABLE_MCP_SEARCH"), _code(enable_search_default), "Default search-tool toggle"],
        [_code("ASYNC_CHAT_ENABLED"), _code(async_chat_default), "Default chat transport mode"],
        [_code("UPLOAD_ALLOWED_EXTS"), _code(upload_allowed_exts_default), "Default direct upload extension allowlist"],
    ]
    quota_rows = [
        [_code("DAILY_TOKEN_LIMIT"), _code(daily_token_limit), "Per-user daily token limit"],
        [_code("DAILY_PDF_LIMIT"), _code(daily_pdf_limit), "Per-user daily PDF action limit"],
        [_code("DAILY_EMAIL_LIMIT"), _code(daily_email_limit), "Per-user daily email action limit"],
        [_code("QUOTA_LOCAL_FALLBACK"), _code(quota_local_fallback_default), "Enable local quota fallback when remote quota backends are absent"],
        [_code("QUOTA_LOCAL_DIR"), _code(quota_local_dir_default), "Local quota file directory"],
        [_code("S3_QUOTA_MAX_RETRIES"), _code(s3_quota_max_retries_default), "Max optimistic-concurrency retries for S3 quota writes"],
    ]
    artifact_rows = [
        [_code("UPLOADS_DIR"), _code(uploads_dir_default), "Local upload directory used by the API and upload-reader fallback path"],
        [_code("DOWNLOADS_DIR"), _code(downloads_dir_default), "Local directory used for serving generated downloads"],
        [_code("UPLOAD_PRESIGN_EXPIRES_SECONDS"), _code(upload_presign_expires_default), "Default presigned upload URL lifetime"],
        [_code("PDF_MAX_MB"), _code(pdf_max_mb_default), "Max generated PDF size in MB"],
        [_code("PDF_MAX_CHARS"), _code(pdf_max_chars_default), "Max text input size for PDF generation"],
        [_code("PDF_URL_EXPIRES_SECONDS"), _code(pdf_url_expires_default), "Default S3 presigned PDF download lifetime"],
    ]

    pdf_action_re = str(regexes.get("_PDF_ACTION_RE", ""))
    email_address_re = str(regexes.get("_EMAIL_ADDRESS_RE", ""))
    email_action_re = str(regexes.get("_EMAIL_ACTION_RE", ""))
    followup_re = str(regexes.get("_FOLLOWUP_ACTION_RE", ""))
    prior_context_re = str(regexes.get("_PRIOR_ACTION_CONTEXT_RE", ""))
    high_risk_patterns = regexes.get("_HIGH_RISK_PATTERNS", [])
    high_risk_lines = []
    if isinstance(high_risk_patterns, list):
        high_risk_lines = [f"- {_code(pattern)}" for pattern in high_risk_patterns]

    candidate_chain = " -> ".join(_code(item) for item in _bedrock_candidate_chain(bedrock_model_default, default_region))
    artifact_behavior = _upload_download_behavior_summary()

    sections = [
        MARKER_START,
        "> This block is generated from `backend/api/routers/*.py`, `backend/config.py`, `backend/server.py`, `backend/mcp_tools/core_mcp_server.py`, `backend/services/quota.py`, `backend/services/chat_runtime/bedrock_runner.py`, and `backend/services/risk_router.py`.",
        "> Do not hand-edit the contents between these markers; run `python scripts/render_architecture_facts.py --write` instead.",
        "",
        "### Generated Route Inventory",
        "",
        _markdown_table(["Method", "Path", "Router function", "Source file"], route_rows),
        "",
        "### Generated Runtime Defaults",
        "",
        _markdown_table(["Setting", "Default", "Meaning"], runtime_rows),
        "",
        "### Generated Quota Defaults",
        "",
        _markdown_table(["Setting", "Default", "Meaning"], quota_rows),
        "",
        "### Generated Upload And Artifact Defaults",
        "",
        _markdown_table(["Setting", "Default", "Meaning"], artifact_rows),
        "",
        "### Generated Upload And Artifact Behavior Summary",
        "",
        *[f"- {line}" for line in artifact_behavior],
        "",
        "### Generated Bedrock Candidate Resolution",
        "",
        _extract_model_candidate_rules(),
        "",
        f"For the current defaults, the candidate chain is: {candidate_chain}.",
        "",
        "### Generated Required-Tool Contract Summary",
        "",
        "The current `required_tool_sequence(message, conversation)` implementation appends required tools in this order:",
        "",
        f"1. {_code('generate_pdf_from_text')} when the current message matches `_PDF_ACTION_RE`, currently {_code(pdf_action_re)}.",
        f"2. {_code('send_resend_email')} when `requires_email_tool_action(message, conversation)` returns `True`.",
        "",
        "Because the list is built in that order, the enforced combined contract for a request that needs both actions is:",
        "",
        f"{_code('generate_pdf_from_text')} -> {_code('send_resend_email')}",
        "",
        "The current email-action detector returns `True` when any of these conditions holds:",
        "",
        f"- the current message matches `_EMAIL_ADDRESS_RE`, currently {_code(email_address_re)}",
        f"- the current message matches `_EMAIL_ACTION_RE`, currently {_code(email_action_re)}",
        f"- the current message matches `_FOLLOWUP_ACTION_RE`, currently {_code(followup_re)}, and recent conversation text matches `_PRIOR_ACTION_CONTEXT_RE`, currently {_code(prior_context_re)}",
        "",
        "The current high-risk keyword patterns are:",
        "",
        *high_risk_lines,
        MARKER_END,
    ]
    return "\n".join(sections).rstrip() + "\n"


def _replace_generated_block(document: str, generated_block: str) -> str:
    pattern = re.compile(
        rf"{re.escape(MARKER_START)}.*?{re.escape(MARKER_END)}\n?",
        re.DOTALL,
    )
    if not pattern.search(document):
        raise SystemExit(
            "Generated markers not found in ARCHITECTURE.md. "
            "Add the marker block before running this script."
        )
    return pattern.sub(lambda _: generated_block, document, count=1)


def write_generated_block() -> None:
    current = _read(ARCHITECTURE_PATH)
    updated = _replace_generated_block(current, render_generated_block())
    if updated != current:
        ARCHITECTURE_PATH.write_text(updated, encoding="utf-8")


def check_generated_block() -> int:
    current = _read(ARCHITECTURE_PATH)
    expected = _replace_generated_block(current, render_generated_block())
    if current != expected:
        sys.stderr.write(
            "ARCHITECTURE.md generated facts are out of date.\n"
            "Run: python scripts/render_architecture_facts.py --write\n"
        )
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Render or verify generated architecture facts.")
    parser.add_argument("--write", action="store_true", help="Update ARCHITECTURE.md in place.")
    parser.add_argument("--check", action="store_true", help="Fail if ARCHITECTURE.md is out of date.")
    args = parser.parse_args()

    if args.write and args.check:
        parser.error("Use either --write or --check, not both.")

    if args.write:
        write_generated_block()
        return 0
    if args.check:
        return check_generated_block()

    sys.stdout.write(render_generated_block())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
