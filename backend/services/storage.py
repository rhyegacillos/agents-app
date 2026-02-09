import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests
from botocore.exceptions import ClientError
from fastapi import HTTPException, UploadFile

from config import (
    FILENAME_PATTERN,
    MEMORY_APPROVED_MAX,
    MEMORY_CANDIDATES_MAX,
    MEMORY_DIR,
    S3_BUCKET,
    UPLOAD_ALLOWED_EXTS,
    UPSTASH_REDIS_REST_TOKEN,
    UPSTASH_REDIS_REST_URL,
    USER_ID_PATTERN,
    USE_S3,
    s3_client,
)


def validate_user_id(user_id: Optional[str]) -> str:
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    user_id = user_id.strip()
    if not USER_ID_PATTERN.match(user_id):
        raise HTTPException(status_code=400, detail="user_id invalid")
    return user_id


def _upstash_enabled() -> bool:
    return bool(UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN)


def _upstash_request(
    path: str,
    *,
    method: str = "GET",
    data: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not _upstash_enabled():
        raise HTTPException(status_code=500, detail="Upstash Redis is not configured")
    base = UPSTASH_REDIS_REST_URL.rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    headers = {"Authorization": f"Bearer {UPSTASH_REDIS_REST_TOKEN}"}
    try:
        if method.upper() == "POST":
            resp = requests.post(
                url,
                headers=headers,
                params=params,
                data=data or "",
                timeout=10,
            )
        else:
            resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Upstash Redis error: {exc}") from exc
    if isinstance(payload, dict) and payload.get("error"):
        raise HTTPException(status_code=500, detail=f"Upstash Redis error: {payload['error']}")
    return payload


def _upstash_set(key: str, value: Dict[str, Any], ttl_seconds: int) -> None:
    encoded_key = quote(key, safe="")
    params = {"EX": str(ttl_seconds)} if ttl_seconds > 0 else None
    _upstash_request(
        f"set/{encoded_key}",
        method="POST",
        data=json.dumps(value),
        params=params,
    )


def _upstash_get(key: str) -> Optional[Dict[str, Any]]:
    encoded_key = quote(key, safe="")
    payload = _upstash_request(f"get/{encoded_key}")
    result = payload.get("result")
    if result is None:
        return None
    if isinstance(result, dict):
        return result
    try:
        return json.loads(result)
    except Exception:
        return {"value": result}


def _job_key(job_id: str) -> str:
    return f"job:{job_id}"


def _memory_candidates_key(user_id: str) -> str:
    return f"memory/{user_id}/memory_candidates.json"


def _memory_approved_key(user_id: str) -> str:
    return f"memory/{user_id}/memory_approved.json"


def _memory_last_extracted_key(user_id: str) -> str:
    return f"memory/{user_id}/memory_last_extracted.json"


def _load_json_list(key: str) -> List[Dict[str, Any]]:
    if USE_S3:
        if not s3_client:
            raise RuntimeError("S3 client is not configured")
        try:
            response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
            return json.loads(response["Body"].read().decode("utf-8"))
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return []
            raise
    else:
        file_path = os.path.join(MEMORY_DIR, key)
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []


def _save_json_list(key: str, items: List[Dict[str, Any]]) -> None:
    if USE_S3:
        if not s3_client:
            raise RuntimeError("S3 client is not configured")
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=json.dumps(items, indent=2),
            ContentType="application/json",
        )
    else:
        file_path = os.path.join(MEMORY_DIR, key)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2)


def load_memory_candidates(user_id: str) -> List[Dict[str, Any]]:
    return _load_json_list(_memory_candidates_key(user_id))


def save_memory_candidates(user_id: str, items: List[Dict[str, Any]]) -> None:
    _save_json_list(_memory_candidates_key(user_id), items[:MEMORY_CANDIDATES_MAX])


def load_approved_memory(user_id: str) -> List[Dict[str, Any]]:
    items = _load_json_list(_memory_approved_key(user_id))
    now = datetime.utcnow()
    filtered: List[Dict[str, Any]] = []
    changed = False
    for item in items:
        expires_at = item.get("expires_at")
        if expires_at:
            try:
                if datetime.fromisoformat(expires_at) < now:
                    changed = True
                    continue
            except ValueError:
                changed = True
        filtered.append(item)
    if changed:
        _save_json_list(_memory_approved_key(user_id), filtered)
    return filtered


def save_approved_memory(user_id: str, items: List[Dict[str, Any]]) -> None:
    _save_json_list(_memory_approved_key(user_id), items[:MEMORY_APPROVED_MAX])


def load_memory_last_extracted_at(user_id: str) -> Optional[str]:
    payload = _load_json_list(_memory_last_extracted_key(user_id))
    if isinstance(payload, list) and payload:
        item = payload[0] if isinstance(payload[0], dict) else None
        if item:
            return str(item.get("last_extracted_at") or "") or None
    if isinstance(payload, dict):
        return str(payload.get("last_extracted_at") or "") or None
    return None


def save_memory_last_extracted_at(user_id: str, extracted_at: str) -> None:
    _save_json_list(_memory_last_extracted_key(user_id), [{"last_extracted_at": extracted_at}])


def sanitize_filename(name: str) -> str:
    cleaned = FILENAME_PATTERN.sub("_", name or "").strip("._")
    return cleaned or f"upload-{os.urandom(8).hex()}"


def validate_upload_file(file: UploadFile) -> str:
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="file required")
    ext = os.path.splitext(file.filename)[1].lower().lstrip(".")
    if ext not in UPLOAD_ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail="file type not allowed")
    return ext


def get_memory_path(user_id: str, session_id: str) -> str:
    return f"{user_id}/{session_id}.json"


def load_conversation(user_id: str, session_id: str) -> List[Dict]:
    key = get_memory_path(user_id, session_id)
    if USE_S3:
        if not s3_client:
            raise RuntimeError("S3 client is not configured")
        try:
            response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
            return json.loads(response["Body"].read().decode("utf-8"))
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return []
            raise
    else:
        file_path = os.path.join(MEMORY_DIR, key)
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []


def save_conversation(user_id: str, session_id: str, messages: List[Dict]):
    key = get_memory_path(user_id, session_id)
    if USE_S3:
        if not s3_client:
            raise RuntimeError("S3 client is not configured")
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=json.dumps(messages, indent=2),
            ContentType="application/json",
        )
    else:
        file_path = os.path.join(MEMORY_DIR, key)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(messages, f, indent=2)


def parse_message_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def truncate_title(text: str, max_len: int = 80) -> str:
    cleaned = " ".join(text.strip().split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1] + "…"


def list_session_objects(user_id: str) -> List[Dict]:
    objects: List[Dict] = []
    prefix = f"{user_id}/"
    if USE_S3:
        if not s3_client:
            raise RuntimeError("S3 client is not configured")
        paginator = s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
            for obj in page.get("Contents", []) or []:
                key = obj.get("Key", "")
                if not key.endswith(".json"):
                    continue
                session_id = key[len(prefix) :].rsplit(".", 1)[0]
                objects.append(
                    {
                        "session_id": session_id,
                        "key": key,
                        "last_modified": obj.get("LastModified"),
                    }
                )
    else:
        user_dir = os.path.join(MEMORY_DIR, user_id)
        if not os.path.isdir(user_dir):
            return []
        for name in os.listdir(user_dir):
            if not name.endswith(".json"):
                continue
            session_id = name.rsplit(".", 1)[0]
            path = os.path.join(user_dir, name)
            objects.append(
                {
                    "session_id": session_id,
                    "key": path,
                    "last_modified": datetime.fromtimestamp(os.path.getmtime(path)),
                }
            )
    return objects


def sort_last_modified(item: Dict) -> float:
    value = item.get("last_modified")
    if isinstance(value, datetime):
        return value.timestamp()
    return 0.0


def list_conversations(user_id: str, limit: int = 5) -> List[Dict]:
    objects = list_session_objects(user_id)
    objects.sort(key=sort_last_modified, reverse=True)
    sessions: List[Dict] = []
    for obj in objects[:limit]:
        session_id = obj["session_id"]
        messages = load_conversation(user_id, session_id)
        last_message = messages[-1] if messages else {}
        last_ts = parse_message_timestamp(last_message.get("timestamp"))
        updated_at = last_ts or obj.get("last_modified") or datetime.utcnow()
        title = truncate_title(str(last_message.get("content", "") or "New conversation"))
        sessions.append(
            {
                "session_id": session_id,
                "title": title or "New conversation",
                "updated_at": updated_at.isoformat(),
                "message_count": len(messages),
            }
        )
    return sessions


def prune_conversations(user_id: str, keep: int = 5) -> None:
    objects = list_session_objects(user_id)
    if len(objects) <= keep:
        return
    objects.sort(key=sort_last_modified, reverse=True)
    for obj in objects[keep:]:
        if USE_S3:
            if not s3_client:
                raise RuntimeError("S3 client is not configured")
            s3_client.delete_object(Bucket=S3_BUCKET, Key=obj["key"])
        else:
            try:
                os.remove(obj["key"])
            except FileNotFoundError:
                pass
