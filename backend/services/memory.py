import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

from config import (
    AI_PROVIDER,
    BEDROCK_MODEL_ID,
    DEFAULT_AWS_REGION,
    GROK_API_KEY,
    GROK_API_URL,
    GROK_MODEL_ID,
    MEMORY_LAYERS,
    MEMORY_TTL_MAP,
    MEMORY_WHAT_NOT_TO_STORE,
    MEMORY_WHAT_TO_STORE,
)
from mcp_tools.mcp_servers import resolve_mcp_python
from services.storage import (
    load_approved_memory,
    load_memory_last_extracted_at,
    load_memory_candidates,
    save_memory_last_extracted_at,
    save_memory_candidates,
)


def build_memory_extraction_input(conversation: List[Dict], limit: int = 6) -> str:
    lines: List[str] = []
    count = 0
    for msg in reversed(conversation):
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "user":
            continue
        content = str(msg.get("content", "")).strip()
        if not content:
            continue
        lines.append(f"User: {content}")
        count += 1
        if count >= limit:
            break
    return "\n".join(reversed(lines))


def _normalize_memory_text(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip().lower())
    text = re.sub(r"[^\w\s]+", "", text)
    return text.strip()


def _is_duplicate_memory(text: str, existing: set[str]) -> bool:
    if not text:
        return True
    if text in existing:
        return True
    if len(text) >= 10:
        for item in existing:
            if text in item or item in text:
                return True
    return False


def _memory_mcp_params() -> StdioServerParameters:
    python_cmd = resolve_mcp_python()
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    base_pythonpath = os.getenv("PYTHONPATH", "").strip()
    path_parts = [p for p in base_pythonpath.split(":") if p]
    if backend_dir not in path_parts:
        path_parts.insert(0, backend_dir)
    merged_pythonpath = ":".join(path_parts) if path_parts else backend_dir
    aws_env = {k: v for k, v in os.environ.items() if k.startswith("AWS_") and v}
    if DEFAULT_AWS_REGION:
        aws_env.setdefault("AWS_REGION", DEFAULT_AWS_REGION)
        aws_env.setdefault("AWS_DEFAULT_REGION", DEFAULT_AWS_REGION)

    return StdioServerParameters(
        command=python_cmd,
        args=[os.path.join(backend_dir, "mcp_tools", "memory_mcp_server.py")],
        env={
            "AI_PROVIDER": AI_PROVIDER,
            "GROK_API_KEY": GROK_API_KEY,
            "GROK_API_URL": GROK_API_URL,
            "GROK_MODEL_ID": GROK_MODEL_ID,
            "BEDROCK_MODEL_ID": BEDROCK_MODEL_ID,
            "DEFAULT_AWS_REGION": DEFAULT_AWS_REGION,
            "PYTHONPATH": merged_pythonpath,
            **aws_env,
        },
    )


async def _call_memory_extractor(
    conversation_snippet: str,
    existing_memory: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    try:
        logging.info("[memory] calling extractor (chars=%d)", len(conversation_snippet))
        async with stdio_client(_memory_mcp_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "extract_memory_candidates",
                    arguments={
                        "conversation": conversation_snippet,
                        "existing_memory": existing_memory,
                        "memory_layers": MEMORY_LAYERS,
                        "what_to_store": MEMORY_WHAT_TO_STORE,
                        "what_not_to_store": MEMORY_WHAT_NOT_TO_STORE,
                    },
                )
                if result.isError:
                    logging.warning("[memory] extractor returned error")
                    return []
                payload = result.structuredContent or getattr(result, "structured_content", None)
                if payload is None and hasattr(result, "model_dump"):
                    dumped = result.model_dump()
                    payload = dumped.get("structuredContent") or dumped.get("structured_content")
                if isinstance(payload, dict) and "result" in payload:
                    payload = payload.get("result")
                if isinstance(payload, list):
                    candidates = payload
                else:
                    payload = payload or {}
                    candidates = payload.get("candidates", [])

                logging.info(
                    "[memory] extractor candidates=%d",
                    len(candidates) if isinstance(candidates, list) else 0,
                )
                return candidates if isinstance(candidates, list) else []
    except Exception as exc:
        logging.warning("[memory] extraction failed: %s", exc)
        return []


async def extract_and_store_memory(user_id: str, session_id: str, conversation: List[Dict[str, Any]]) -> None:
    def parse_dt(v: Any) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(str(v)) if v else None
        except ValueError:
            return None

    # newest user timestamp
    last_user_ts = max(
        (parse_dt(m.get("timestamp")) for m in conversation if isinstance(m, dict) and m.get("role") == "user"),
        default=None,
    )
    if not last_user_ts:
        logging.info("[memory] skip: no user timestamp")
        return

    # skip if nothing new
    last_extracted = parse_dt(load_memory_last_extracted_at(user_id))
    if last_extracted and last_user_ts <= last_extracted:
        logging.info("[memory] skip: already extracted last_user_ts=%s", last_user_ts.isoformat())
        return

    # inputs
    pending = load_memory_candidates(user_id) or []
    approved = load_approved_memory(user_id) or []
    existing = [
        {"text": str(x.get("text", "")).strip(), "category": str(x.get("category", "")).strip(), "ttl_days": x.get("ttl_days")}
        for x in (pending + approved)
        if str(x.get("text", "")).strip()
    ]
    existing_norms = {_normalize_memory_text(item.get("text", "")) for item in existing}
    existing_norms = {n for n in existing_norms if n}

    snippet = build_memory_extraction_input(conversation, limit=6)
    if not str(snippet).strip():
        logging.info("[memory] skip: empty snippet")
        return

    candidates = await _call_memory_extractor(snippet, existing) or []
    if not candidates:
        save_memory_last_extracted_at(user_id, last_user_ts.isoformat())
        return

    # re-check (parallel runs)
    last_extracted = parse_dt(load_memory_last_extracted_at(user_id))
    if last_extracted and last_user_ts <= last_extracted:
        logging.info("[memory] skip: extracted during run last_user_ts=%s", last_user_ts.isoformat())
        return

    now = datetime.now(timezone.utc).isoformat()
    added = 0
    new_norms: set[str] = set()
    for c in candidates:
        text = str(c.get("text", "")).strip()
        cat = str(c.get("category", "")).strip()
        if not text or cat not in MEMORY_TTL_MAP:
            continue
        norm = _normalize_memory_text(text)
        if _is_duplicate_memory(norm, existing_norms | new_norms):
            continue
        ttl = c.get("ttl_days") or MEMORY_TTL_MAP[cat]
        try:
            ttl = int(ttl)
        except (TypeError, ValueError):
            ttl = int(MEMORY_TTL_MAP[cat])

        pending.append(
            {
                "id": uuid.uuid4().hex,
                "text": text,
                "category": cat,
                "ttl_days": ttl,
                "session_id": session_id,
                "created_at": now,
                "source": {"message_ids": [], "excerpt": str(c.get("excerpt", "")).strip()},
            }
        )
        new_norms.add(norm)
        added += 1

    if added:
        save_memory_candidates(user_id, pending)
    save_memory_last_extracted_at(user_id, last_user_ts.isoformat())
    logging.info("[memory] saved candidates: added=%d total_pending=%d", added, len(pending))
