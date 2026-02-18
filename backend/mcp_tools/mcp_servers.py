import os
import sys
from typing import Dict, List, Optional

MCP_DIR = os.path.abspath(os.path.dirname(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(MCP_DIR, os.pardir))


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


def build_mcp_server_specs(enable_search: bool = True, job_id: Optional[str] = None) -> List[Dict]:
    python_cmd = resolve_mcp_python()
    brave_key = os.getenv("BRAVE_API_KEY", "").strip()
    async_env: Dict[str, str] = {}
    if job_id:
        async_env = {
            "ASYNC_JOB_ID": job_id,
            "UPSTASH_REDIS_REST_URL": os.getenv("UPSTASH_REDIS_REST_URL", ""),
            "UPSTASH_REDIS_REST_TOKEN": os.getenv("UPSTASH_REDIS_REST_TOKEN", ""),
            "ASYNC_JOB_TTL_SECONDS": os.getenv("ASYNC_JOB_TTL_SECONDS", "3600"),
        }
    base_pythonpath = os.getenv("PYTHONPATH", "").strip()
    path_parts = [p for p in base_pythonpath.split(":") if p]
    if BACKEND_DIR not in path_parts:
        path_parts.insert(0, BACKEND_DIR)
    merged_pythonpath = ":".join(path_parts) if path_parts else BACKEND_DIR
    aws_env = {k: v for k, v in os.environ.items() if k.startswith("AWS_") and v}
    otel_env = {
        k: os.getenv(k, "")
        for k in (
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
        )
    }
    otel_env = {k: v for k, v in otel_env.items() if v}
    base_otel_service = os.getenv("OTEL_SERVICE_NAME", "digital-assistant-backend").strip() or "digital-assistant-backend"
    default_region = os.getenv("DEFAULT_AWS_REGION", "").strip()
    if default_region:
        aws_env.setdefault("AWS_REGION", default_region)
        aws_env.setdefault("AWS_DEFAULT_REGION", default_region)
    brave_env = (
        {
            "BRAVE_API_KEY": brave_key,
            "PYTHONPATH": merged_pythonpath,
            "OTEL_SERVICE_NAME": f"{base_otel_service}-mcp-brave",
            **async_env,
            **aws_env,
            **otel_env,
        }
        if brave_key
        else {
            "PYTHONPATH": merged_pythonpath,
            "OTEL_SERVICE_NAME": f"{base_otel_service}-mcp-brave",
            **async_env,
            **aws_env,
            **otel_env,
        }
    )
    resend_key = os.getenv("RESEND_API_KEY", "").strip()
    resend_from = os.getenv("RESEND_FROM", "no-reply@agentairg.site").strip()
    core_env = {
        "UPLOADS_DIR": os.getenv("UPLOADS_DIR", "/tmp/uploads"),
        "USE_S3": os.getenv("USE_S3", "false"),
        "UPLOADS_BUCKET": os.getenv("UPLOADS_BUCKET", ""),
        "S3_BUCKET": os.getenv("S3_BUCKET", ""),
        "DEFAULT_AWS_REGION": os.getenv("DEFAULT_AWS_REGION", "us-east-1"),
        "RESEND_API_KEY": resend_key,
        "RESEND_FROM": resend_from,
        "PUBLIC_BASE_URL": os.getenv("PUBLIC_BASE_URL", ""),
        "API_PUBLIC_URL": os.getenv("API_PUBLIC_URL", ""),
        "BASE_URL": os.getenv("BASE_URL", ""),
        "DOWNLOADS_DIR": os.getenv("DOWNLOADS_DIR", "/tmp/downloads"),
        "DOWNLOADS_BUCKET": os.getenv("DOWNLOADS_BUCKET", ""),
        "PDF_MAX_MB": os.getenv("PDF_MAX_MB", "50"),
        "PDF_MAX_CHARS": os.getenv("PDF_MAX_CHARS", "200000"),
        "PDF_URL_EXPIRES_SECONDS": os.getenv("PDF_URL_EXPIRES_SECONDS", "86400"),
        "PYTHONPATH": merged_pythonpath,
        "OTEL_SERVICE_NAME": f"{base_otel_service}-mcp-core",
        **async_env,
        **aws_env,
        **otel_env,
    }
    memory_env = {
        "AI_PROVIDER": os.getenv("AI_PROVIDER", "bedrock"),
        "GROK_API_KEY": os.getenv("GROK_API_KEY", ""),
        "GROK_API_URL": os.getenv("GROK_API_URL", "https://api.x.ai/v1"),
        "GROK_MODEL_ID": os.getenv("GROK_MODEL_ID", "grok-4-1-fast"),
        "BEDROCK_MODEL_ID": os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"),
        "DEFAULT_AWS_REGION": os.getenv("DEFAULT_AWS_REGION", "us-east-1"),
        "PYTHONPATH": merged_pythonpath,
        "OTEL_SERVICE_NAME": f"{base_otel_service}-mcp-memory",
        **async_env,
        **aws_env,
        **otel_env,
    }

    specs: List[Dict] = []

    # Brave Search MCP server (Python + Brave API)
    if enable_search and brave_key:
        specs.append(
            {
                "name": "mcp-brave-search",
                "params": {
                    "command": python_cmd,
                    "args": [os.path.join(MCP_DIR, "brave_mcp_server.py")],
                    "env": brave_env,
                },
            }
        )

    # Core MCP server (PDF + email + uploads)
    core_env["PYTHONUNBUFFERED"] = "1"
    specs.append(
        {
            "name": "mcp-core-tools",
            "params": {
                "command": python_cmd,
                "args": [os.path.join(MCP_DIR, "core_mcp_server.py")],
                "env": core_env,
            },
        }
    )

    # Memory extraction MCP server
    specs.append(
        {
            "name": "mcp-memory",
            "params": {
                "command": python_cmd,
                "args": [os.path.join(MCP_DIR, "memory_mcp_server.py")],
                "env": memory_env,
            },
        }
    )

    return specs
