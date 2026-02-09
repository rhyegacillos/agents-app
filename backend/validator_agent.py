import json
import logging
import os
from typing import Any, Dict, List, Optional

import boto3
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

logger = logging.getLogger(__name__)

GROK_API_KEY = os.getenv("GROK_API_KEY", "").strip()
GROK_API_URL = os.getenv("GROK_API_URL", "https://api.x.ai/v1").strip()
GROK_MODEL_ID = os.getenv("GROK_MODEL_ID", "grok-4-1-fast").strip()
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0").strip()
DEFAULT_AWS_REGION = os.getenv("DEFAULT_AWS_REGION", "us-east-1").strip()

bedrock_client = boto3.client(
    service_name="bedrock-runtime",
    region_name=DEFAULT_AWS_REGION or "us-east-1",
)


def _extract_json_object(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


def build_memory_validator_instructions(approved: List[Dict[str, Any]]) -> str:
    lines = [
        "You are a response compliance validator.",
        "Use ONLY the Approved Memory below as the criteria for compliance.",
        "Approved Memory:",
    ]
    for item in approved:
        text = str(item.get("text", "")).strip()
        if text:
            lines.append(f"- {text}")
    lines.append(
        "Return JSON only: "
        '{"compliant": true|false, "reason": "short", "fix_instructions": "short"}'
    )
    return "\n".join(lines)


async def validate_memory_compliance_grok(
    approved: List[Dict[str, Any]],
    user_message: str,
    assistant_response: str,
) -> Dict[str, Any]:
    logger.info(
        "[memory_validator] grok start model=%s approved=%d user_chars=%d response_chars=%d",
        GROK_MODEL_ID,
        len(approved),
        len(user_message or ""),
        len(assistant_response or ""),
    )
    system = build_memory_validator_instructions(approved)
    user = (
        "User message:\n"
        f"{user_message}\n\n"
        "Assistant response:\n"
        f"{assistant_response}\n\n"
        "Return JSON only."
    )
    client = AsyncOpenAI(api_key=GROK_API_KEY, base_url=GROK_API_URL)
    response = await client.chat.completions.create(
        model=GROK_MODEL_ID,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.0,
        max_tokens=500,
    )
    raw = response.choices[0].message.content or ""
    payload = _extract_json_object(raw) or {}
    result = {
        "compliant": bool(payload.get("compliant")),
        "reason": str(payload.get("reason", "")).strip(),
        "fix_instructions": str(payload.get("fix_instructions", "")).strip(),
    }
    logger.info(
        "[memory_validator] grok done compliant=%s reason=%s",
        result["compliant"],
        result["reason"][:200],
    )
    return result


def validate_memory_compliance_bedrock(
    approved: List[Dict[str, Any]],
    user_message: str,
    assistant_response: str,
) -> Dict[str, Any]:
    logger.info(
        "[memory_validator] bedrock start model=%s approved=%d user_chars=%d response_chars=%d",
        BEDROCK_MODEL_ID,
        len(approved),
        len(user_message or ""),
        len(assistant_response or ""),
    )
    system = build_memory_validator_instructions(approved)
    user = (
        "User message:\n"
        f"{user_message}\n\n"
        "Assistant response:\n"
        f"{assistant_response}\n\n"
        "Return JSON only."
    )
    response = bedrock_client.converse(
        modelId=BEDROCK_MODEL_ID,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user}]}],
        inferenceConfig={"maxTokens": 500, "temperature": 0.0, "topP": 0.9},
    )
    raw = response["output"]["message"]["content"][0]["text"]
    payload = _extract_json_object(raw) or {}
    result = {
        "compliant": bool(payload.get("compliant")),
        "reason": str(payload.get("reason", "")).strip(),
        "fix_instructions": str(payload.get("fix_instructions", "")).strip(),
    }
    logger.info(
        "[memory_validator] bedrock done compliant=%s reason=%s",
        result["compliant"],
        result["reason"][:200],
    )
    return result
