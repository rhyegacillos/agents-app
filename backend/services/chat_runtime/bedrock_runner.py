import logging
from typing import Any, Dict, List, Tuple

from botocore.exceptions import ClientError
from fastapi import HTTPException

from services.bedrock_tools import run_bedrock_with_tools
from validator_agent import validate_memory_compliance_bedrock


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
    history_text: str,
    user_message: str,
    mcp_specs: List[Dict[str, Any]],
    approved_memory: List[Dict[str, Any]],
) -> Tuple[str, int]:
    candidates = _model_candidates(bedrock_model_id, default_aws_region)
    if not candidates:
        raise HTTPException(status_code=500, detail="BEDROCK_MODEL_ID is not configured")

    for model_id in candidates:
        try:
            total_llm_tokens = 0
            output, tokens_used = await run_bedrock_with_tools(
                bedrock_client=bedrock_client,
                model_id=model_id,
                system_text=system_text,
                user_text=history_text,
                mcp_specs=mcp_specs,
                inference_config={"maxTokens": 2000, "temperature": 0.7, "topP": 0.9},
            )
            total_llm_tokens += tokens_used
            if approved_memory:
                logging.info("[memory_validator] running (approved=%d)", len(approved_memory))
                verdict = validate_memory_compliance_bedrock(approved_memory, user_message, output)
                if not verdict.get("compliant"):
                    fix = verdict.get("fix_instructions", "")
                    system = system_text + "\n\nYou must revise your response to comply with Approved Memory."
                    if fix:
                        system += f"\nFix instructions: {fix}"
                    user_text = history_text + "\n\nRevise your response to comply with Approved Memory."
                    if fix:
                        user_text += f"\nFix instructions: {fix}"
                    output, tokens_used = await run_bedrock_with_tools(
                        bedrock_client=bedrock_client,
                        model_id=model_id,
                        system_text=system,
                        user_text=user_text,
                        mcp_specs=mcp_specs,
                        inference_config={"maxTokens": 2000, "temperature": 0.0, "topP": 0.9},
                    )
                    total_llm_tokens += tokens_used
            else:
                logging.info("[memory_validator] skipped (no approved memory)")
            return output, total_llm_tokens
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
