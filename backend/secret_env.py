import base64
import json
import os
import threading
from typing import Dict, Iterable

import boto3


_LOCK = threading.Lock()
_SECRET_CACHE: Dict[str, Dict[str, str]] = {}


def _aws_region() -> str:
    return (
        os.getenv("DEFAULT_AWS_REGION", "").strip()
        or os.getenv("AWS_REGION", "").strip()
        or os.getenv("AWS_DEFAULT_REGION", "").strip()
        or "us-east-1"
    )


def _runtime_secret_id() -> str:
    return os.getenv("APP_RUNTIME_SECRETS_ARN", "").strip()


def _load_runtime_secrets() -> Dict[str, str]:
    secret_id = _runtime_secret_id()
    if not secret_id:
        return {}

    with _LOCK:
        cached = _SECRET_CACHE.get(secret_id)
        if cached is not None:
            return dict(cached)

    client = boto3.client("secretsmanager", region_name=_aws_region())
    response = client.get_secret_value(SecretId=secret_id)
    raw = response.get("SecretString")
    if not raw and response.get("SecretBinary"):
        raw = base64.b64decode(response["SecretBinary"]).decode("utf-8")

    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}

    normalized = {
        str(key): str(value).strip()
        for key, value in parsed.items()
        if key and value is not None and str(value).strip()
    }
    with _LOCK:
        _SECRET_CACHE[secret_id] = dict(normalized)
    return dict(normalized)


def get_secret_env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is not None and str(value).strip():
        return str(value).strip()
    return str(_load_runtime_secrets().get(name, default)).strip()


def hydrate_secret_env(names: Iterable[str]) -> None:
    for name in names:
        value = get_secret_env(name, "")
        if value and not os.getenv(name):
            os.environ[name] = value
