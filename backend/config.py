import logging
import os
import re

import boto3
from dotenv import load_dotenv

from resources import facts


load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logging.getLogger().setLevel(LOG_LEVEL)

# AI provider selection
AI_PROVIDER = os.getenv("AI_PROVIDER", "bedrock").strip().lower()

# Grok model configuration
GROK_MODEL_ID = os.getenv("GROK_MODEL_ID", "grok-4-1-fast")
GROK_API_URL = os.getenv("GROK_API_URL", "https://api.x.ai/v1")
GROK_API_KEY = os.getenv("GROK_API_KEY", "").strip()

# Bedrock client (fallback)
DEFAULT_AWS_REGION = os.getenv("DEFAULT_AWS_REGION", "us-east-1")
bedrock_client = boto3.client("bedrock-runtime", region_name=DEFAULT_AWS_REGION)
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

# MCP search control
ENABLE_MCP_SEARCH = os.getenv("ENABLE_MCP_SEARCH", "true").lower() == "true"

# Async chat (queue/worker) configuration
ASYNC_CHAT_ENABLED = os.getenv("ASYNC_CHAT_ENABLED", "false").lower() == "true"
UPSTASH_REDIS_REST_URL = os.getenv("UPSTASH_REDIS_REST_URL", "").strip()
UPSTASH_REDIS_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()
ASYNC_JOB_TTL_SECONDS = int(os.getenv("ASYNC_JOB_TTL_SECONDS", "3600"))
ASYNC_WORKER_FUNCTION_NAME = os.getenv("ASYNC_WORKER_FUNCTION_NAME", "").strip()
LLM_TIMEOUT_SECONDS = os.getenv("LLM_TIMEOUT_SECONDS", "").strip()
MCP_STARTUP_TIMEOUT_SECONDS = os.getenv("MCP_STARTUP_TIMEOUT_SECONDS", "").strip()
RUNNER_TIMEOUT_SECONDS = os.getenv("RUNNER_TIMEOUT_SECONDS", "").strip()
MEMORY_EXTRACT_SYNC = os.getenv("MEMORY_EXTRACT_SYNC", "false").lower() == "true"

# Memory storage configuration
USE_S3 = os.getenv("USE_S3", "false").lower() == "true"
S3_BUCKET = os.getenv("S3_BUCKET", "")
MEMORY_DIR = os.getenv("MEMORY_DIR", "../memory")

# Upload configuration
UPLOADS_DIR = os.getenv("UPLOADS_DIR", "/tmp/uploads")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
UPLOAD_ALLOWED_EXTS = {
    ext.strip().lower()
    for ext in os.getenv("UPLOAD_ALLOWED_EXTS", "pdf,docx,txt,md").split(",")
    if ext.strip()
}
UPLOADS_BUCKET = os.getenv("UPLOADS_BUCKET") or S3_BUCKET

# Initialize S3 client if needed
s3_client = boto3.client("s3") if USE_S3 else None

# Memory management configuration
USER_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{8,64}$")
FILENAME_PATTERN = re.compile(r"[^a-zA-Z0-9._-]+")
MEMORY_CANDIDATES_MAX = int(os.getenv("MEMORY_CANDIDATES_MAX", "50"))
MEMORY_APPROVED_MAX = int(os.getenv("MEMORY_APPROVED_MAX", "200"))

MEMORY_MODEL = (facts or {}).get("memory_model", {})
MEMORY_LAYERS = MEMORY_MODEL.get("memory_layers", [])
MEMORY_WHAT_TO_STORE = MEMORY_MODEL.get("what_to_store", [])
MEMORY_WHAT_NOT_TO_STORE = MEMORY_MODEL.get("what_not_to_store", [])
MEMORY_TTL_MAP = {layer.get("name"): layer.get("ttl_days") for layer in MEMORY_LAYERS}
