import os
import sys
from typing import Dict, List, Optional

from mcp_tools.tracing import build_trace_context_env
from secret_env import get_secret_env

MCP_DIR = os.path.abspath(os.path.dirname(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(MCP_DIR, os.pardir))
_OTEL_ENV_KEYS = (
    "OTEL_ENABLED",
    "OTEL_ENVIRONMENT",
    "OTEL_TRACES_SAMPLE_RATE",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_HEADERS",
    "OTEL_LOGS_ENABLED",
    "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
    "OTEL_EXPORTER_OTLP_LOGS_HEADERS",
    "OTEL_LOGS_MIN_LEVEL",
    "APP_TIMEZONE",
    "APP_RUNTIME_SECRETS_ARN",
)


def resolve_mcp_python() -> str:
    env_python = os.getenv("MCP_PYTHON", "").strip()
    if env_python and os.path.exists(env_python):
        return env_python

    venv = os.getenv("VIRTUAL_ENV", "").strip()
    candidates = []
    if venv:
        candidates.append(os.path.join(venv, "bin", "python"))
    candidates.append(os.path.join(BACKEND_DIR, ".venv", "bin", "python"))

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate

    return sys.executable or "python3"


def _build_async_env(job_id: Optional[str]) -> Dict[str, str]:
    if not job_id:
        return {}
    return {
        "ASYNC_JOB_ID": job_id,
        "APP_RUNTIME_SECRETS_ARN": os.getenv("APP_RUNTIME_SECRETS_ARN", ""),
        "ASYNC_JOB_TTL_SECONDS": os.getenv("ASYNC_JOB_TTL_SECONDS", "3600"),
    }


def _build_pythonpath() -> str:
    base_pythonpath = os.getenv("PYTHONPATH", "").strip()
    path_parts = [p for p in base_pythonpath.split(":") if p]
    if BACKEND_DIR not in path_parts:
        path_parts.insert(0, BACKEND_DIR)
    return ":".join(path_parts) if path_parts else BACKEND_DIR


def _build_aws_env() -> Dict[str, str]:
    aws_env = {k: v for k, v in os.environ.items() if k.startswith("AWS_") and v}
    default_region = os.getenv("DEFAULT_AWS_REGION", "").strip()
    if default_region:
        aws_env.setdefault("AWS_REGION", default_region)
        aws_env.setdefault("AWS_DEFAULT_REGION", default_region)
    return aws_env


def _build_otel_env() -> Dict[str, str]:
    return {k: v for k in _OTEL_ENV_KEYS if (v := os.getenv(k, ""))}


def _compose_env(
    *,
    merged_pythonpath: str,
    base_otel_service: str,
    service_suffix: str,
    extra_env: Dict[str, str],
    common_env: Dict[str, str],
) -> Dict[str, str]:
    return {
        "PYTHONPATH": merged_pythonpath,
        "OTEL_SERVICE_NAME": f"{base_otel_service}-{service_suffix}",
        **extra_env,
        **common_env,
    }


def _build_spec(name: str, python_cmd: str, script_name: str, env: Dict[str, str]) -> Dict:
    return {
        "name": name,
        "params": {
            "command": python_cmd,
            "args": [os.path.join(MCP_DIR, script_name)],
            "env": env,
        },
    }


def build_mcp_server_specs(enable_search: bool = True, job_id: Optional[str] = None) -> List[Dict]:
    python_cmd = resolve_mcp_python()
    brave_key = get_secret_env("BRAVE_API_KEY", "")
    async_env = _build_async_env(job_id)
    merged_pythonpath = _build_pythonpath()
    aws_env = _build_aws_env()
    otel_env = _build_otel_env()
    trace_env = build_trace_context_env()
    common_env = {**async_env, **aws_env, **otel_env, **trace_env}
    base_otel_service = os.getenv("OTEL_SERVICE_NAME", "digital-assistant-backend").strip() or "digital-assistant-backend"
    brave_env = _compose_env(
        merged_pythonpath=merged_pythonpath,
        base_otel_service=base_otel_service,
        service_suffix="mcp-brave",
        extra_env={"BRAVE_API_KEY": brave_key} if brave_key else {},
        common_env=common_env,
    )
    resend_from = os.getenv("RESEND_FROM", "no-reply@agentairg.site").strip()
    core_env = _compose_env(
        merged_pythonpath=merged_pythonpath,
        base_otel_service=base_otel_service,
        service_suffix="mcp-core",
        extra_env={
            "UPLOADS_DIR": os.getenv("UPLOADS_DIR", "/tmp/uploads"),
            "USE_S3": os.getenv("USE_S3", "false"),
            "UPLOADS_BUCKET": os.getenv("UPLOADS_BUCKET", ""),
            "S3_BUCKET": os.getenv("S3_BUCKET", ""),
            "DEFAULT_AWS_REGION": os.getenv("DEFAULT_AWS_REGION", "us-east-1"),
            "RESEND_FROM": resend_from,
            "PUBLIC_BASE_URL": os.getenv("PUBLIC_BASE_URL", ""),
            "API_PUBLIC_URL": os.getenv("API_PUBLIC_URL", ""),
            "BASE_URL": os.getenv("BASE_URL", ""),
            "DOWNLOADS_DIR": os.getenv("DOWNLOADS_DIR", "/tmp/downloads"),
            "DOWNLOADS_BUCKET": os.getenv("DOWNLOADS_BUCKET", ""),
            "PDF_MAX_MB": os.getenv("PDF_MAX_MB", "50"),
            "PDF_MAX_CHARS": os.getenv("PDF_MAX_CHARS", "200000"),
            "PDF_URL_EXPIRES_SECONDS": os.getenv("PDF_URL_EXPIRES_SECONDS", "86400"),
            "PYTHONUNBUFFERED": "1",
        },
        common_env=common_env,
    )
    memory_env = _compose_env(
        merged_pythonpath=merged_pythonpath,
        base_otel_service=base_otel_service,
        service_suffix="mcp-memory",
        extra_env={
            "AI_PROVIDER": os.getenv("AI_PROVIDER", "bedrock"),
            "GROK_API_URL": os.getenv("GROK_API_URL", "https://api.x.ai/v1"),
            "GROK_MODEL_ID": os.getenv("GROK_MODEL_ID", "grok-4-1-fast"),
            "BEDROCK_MODEL_ID": os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"),
            "DEFAULT_AWS_REGION": os.getenv("DEFAULT_AWS_REGION", "us-east-1"),
        },
        common_env=common_env,
    )

    specs: List[Dict] = []

    # Brave Search MCP server (Python + Brave API)
    if enable_search and brave_key:
        specs.append(_build_spec("mcp-brave-search", python_cmd, "brave_mcp_server.py", brave_env))

    # Core MCP server (PDF + email + uploads)
    specs.append(_build_spec("mcp-core-tools", python_cmd, "core_mcp_server.py", core_env))

    # Memory extraction MCP server
    specs.append(_build_spec("mcp-memory", python_cmd, "memory_mcp_server.py", memory_env))

    return specs
