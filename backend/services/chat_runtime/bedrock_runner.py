import logging
from typing import Any, Dict, List, Tuple

from botocore.exceptions import ClientError
from fastapi import HTTPException

from services.bedrock_tools import run_bedrock_with_tools
from services.chat_runtime.result_types import HighRiskChatResult


def _model_candidates(model_id: str, default_region: str) -> List[str]:
    model_id = model_id.strip()
    if not model_id:
        return []

    candidates = [model_id]

    # Try cross-region inference profile IDs if caller provided a base model ID.
    if "." not in model_id.split("/")[0]:
        region = default_region or "us-east-1"
        if region.startswith("us-"):
            prefixes = ["us", "eu", "apac"]
        elif region.startswith("eu-"):
            prefixes = ["eu", "us", "apac"]
        else:
            prefixes = ["apac", "us", "eu"]
        candidates.extend([f"{prefix}.{model_id}" for prefix in prefixes])

    # Preserve order and uniqueness.
    return list(dict.fromkeys(candidates))


async def run_bedrock_chat(
    *,
    bedrock_client: Any,
    bedrock_model_id: str,
    default_aws_region: str,
    system_text: str,
    user_text: str,
    mcp_specs: List[Dict[str, Any]],
    required_tool_names: List[str] | None = None,
) -> HighRiskChatResult:
    candidates = _model_candidates(bedrock_model_id, default_aws_region)
    if not candidates:
        raise HTTPException(status_code=500, detail="BEDROCK_MODEL_ID is not configured")

    for model_id in candidates:
        try:
            output, tokens_used, tool_events = await run_bedrock_with_tools(
                bedrock_client=bedrock_client,
                model_id=model_id,
                system_text=system_text,
                user_text=user_text,
                mcp_specs=mcp_specs,
                required_tool_names=required_tool_names,
                inference_config={"maxTokens": 2000, "temperature": 0.7, "topP": 0.9},
            )
            return HighRiskChatResult(
                output=output,
                tool_events=tool_events,
                llm_tokens=tokens_used,
            )
        except ClientError as e:
            error = e.response.get("Error", {})
            error_code = error.get("Code", "")
            error_message = error.get("Message", str(e))

            if error_code == "ValidationException":
                if "operation not allowed" in error_message.lower():
                    logging.warning(
                        "Bedrock rejected modelId '%s': %s",
                        model_id,
                        error_message,
                    )
                    continue
                logging.exception(
                    "Bedrock validation error for modelId '%s': %s",
                    model_id,
                    error_message,
                )
                raise HTTPException(status_code=400, detail=f"Bedrock validation error: {error_message}")

            if error_code == "AccessDeniedException":
                logging.exception(
                    "Bedrock access denied for modelId '%s': %s",
                    model_id,
                    error_message,
                )
                raise HTTPException(status_code=403, detail=f"Access denied to Bedrock model: {error_message}")

            logging.exception(
                "Bedrock error for modelId '%s': %s",
                model_id,
                error_message,
            )
            raise HTTPException(status_code=500, detail=f"Bedrock error: {error_message}")
        except Exception as e:
            logging.exception("Bedrock tool call failed for modelId '%s'", model_id)
            raise HTTPException(status_code=500, detail=f"Bedrock tool call failed: {e}")

    raise HTTPException(
        status_code=400,
        detail=(
            "Bedrock returned 'Operation not allowed' for all model IDs tried: "
            f"{', '.join(candidates)}. "
            "Enable model access for the selected model in this region or set BEDROCK_MODEL_ID "
            "to an allowed model/inference-profile ID."
        ),
    )


async def run_bedrock_prose(
    *,
    bedrock_client: Any,
    bedrock_model_id: str,
    default_aws_region: str,
    system_text: str,
    user_text: str,
) -> Tuple[str, int]:
    candidates = _model_candidates(bedrock_model_id, default_aws_region)
    if not candidates:
        raise HTTPException(status_code=500, detail="BEDROCK_MODEL_ID is not configured")

    for model_id in candidates:
        try:
            response = bedrock_client.converse(
                modelId=model_id,
                system=[{"text": system_text}],
                messages=[{"role": "user", "content": [{"text": user_text}]}],
                inferenceConfig={"maxTokens": 2000, "temperature": 0.7, "topP": 0.9},
            )
            usage = response.get("usage", {}) or {}
            try:
                tokens_used = int(
                    usage.get("totalTokens")
                    or usage.get("total_tokens")
                    or (
                        int(usage.get("inputTokens", 0) or 0)
                        + int(usage.get("outputTokens", 0) or 0)
                    )
                )
            except (TypeError, ValueError):
                tokens_used = 0
            content_blocks = response.get("output", {}).get("message", {}).get("content", []) or []
            parts: List[str] = []
            for block in content_blocks:
                if "text" in block:
                    parts.append(block.get("text") or "")
            return "".join(parts).strip(), tokens_used
        except ClientError as e:
            error = e.response.get("Error", {})
            error_code = error.get("Code", "")
            error_message = error.get("Message", str(e))

            if error_code == "ValidationException":
                if "operation not allowed" in error_message.lower():
                    logging.warning(
                        "Bedrock rejected modelId '%s': %s",
                        model_id,
                        error_message,
                    )
                    continue
                logging.exception(
                    "Bedrock validation error for modelId '%s': %s",
                    model_id,
                    error_message,
                )
                raise HTTPException(status_code=400, detail=f"Bedrock validation error: {error_message}")

            if error_code == "AccessDeniedException":
                logging.exception(
                    "Bedrock access denied for modelId '%s': %s",
                    model_id,
                    error_message,
                )
                raise HTTPException(status_code=403, detail=f"Access denied to Bedrock model: {error_message}")

            logging.exception(
                "Bedrock error for modelId '%s': %s",
                model_id,
                error_message,
            )
            raise HTTPException(status_code=500, detail=f"Bedrock error: {error_message}")
        except Exception as e:
            logging.exception("Bedrock prose call failed for modelId '%s'", model_id)
            raise HTTPException(status_code=500, detail=f"Bedrock error: {e}")

    raise HTTPException(
        status_code=400,
        detail=(
            "Bedrock returned 'Operation not allowed' for all model IDs tried: "
            f"{', '.join(candidates)}. "
            "Enable model access for the selected model in this region or set BEDROCK_MODEL_ID "
            "to an allowed model/inference-profile ID."
        ),
    )
