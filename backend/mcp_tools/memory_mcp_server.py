import os
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

import boto3
from mcp.server.fastmcp import FastMCP
from openai import AsyncOpenAI

from mcp_tools.bootstrap import bootstrap_mcp_process
from mcp_tools.status import update_job_status
from tool_instructions import tool_instructions_for

mcp = FastMCP("Memory-Extractor-Service")

AI_PROVIDER = os.getenv("AI_PROVIDER", "bedrock").strip().lower()
GROK_API_KEY = os.getenv("GROK_API_KEY", "").strip()
GROK_API_URL = os.getenv("GROK_API_URL", "https://api.x.ai/v1").strip()
GROK_MODEL_ID = os.getenv("GROK_MODEL_ID", "grok-4-1-fast").strip()
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0").strip()
DEFAULT_AWS_REGION = os.getenv("DEFAULT_AWS_REGION", "us-east-1").strip()

bootstrap_mcp_process(log_level_env="MEMORY_LOG_LEVEL", service_label="mcp-memory")

bedrock_client = boto3.client(
    service_name="bedrock-runtime",
    region_name=DEFAULT_AWS_REGION or "us-east-1",
)


def _tool(name: str):
    def decorator(func):
        doc = tool_instructions_for(name)
        if doc:
            func.__doc__ = doc
        return mcp.tool()(func)
    return decorator


def _extract_json(text: str) -> Dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found")
    return json.loads(text[start : end + 1])


async def _call_grok(system: str, user: str) -> str:
    if not GROK_API_KEY:
        raise RuntimeError("GROK_API_KEY is not configured")
    client = AsyncOpenAI(api_key=GROK_API_KEY, base_url=GROK_API_URL)
    response = await client.chat.completions.create(
        model=GROK_MODEL_ID,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.0,
        max_tokens=900,
    )
    return response.choices[0].message.content or ""


def _call_bedrock(system: str, user: str) -> str:
    response = bedrock_client.converse(
        modelId=BEDROCK_MODEL_ID,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user}]}],
        inferenceConfig={"maxTokens": 900, "temperature": 0.0, "topP": 0.9},
    )
    return response["output"]["message"]["content"][0]["text"]


@_tool("extract_memory_candidates")
async def extract_memory_candidates(
    conversation: str,
    memory_layers: List[Dict[str, Any]],
    what_to_store: List[str],
    what_not_to_store: List[str],
    existing_memory: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """
    Extract memory candidates from a conversation snippet.
    Returns: {"candidates": [ {text, category, ttl_days, excerpt} ]}
    """
    update_job_status("Tool: Memory Extractor", 60)
    ttl_map = {layer.get("name"): layer.get("ttl_days") for layer in memory_layers}
    categories = ", ".join([layer.get("name", "") for layer in memory_layers if layer.get("name")])
    existing_memory = existing_memory or []

    logging.info(
        "[memory_mcp] extract start chars=%d categories=%s",
        len(conversation),
        categories or "none",
    )

    system = (
        "You are a memory extraction engine for an LLM assistant.\n"
        "Goal: propose new, durable memory items about the user (preferences, stable constraints) or their project specs "
        "that will measurably improve future responses.\n\n"

        "OUTPUT (strict): Return JSON only with this exact shape:\n"
        "{\"candidates\": [{\"text\": \"...\", \"category\": \"...\", \"ttl_days\": 0, \"excerpt\": \"...\"}]}\n\n"

        "HARD RULES:\n"
        "1) Allowed categories only. category MUST be one of: " + categories + "\n"
        "2) Privacy/safety: NEVER store secrets or sensitive/private data (credentials, tokens, personal identifiers, "
        "precise location, medical/financial details, legal issues, account numbers, private contact info, etc.).\n"
        "3) Exclude defaults: Do NOT store markdown formatting preferences (assume markdown is already default). "
        "Other format preferences (e.g., strict JSON, plaintext) are allowed ONLY if explicitly requested.\n"
        "4) No duplicates: Treat Existing memory as canonical. If a candidate overlaps in meaning with any Existing memory item, "
        "SKIP it (do not paraphrase, restate, or slightly reword it). 'Overlap' includes synonyms or the same preference stated differently.\n"
        "5) Durability filter: Only store items likely to remain useful for weeks+. Ignore one-off tasks, ephemeral context, "
        "and transient states.\n"
        "6) Preference detection: Prefer explicit preferences (e.g., 'I prefer', 'always', 'from now on'), "
        "but you MAY infer a preference when the user repeats the same request across multiple messages "
        "or corrects the assistant's behavior (e.g., 'stop doing X, do Y instead').\n"
        "7) One-off exclusion: If the request is about a single task or a one-time output (e.g., 'generate a PDF for this' once), "
        "skip it.\n"
        "8) Do NOT store transient failures or delivery issues as memories. "
        "You may store a durable preference that results from repeated failures only if it is phrased as a preference "
        "(e.g., 'always include a download link in addition to email').\n"
        "9) Format scope: Store output format preferences only if the user indicates it should apply broadly "
        "(e.g., 'always use JSON'), not for a single response.\n"
        "10) Specificity: Keep each 'text' short, concrete, and actionable.\n"
        "11) De-dup within this response: If two candidates are similar, keep only the single most specific one.\n"
        "12) Evidence: excerpt MUST be a short verbatim snippet from the conversation provided (at least 5 words).\n"
        "13) Limit: Return at most 5 candidates. If none qualify, return {\"candidates\": []}.\n\n"

        "TTL POLICY:\n"
        "- ttl_days must match the TTL for its category from the provided category/TTL list.\n"
        "- If the category is not in the TTL list, skip the candidate.\n"
    )


    user = (
        "INPUTS:\n\n"
        "Conversation snippet:\n"
        f"{conversation}\n\n"
        "Allowed memory categories (with TTL days):\n"
        f"{memory_layers}\n\n"
        "Existing memory (MUST NOT duplicate or paraphrase):\n"
        f"{existing_memory}\n\n"
        "Store guidance (positive examples / scope):\n"
        f"{what_to_store}\n\n"
        "Do-not-store guidance (negative examples):\n"
        f"{what_not_to_store}\n\n"
        "TASK:\n"
        "- Extract up to 5 **new** memory candidates that comply with HARD RULES.\n"
        "- Return JSON only.\n"
    )

    try:
        if AI_PROVIDER == "bedrock":
            raw = _call_bedrock(system, user)
        else:
            raw = await _call_grok(system, user)
        logging.info("[memory_mcp] model returned chars=%d", len(raw))
        payload = _extract_json(raw)
        candidates = payload.get("candidates", [])

        logging.info(
            "[memory_mcp] raw candidates=%s",
            candidates,
        )
        cleaned: List[Dict[str, Any]] = []
        for cand in candidates:
            text = str(cand.get("text", "")).strip()
            category = str(cand.get("category", "")).strip()
            excerpt = str(cand.get("excerpt", "")).strip()
            ttl = cand.get("ttl_days")
            if not text or category not in ttl_map:
                continue
            if ttl is None:
                ttl = ttl_map.get(category)
            cleaned.append(
                {
                    "text": text,
                    "category": category,
                    "ttl_days": int(ttl) if ttl else ttl_map.get(category),
                    "excerpt": excerpt,
                    "extracted_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        logging.info(
            "[memory_mcp] cleaned candidates=%d",
            len(cleaned),
        )
        return {"candidates": cleaned}
    except Exception as exc:
        logging.error("[memory] extraction failed: %s", exc)
        return {"candidates": []}


@_tool("check_memory_conflict")
async def check_memory_conflict(
    candidate: Dict[str, Any],
    approved: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Decide if a candidate memory conflicts with approved memory.
    Returns: {"conflict": bool, "conflicting_ids": [..], "reason": "..."}
    """
    update_job_status("Tool: Memory Conflict Check", 75)
    system = (
        "You are a memory conflict checker. Decide if a new memory candidate "
        "conflicts with existing approved memories. A conflict means the two "
        "memories cannot both be true or would create incompatible instructions "
        "for the assistant. Return JSON only.\n"
        "Rules:\n"
        "- If two memories set different output formats (e.g., 'strict JSON' vs 'markdown'), this IS a conflict.\n"
        "- If two memories set different required sections (e.g., 'always include risks' vs 'never include risks'), this IS a conflict.\n"
        "- If two memories set different regions or defaults for the same domain (e.g., Terraform region), this IS a conflict.\n"
        "- If memories are compatible or additive, return conflict=false.\n"
        "Be conservative: when in doubt, mark conflict=true and explain."
    )
    user = (
        "Candidate:\n"
        f"{json.dumps(candidate, ensure_ascii=False)}\n\n"
        "Approved:\n"
        f"{json.dumps(approved, ensure_ascii=False)}\n\n"
        "Return JSON only in this schema:\n"
        "{\n"
        '  "conflict": true|false,\n'
        '  "conflicting_ids": ["id1","id2"],\n'
        '  "reason": "short explanation"\n'
        "}\n"
    )

    try:
        if AI_PROVIDER == "bedrock":
            raw = _call_bedrock(system, user)
        else:
            raw = await _call_grok(system, user)
        payload = _extract_json(raw)
        conflict = bool(payload.get("conflict"))
        conflicting_ids = payload.get("conflicting_ids") or []
        if not isinstance(conflicting_ids, list):
            conflicting_ids = []
        reason = str(payload.get("reason", "")).strip()
        return {"conflict": conflict, "conflicting_ids": conflicting_ids, "reason": reason}
    except Exception as exc:
        logging.error("[memory] conflict check failed: %s", exc)
        return {"conflict": False, "conflicting_ids": [], "reason": ""}


if __name__ == "__main__":
    try:
        mcp.run(transport="stdio")
    except TypeError:
        mcp.run()
