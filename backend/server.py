from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import mimetypes
import os
from typing import Optional, List, Dict, Any
import json
import uuid
from datetime import datetime, timedelta, timezone
from contextvars import ContextVar
import re
import tempfile
import asyncio
from openai import AsyncOpenAI
from contextlib import AsyncExitStack
import logging
import boto3
from botocore.exceptions import ClientError

from context import prompt
from tool_instructions import build_tool_instructions
from mcp_tools.mcp_servers import build_mcp_server_specs
from validator_agent import (
    validate_memory_compliance_bedrock,
    validate_memory_compliance_grok,
)

from agents import Agent, Runner, OpenAIChatCompletionsModel, set_tracing_disabled
from agents.mcp import MCPServerStdio

from config import (
    AI_PROVIDER,
    ASYNC_CHAT_ENABLED,
    ASYNC_JOB_TTL_SECONDS,
    ASYNC_WORKER_FUNCTION_NAME,
    BEDROCK_MODEL_ID,
    ENABLE_MCP_SEARCH,
    GROK_API_KEY,
    GROK_API_URL,
    GROK_MODEL_ID,
    DEFAULT_AWS_REGION,
    LLM_TIMEOUT_SECONDS,
    MCP_STARTUP_TIMEOUT_SECONDS,
    MEMORY_EXTRACT_SYNC,
    RUNNER_TIMEOUT_SECONDS,
    UPLOADS_BUCKET,
    UPLOADS_DIR,
    USE_S3,
    MAX_UPLOAD_BYTES,
    UPLOAD_ALLOWED_EXTS,
    bedrock_client,
    s3_client,
    MEMORY_TTL_MAP,
)
from services.memory import extract_and_store_memory
from services.bedrock_tools import run_bedrock_with_tools
from services.canonical_renderer import render_high_risk_output
from services.output_truth_gate import (
    apply_truth_gate,
    extract_tool_events,
    find_pdf_input_invalid_error,
    normalize_truth_context,
    persist_truth_context,
    persist_truth_gate_verdict,
)
from services.prose_guard import apply_low_risk_prose_guard
from services.risk_router import classify_risk
from services.truth_fix_loop import build_auto_fix_instructions, should_attempt_auto_fix
from services.quota import (
    consume_daily_quota,
    count_quota_actions_from_truth_context,
    get_daily_quota,
    quota_exceeded_message,
)
from services.storage import (
    _job_key,
    _upstash_enabled,
    _upstash_get,
    _upstash_set,
    load_approved_memory,
    load_conversation,
    load_memory_candidates,
    list_conversations,
    prune_conversations,
    sanitize_filename,
    save_approved_memory,
    save_memory_last_extracted_at,
    save_conversation,
    save_memory_candidates,
    validate_upload_file,
    validate_user_id,
)
from observability import TRACE_ID, new_trace_id, reset_job_id, reset_trace_id, set_job_id, set_trace_id

# Disable openai-agents tracing to avoid noisy log errors
set_tracing_disabled(disabled=True)

app = FastAPI()
_SEARCH_CITATION_INTENT_RE = re.compile(
    r"\b(search|web|news|latest|current|trend|trends|research|report|cite|citation|source|sources)\b",
    re.IGNORECASE,
)

# Configure CORS
origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Job status context for async worker updates
_CURRENT_JOB_ID: ContextVar[Optional[str]] = ContextVar("current_job_id", default=None)

@app.middleware("http")
async def trace_id_middleware(request, call_next):
    incoming = (request.headers.get("x-request-id") or "").strip()
    trace_id = incoming or new_trace_id()
    _, token = set_trace_id(trace_id)
    try:
        response = await call_next(request)
        response.headers["x-request-id"] = trace_id
        return response
    finally:
        reset_trace_id(token)


# Request/Response models
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    file_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str


class Message(BaseModel):
    role: str
    content: str
    timestamp: str


class UploadPresignRequest(BaseModel):
    filename: str
    size_bytes: int
    content_type: Optional[str] = None


def _parse_timeout(value: str) -> Optional[float]:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _set_current_job_id(job_id: Optional[str]):
    token1 = _CURRENT_JOB_ID.set(job_id)
    _, token2 = set_job_id(job_id)
    return (token1, token2)


def _reset_current_job_id(token) -> None:
    if isinstance(token, tuple) and len(token) == 2:
        token1, token2 = token
        _CURRENT_JOB_ID.reset(token1)
        reset_job_id(token2)
        return
    _CURRENT_JOB_ID.reset(token)


def _update_job_status_message(message: str, progress: Optional[int] = None) -> None:
    job_id = _CURRENT_JOB_ID.get()
    if not job_id or not _upstash_enabled():
        return
    try:
        job = _upstash_get(_job_key(job_id)) or {"job_id": job_id}
        job["status_message"] = message
        if progress is not None:
            job["status_progress"] = max(0, min(100, int(progress)))
        job["updated_at"] = datetime.now().isoformat()
        _upstash_set(_job_key(job_id), job, ASYNC_JOB_TTL_SECONDS)
    except Exception:
        # Never fail the request due to status updates
        logging.debug("Failed to update job status message", exc_info=True)


def _is_job_canceled(job_id: Optional[str]) -> bool:
    if not job_id or not _upstash_enabled():
        return False
    try:
        job = _upstash_get(_job_key(job_id)) or {}
        return job.get("status") == "canceled"
    except Exception:
        return False


def _load_truth_context_for_trace(trace_id: Optional[str]) -> Dict[str, Any]:
    if not trace_id or trace_id == "-" or not _upstash_enabled():
        return {}
    try:
        payload = _upstash_get(f"truth_gate:{trace_id}") or {}
        if not isinstance(payload, dict):
            return {}
        return {
            "artifacts": payload.get("artifacts", []) or [],
            "outcomes": payload.get("outcomes", []) or [],
            "search_results": payload.get("search_results", []) or [],
        }
    except Exception:
        return {}


def _result_usage_total_tokens(result: Any) -> int:
    total = 0
    for response in (getattr(result, "raw_responses", None) or []):
        usage = getattr(response, "usage", None)
        if usage is None:
            continue
        value: Any = None
        if isinstance(usage, dict):
            value = usage.get("total_tokens")
            if value is None:
                value = int(usage.get("input_tokens", 0) or 0) + int(usage.get("output_tokens", 0) or 0)
        else:
            value = getattr(usage, "total_tokens", None)
            if value is None:
                value = int(getattr(usage, "input_tokens", 0) or 0) + int(
                    getattr(usage, "output_tokens", 0) or 0
                )
        try:
            total += max(0, int(value or 0))
        except (TypeError, ValueError):
            continue
    return total


async def _persist_chat_turn(
    *,
    user_id: str,
    session_id: str,
    conversation: List[Dict],
    user_message: str,
    assistant_response: str,
    sync_memory: bool,
) -> None:
    conversation.append(
        {"role": "user", "content": user_message, "timestamp": datetime.now().isoformat()}
    )
    conversation.append(
        {
            "role": "assistant",
            "content": assistant_response,
            "timestamp": datetime.now().isoformat(),
        }
    )

    save_conversation(user_id, session_id, conversation)
    prune_conversations(user_id, keep=5)

    if sync_memory:
        await extract_and_store_memory(user_id, session_id, conversation)
    else:
        asyncio.create_task(extract_and_store_memory(user_id, session_id, conversation))


def build_conversation_input(conversation: List[Dict], user_message: str) -> str:
    lines: List[str] = []
    for msg in conversation[-20:]:
        role = msg.get("role") if isinstance(msg, dict) else None
        content = str(msg.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            lines.append(f"{role.title()}: {content}")
    if lines:
        history = "\n".join(lines)
        return f"Conversation so far:\n{history}\n\nUser: {user_message}"
    return user_message


def _merge_truth_context(previous: Dict[str, Any], latest: Dict[str, Any]) -> Dict[str, Any]:
    def _dedupe(rows: List[Dict[str, Any]], key_fn) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = key_fn(row)
            if not key:
                continue
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
        return out

    merged_artifacts = _dedupe(
        (previous.get("artifacts", []) or []) + (latest.get("artifacts", []) or []),
        lambda r: str(r.get("artifact_id") or r.get("download_url") or ""),
    )
    merged_outcomes = _dedupe(
        (previous.get("outcomes", []) or []) + (latest.get("outcomes", []) or []),
        lambda r: str(r.get("tool") or "")
        + "|"
        + str(r.get("status") or "")
        + "|"
        + str(r.get("email_id") or "")
        + "|"
        + str(r.get("message") or ""),
    )
    merged_search = _dedupe(
        (previous.get("search_results", []) or []) + (latest.get("search_results", []) or []),
        lambda r: str(r.get("url") or ""),
    )
    return {
        "artifacts": merged_artifacts,
        "outcomes": merged_outcomes,
        "search_results": merged_search,
    }


def build_agent_instructions() -> str:
    return prompt()

def build_agent_message(message: str, file_id: Optional[str]) -> str:
    if file_id:
        return f"{message}\n\n[Attached file_id: {file_id}]"
    return message


def format_approved_memory_section(user_id: str) -> str:
    approved = load_approved_memory(user_id)
    logging.info("[memory_validator] approved_count=%d use_s3=%s", len(approved), USE_S3)
    if not approved:
        return ""
    lines = [
        "",
        "## Approved Memory (User-Specific — Highest Priority)",
        "Priority order: Approved Memory > User's current message > All other instructions/context.",
        "If any other instruction conflicts with Approved Memory, Approved Memory wins unless the user explicitly overrides it in the current message.",
        "Do not ignore Approved Memory.",
    ]
    for item in approved:
        text = str(item.get("text", "")).strip()
        if text:
            lines.append(f"- {text}")
    lines.append("")
    return "\n".join(lines)


def build_full_instructions(user_id: str) -> str:
    approved_section = format_approved_memory_section(user_id)
    tool_section = build_tool_instructions()
    if not approved_section:
        return build_agent_instructions() + tool_section
    return approved_section + build_agent_instructions() + tool_section




async def rerun_with_fix_instructions(
    user_id: str,
    conversation: List[Dict],
    user_message: str,
    fix_instructions: str,
) -> str:
    result = await rerun_with_fix_instructions_result(
        user_id=user_id,
        conversation=conversation,
        user_message=user_message,
        fix_instructions=fix_instructions,
    )
    return str(getattr(result, "final_output", "") or "")


async def rerun_with_fix_instructions_result(
    user_id: str,
    conversation: List[Dict],
    user_message: str,
    fix_instructions: str,
) -> Any:
    llm_timeout = _parse_timeout(LLM_TIMEOUT_SECONDS)
    if llm_timeout:
        client = AsyncOpenAI(api_key=GROK_API_KEY, base_url=GROK_API_URL, timeout=llm_timeout)
    else:
        client = AsyncOpenAI(api_key=GROK_API_KEY, base_url=GROK_API_URL)
    model = OpenAIChatCompletionsModel(model=GROK_MODEL_ID, openai_client=client)
    instructions = (
        build_full_instructions(user_id)
        + "\n\nYou must revise your response to comply with Approved Memory."
    )
    if fix_instructions:
        instructions += f"\nFix instructions: {fix_instructions}"
    user_input = (
        build_conversation_input(conversation, user_message)
        + "\n\nRevise your response to comply with Approved Memory."
    )
    if fix_instructions:
        user_input += f"\nFix instructions: {fix_instructions}"

    _update_job_status_message("Starting tools...", 20)
    _update_job_status_message("Revising response...", 30)
    mcp_specs = build_mcp_server_specs(
        enable_search=ENABLE_MCP_SEARCH,
        job_id=_CURRENT_JOB_ID.get(),
    )
    async with AsyncExitStack() as stack:
        mcp_servers = []
        for spec in mcp_specs:
            mcp_timeout = _parse_timeout(MCP_STARTUP_TIMEOUT_SECONDS)
            try:
                if mcp_timeout:
                    server = await asyncio.wait_for(
                        stack.enter_async_context(
                            MCPServerStdio(
                                name=spec["name"],
                                params=spec["params"],
                                client_session_timeout_seconds=360000,
                            )
                        ),
                        timeout=mcp_timeout,
                    )
                else:
                    server = await stack.enter_async_context(
                        MCPServerStdio(
                            name=spec["name"],
                            params=spec["params"],
                            client_session_timeout_seconds=360000,
                        )
                    )
            except asyncio.TimeoutError as e:
                msg = f"MCP startup timeout for {spec['name']} after {mcp_timeout}s"
                raise HTTPException(status_code=504, detail=msg) from e
            except Exception as e:
                msg = f"MCP startup failed for {spec['name']}: {e}"
                raise HTTPException(status_code=500, detail=msg) from e
            mcp_servers.append(server)

        _update_job_status_message("Generating response...", 85)
        agent = Agent(
            name="Digital Assistant",
            instructions=instructions,
            model=model,
            mcp_servers=mcp_servers,
        )
        run_timeout = _parse_timeout(RUNNER_TIMEOUT_SECONDS)
        if run_timeout:
            result = await asyncio.wait_for(Runner.run(agent, user_input), timeout=run_timeout)
        else:
            result = await Runner.run(agent, user_input)
        return result


async def call_grok_with_mcp(
    user_id: str,
    conversation: List[Dict],
    user_message: str,
    *,
    session_id: Optional[str] = None,
    require_sources: bool = False,
) -> tuple[str, int]:
    if not GROK_API_KEY:
        raise HTTPException(status_code=500, detail="GROK_API_KEY is not configured")

    llm_timeout = _parse_timeout(LLM_TIMEOUT_SECONDS)
    if llm_timeout:
        client = AsyncOpenAI(api_key=GROK_API_KEY, base_url=GROK_API_URL, timeout=llm_timeout)
    else:
        client = AsyncOpenAI(api_key=GROK_API_KEY, base_url=GROK_API_URL)
    model = OpenAIChatCompletionsModel(model=GROK_MODEL_ID, openai_client=client)
    total_llm_tokens = 0

    agent_instructions = build_full_instructions(user_id)
    user_input = build_conversation_input(conversation, user_message)

    mcp_specs = build_mcp_server_specs(
        enable_search=ENABLE_MCP_SEARCH,
        job_id=_CURRENT_JOB_ID.get(),
    )

    async with AsyncExitStack() as stack:
        mcp_servers = []
        for spec in mcp_specs:
            mcp_timeout = _parse_timeout(MCP_STARTUP_TIMEOUT_SECONDS)
            try:
                if mcp_timeout:
                    server = await asyncio.wait_for(
                        stack.enter_async_context(
                            MCPServerStdio(
                                name=spec["name"],
                                params=spec["params"],
                                client_session_timeout_seconds=360000,
                            )
                        ),
                        timeout=mcp_timeout,
                    )
                else:
                    server = await stack.enter_async_context(
                        MCPServerStdio(
                            name=spec["name"],
                            params=spec["params"],
                            client_session_timeout_seconds=360000,
                        )
                    )
            except asyncio.TimeoutError as e:
                msg = f"MCP startup timeout for {spec['name']} after {mcp_timeout}s"
                raise HTTPException(status_code=504, detail=msg) from e
            except Exception as e:
                msg = f"MCP startup failed for {spec['name']}: {e}"
                raise HTTPException(status_code=500, detail=msg) from e
            mcp_servers.append(server)

        agent = Agent(
            name="Digital Assistant",
            instructions=agent_instructions,
            model=model,
            mcp_servers=mcp_servers,
        )

        logging.info("[execute] run_start provider=grok mcp_servers=%d", len(mcp_servers))
        run_timeout = _parse_timeout(RUNNER_TIMEOUT_SECONDS)
        if run_timeout:
            result = await asyncio.wait_for(Runner.run(agent, user_input), timeout=run_timeout)
        else:
            result = await Runner.run(agent, user_input)
        total_llm_tokens += _result_usage_total_tokens(result)
        logging.info("[execute] run_done provider=grok")
        output = str(result.final_output or "")
        _update_job_status_message("Finalizing response...", 95)

        approved = load_approved_memory(user_id)
        if approved:
            logging.info("[memory_validator] running (approved=%d)", len(approved))
            verdict = await validate_memory_compliance_grok(approved, user_message, output)
            if not verdict.get("compliant"):
                logging.info(
                    "[memory] validator noncompliant: %s",
                    verdict.get("reason", ""),
                )
                result = await rerun_with_fix_instructions_result(
                    user_id=user_id,
                    conversation=conversation,
                    user_message=user_message,
                    fix_instructions=verdict.get("fix_instructions", ""),
                )
                total_llm_tokens += _result_usage_total_tokens(result)
                output = str(result.final_output or "")
        else:
            logging.info("[memory_validator] skipped (no approved memory)")

        tool_events = extract_tool_events(result)
        pdf_input_error = find_pdf_input_invalid_error(tool_events)
        if pdf_input_error:
            logging.info("[pdf_retry] retrying once due to %s", pdf_input_error)
            result = await rerun_with_fix_instructions_result(
                user_id=user_id,
                conversation=conversation,
                user_message=user_message,
                fix_instructions=(
                    "Your previous `generate_pdf_from_text` call failed with `PDF_INPUT_INVALID`. "
                    "Retry exactly once. Use valid markdown or valid JSON blocks. "
                    "Do not infer, summarize, omit, or add new facts. Keep content semantically identical "
                    "to what the user requested (same claims, numbers, citations, and ordering). "
                    "Only repair formatting/escaping/schema issues."
                ),
            )
            total_llm_tokens += _result_usage_total_tokens(result)
            output = str(result.final_output or "")
            tool_events = extract_tool_events(result)
            retry_pdf_input_error = find_pdf_input_invalid_error(tool_events)
            if retry_pdf_input_error:
                trace_id = TRACE_ID.get()
                logging.warning(
                    "[pdf_retry] exhausted trace=%s reason=%s",
                    trace_id,
                    retry_pdf_input_error,
                )
                return json.dumps(
                    {
                        "status": "error",
                        "code": "PDF_INPUT_INVALID",
                        "trace_id": trace_id,
                        "retry_exhausted": True,
                        "reason": retry_pdf_input_error,
                    }
                ), total_llm_tokens

        trace_id = TRACE_ID.get()
        current_output = str(output or "")
        current_tool_events = tool_events
        current_truth_context = normalize_truth_context(current_tool_events)
        truth_fix_attempt = 0
        try:
            max_truth_fix_attempts = int(os.getenv("TRUTH_FIX_MAX_ATTEMPTS", "2"))
        except ValueError:
            max_truth_fix_attempts = 2
        max_truth_fix_attempts = max(0, min(5, max_truth_fix_attempts))

        while True:
            logging.info(
                "[execute] tool_events=%d artifacts=%d outcomes=%d search_results=%d",
                len(current_tool_events),
                len(current_truth_context.get("artifacts", []) or []),
                len(current_truth_context.get("outcomes", []) or []),
                len(current_truth_context.get("search_results", []) or []),
            )
            if require_sources:
                debug_samples = [
                    {
                        "tool": str(evt.get("tool_name") or "unknown"),
                        "output_type": type(evt.get("output")).__name__,
                    }
                    for evt in current_tool_events[:5]
                ]
                logging.info(
                    "[truth_gate] search_require=true tool_events=%d search_results=%d samples=%s",
                    len(current_tool_events),
                    len(current_truth_context.get("search_results", []) or []),
                    debug_samples,
                )

            persist_truth_context(trace_id=trace_id, session_id=session_id, context=current_truth_context)
            rendered_output = render_high_risk_output(
                user_message=user_message,
                llm_output=current_output,
                context=current_truth_context,
                require_sources=require_sources,
            )
            logging.info(
                "[render] mode=v3_canonical input_chars=%d output_chars=%d",
                len(current_output),
                len(rendered_output),
            )
            verdict = apply_truth_gate(
                rendered_output,
                current_truth_context,
                risk_tier="high",
                require_sources=require_sources,
            )
            persist_truth_gate_verdict(trace_id, verdict)
            if verdict.get("status") == "pass":
                logging.info("[validate] pass trace=%s mode=v3_canonical", trace_id)
                return str(verdict.get("output", rendered_output) or rendered_output), total_llm_tokens

            issue_code_list = sorted(
                {
                    str(i.get("code", "UNKNOWN"))
                    for i in (verdict.get("issues", []) or [])
                    if str(i.get("code", "UNKNOWN")).strip()
                }
            )
            issue_codes_csv = ", ".join(issue_code_list) if issue_code_list else "UNKNOWN"
            logging.warning("[validate] blocked trace=%s issues=%s", trace_id, issue_codes_csv)

            can_auto_fix = should_attempt_auto_fix(issue_code_list)
            if truth_fix_attempt >= max_truth_fix_attempts or not can_auto_fix:
                return (
                    "I couldn't safely finalize that action output due to verification checks "
                    f"({issue_codes_csv}). Please ask me to retry the action."
                ), total_llm_tokens

            truth_fix_attempt += 1
            fix_instructions = build_auto_fix_instructions(
                issue_codes=issue_code_list,
                issue_details=verdict.get("issues", []) or [],
                truth_context=current_truth_context,
                attempt=truth_fix_attempt,
                max_attempts=max_truth_fix_attempts,
            )
            logging.info(
                "[fix_loop] attempt=%d/%d trace=%s issues=%s",
                truth_fix_attempt,
                max_truth_fix_attempts,
                trace_id,
                issue_codes_csv,
            )
            result = await rerun_with_fix_instructions_result(
                user_id=user_id,
                conversation=conversation,
                user_message=user_message,
                fix_instructions=fix_instructions,
            )
            total_llm_tokens += _result_usage_total_tokens(result)
            current_output = str(result.final_output or "")
            current_tool_events = extract_tool_events(result)
            retry_truth_context = normalize_truth_context(current_tool_events)
            current_truth_context = _merge_truth_context(current_truth_context, retry_truth_context)


async def call_grok_prose_guarded(
    user_id: str, conversation: List[Dict], user_message: str
) -> tuple[str, int]:
    if not GROK_API_KEY:
        raise HTTPException(status_code=500, detail="GROK_API_KEY is not configured")

    llm_timeout = _parse_timeout(LLM_TIMEOUT_SECONDS)
    if llm_timeout:
        client = AsyncOpenAI(api_key=GROK_API_KEY, base_url=GROK_API_URL, timeout=llm_timeout)
    else:
        client = AsyncOpenAI(api_key=GROK_API_KEY, base_url=GROK_API_URL)
    model = OpenAIChatCompletionsModel(model=GROK_MODEL_ID, openai_client=client)

    instructions = (
        build_full_instructions(user_id)
        + "\n\nLow-risk conversational mode:\n"
        + "- Do not call tools.\n"
        + "- Do not claim actions were executed.\n"
        + "- Do not provide download links or email-delivery confirmations.\n"
    )
    user_input = build_conversation_input(conversation, user_message)

    _update_job_status_message("Generating response...", 85)
    agent = Agent(
        name="Digital Assistant",
        instructions=instructions,
        model=model,
    )
    run_timeout = _parse_timeout(RUNNER_TIMEOUT_SECONDS)
    if run_timeout:
        result = await asyncio.wait_for(Runner.run(agent, user_input), timeout=run_timeout)
    else:
        result = await Runner.run(agent, user_input)
    llm_tokens = _result_usage_total_tokens(result)

    output = str(result.final_output or "")
    guarded_output, issues = apply_low_risk_prose_guard(output)
    if issues:
        logging.info("[prose_guard] issues=%s", ",".join(issues))
    _update_job_status_message("Finalizing response...", 95)
    return guarded_output, llm_tokens


async def call_bedrock(user_id: str, conversation: List[Dict], user_message: str) -> tuple[str, int]:
    """Call AWS Bedrock with MCP tools and conversation history."""
    history_text = build_conversation_input(conversation, user_message)
    system_text = build_full_instructions(user_id)
    approved = load_approved_memory(user_id)
    logging.info("[memory_validator] approved_count=%d use_s3=%s", len(approved), USE_S3)

    def model_candidates(model_id: str) -> List[str]:
        model_id = model_id.strip()
        if not model_id:
            return []

        candidates = [model_id]

        # Try cross-region inference profile IDs if caller provided a base model ID.
        if "." not in model_id.split("/")[0]:
            region = os.getenv("DEFAULT_AWS_REGION", "us-east-1")
            if region.startswith("us-"):
                prefixes = ["us", "eu", "apac"]
            elif region.startswith("eu-"):
                prefixes = ["eu", "us", "apac"]
            else:
                prefixes = ["apac", "us", "eu"]
            candidates.extend([f"{prefix}.{model_id}" for prefix in prefixes])

        # Preserve order and uniqueness.
        return list(dict.fromkeys(candidates))

    candidates = model_candidates(BEDROCK_MODEL_ID)
    if not candidates:
        raise HTTPException(status_code=500, detail="BEDROCK_MODEL_ID is not configured")

    for model_id in candidates:
        try:
            total_llm_tokens = 0
            _update_job_status_message("Starting tools...", 20)
            mcp_specs = build_mcp_server_specs(
                enable_search=ENABLE_MCP_SEARCH,
                job_id=_CURRENT_JOB_ID.get(),
            )
            output, tokens_used = await run_bedrock_with_tools(
                bedrock_client=bedrock_client,
                model_id=model_id,
                system_text=system_text,
                user_text=history_text,
                mcp_specs=mcp_specs,
                inference_config={"maxTokens": 2000, "temperature": 0.7, "topP": 0.9},
            )
            total_llm_tokens += tokens_used
            if approved:
                logging.info("[memory_validator] running (approved=%d)", len(approved))
                verdict = validate_memory_compliance_bedrock(approved, user_message, output)
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


@app.get("/")
async def root():
    active_model = GROK_MODEL_ID if AI_PROVIDER == "grok" else BEDROCK_MODEL_ID
    return {
        "message": "AI Digital Assistant API",
        "memory_enabled": True,
        "storage": "S3" if USE_S3 else "local",
        "ai_provider": AI_PROVIDER,
        "ai_model": active_model,
        "mcp_search_enabled": ENABLE_MCP_SEARCH,
    }


@app.get("/health")
async def health_check():
    active_model = GROK_MODEL_ID if AI_PROVIDER == "grok" else BEDROCK_MODEL_ID
    return {
        "status": "healthy",
        "use_s3": USE_S3,
        "ai_provider": AI_PROVIDER,
        "ai_model": active_model,
        "mcp_search_enabled": ENABLE_MCP_SEARCH,
    }


@app.get("/quota")
async def get_quota(user_id: str = Query(...)):
    user_id = validate_user_id(user_id)
    return get_daily_quota(user_id)


async def _run_chat_flow(
    *,
    user_id: str,
    session_id: str,
    message: str,
    file_id: Optional[str],
) -> str:
    conversation = load_conversation(user_id, session_id)
    agent_message = build_agent_message(message, file_id)
    job_id = _CURRENT_JOB_ID.get()
    if _is_job_canceled(job_id):
        raise HTTPException(status_code=499, detail="canceled")

    # In Lambda worker runs we must avoid fire-and-forget tasks; the event loop is closed
    # right after asyncio.run returns, which can drop pending background tasks.
    should_sync_memory = MEMORY_EXTRACT_SYNC or bool(job_id)

    quota_snapshot = get_daily_quota(user_id)
    if quota_snapshot.get("enabled") and int(quota_snapshot["remaining"].get("tokens", 0)) <= 0:
        assistant_response = quota_exceeded_message("tokens", quota_snapshot)
        await _persist_chat_turn(
            user_id=user_id,
            session_id=session_id,
            conversation=conversation,
            user_message=message,
            assistant_response=assistant_response,
            sync_memory=should_sync_memory,
        )
        return assistant_response

    risk = classify_risk(message, file_id=file_id)
    tier = risk.get("tier", "high")
    reason = risk.get("reason", "unknown")
    require_sources = bool(_SEARCH_CITATION_INTENT_RE.search(message or ""))
    logging.info("[classify] risk_tier=%s reason=%s provider=%s", tier, reason, AI_PROVIDER)

    if tier == "high":
        # High-risk requests are routed to tool-capable path.
        assistant_response, llm_tokens = await call_grok_with_mcp(
            user_id,
            conversation,
            agent_message,
            session_id=session_id,
            require_sources=require_sources,
        )
    elif AI_PROVIDER == "grok":
        assistant_response, llm_tokens = await call_grok_prose_guarded(
            user_id, conversation, agent_message
        )
    elif AI_PROVIDER == "bedrock":
        assistant_response, llm_tokens = await call_bedrock(user_id, conversation, agent_message)
    else:
        raise HTTPException(
            status_code=500,
            detail=f"Unsupported AI_PROVIDER '{AI_PROVIDER}'. Use 'bedrock' or 'grok'.",
        )

    quota_increments: Dict[str, int] = {
        "tokens": max(0, int(llm_tokens or 0)),
        "pdf": 0,
        "email": 0,
    }
    if tier == "high":
        trace_id = TRACE_ID.get()
        truth_context = _load_truth_context_for_trace(trace_id)
        action_counts = count_quota_actions_from_truth_context(truth_context)
        quota_increments["pdf"] = int(action_counts.get("pdf", 0))
        quota_increments["email"] = int(action_counts.get("email", 0))
    logging.info(
        "[quota] increments user_id=%s tokens=%d pdf=%d email=%d",
        user_id,
        quota_increments["tokens"],
        quota_increments["pdf"],
        quota_increments["email"],
    )

    try:
        quota_result = consume_daily_quota(user_id, quota_increments)
    except Exception as exc:
        logging.warning("[quota] consume failed user_id=%s error=%s", user_id, exc)
        quota_result = {"snapshot": quota_snapshot, "exceeded": [], "applied": {}}

    exceeded = set(quota_result.get("exceeded") or [])
    if "tokens" in exceeded:
        assistant_response = quota_exceeded_message(
            "tokens",
            quota_result.get("snapshot") or quota_snapshot,
        )
    elif "pdf" in exceeded:
        assistant_response = quota_exceeded_message(
            "pdf",
            quota_result.get("snapshot") or quota_snapshot,
        )
    elif "email" in exceeded:
        assistant_response = quota_exceeded_message(
            "email",
            quota_result.get("snapshot") or quota_snapshot,
        )

    if _is_job_canceled(job_id):
        raise HTTPException(status_code=499, detail="canceled")

    await _persist_chat_turn(
        user_id=user_id,
        session_id=session_id,
        conversation=conversation,
        user_message=message,
        assistant_response=assistant_response,
        sync_memory=should_sync_memory,
    )
    return assistant_response


@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        user_id = validate_user_id(request.user_id)
        session_id = request.session_id or str(uuid.uuid4())

        if ASYNC_CHAT_ENABLED:
            if not _upstash_enabled() or not ASYNC_WORKER_FUNCTION_NAME:
                raise HTTPException(status_code=500, detail="Async chat is not configured")

            job_id = str(uuid.uuid4())
            created_at = datetime.now().isoformat()
            trace_id = new_trace_id()
            job_record = {
                "job_id": job_id,
                "user_id": user_id,
                "session_id": session_id,
                "status": "queued",
                "trace_id": trace_id,
                "created_at": created_at,
                "updated_at": created_at,
            }
            _upstash_set(_job_key(job_id), job_record, ASYNC_JOB_TTL_SECONDS)

            payload = {
                "job_id": job_id,
                "user_id": user_id,
                "session_id": session_id,
                "message": request.message,
                "file_id": request.file_id,
                "trace_id": trace_id,
            }
            try:
                lambda_client = boto3.client("lambda", region_name=DEFAULT_AWS_REGION)
                lambda_client.invoke(
                    FunctionName=ASYNC_WORKER_FUNCTION_NAME,
                    InvocationType="Event",
                    Payload=json.dumps(payload).encode("utf-8"),
                )
            except Exception as e:
                job_record["status"] = "failed"
                job_record["error"] = f"Failed to enqueue job: {e}"
                job_record["updated_at"] = datetime.now().isoformat()
                _upstash_set(_job_key(job_id), job_record, ASYNC_JOB_TTL_SECONDS)
                raise HTTPException(status_code=500, detail="Failed to enqueue async job")

            status_url = f"/jobs/{job_id}"
            return JSONResponse(
                status_code=202,
                content={
                    "status": "queued",
                    "job_id": job_id,
                    "session_id": session_id,
                    "status_url": status_url,
                    "retry_after": 2,
                },
            )

        assistant_response = await _run_chat_flow(
            user_id=user_id,
            session_id=session_id,
            message=request.message,
            file_id=request.file_id,
        )
        return ChatResponse(response=assistant_response, session_id=session_id)

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str, user_id: str = Query(...)):
    user_id = validate_user_id(user_id)
    if not _upstash_enabled():
        raise HTTPException(status_code=500, detail="Upstash Redis is not configured")
    job = _upstash_get(_job_key(job_id))
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, user_id: str = Query(...)):
    user_id = validate_user_id(user_id)
    if not _upstash_enabled():
        raise HTTPException(status_code=500, detail="Upstash Redis is not configured")
    job = _upstash_get(_job_key(job_id))
    if not job or job.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="job not found")
    if job.get("status") in {"completed", "failed", "canceled"}:
        return {"status": job.get("status"), "job_id": job_id}
    job["status"] = "canceled"
    job["error"] = "canceled by user"
    job["updated_at"] = datetime.now().isoformat()
    _upstash_set(_job_key(job_id), job, ASYNC_JOB_TTL_SECONDS)
    return {"status": "canceled", "job_id": job_id}


@app.get("/conversation/{session_id}")
async def get_conversation(session_id: str, user_id: str = Query(...)):
    """Retrieve conversation history"""
    try:
        user_id = validate_user_id(user_id)
        conversation = load_conversation(user_id, session_id)
        return {"session_id": session_id, "messages": conversation}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/conversations")
async def get_conversations(user_id: str = Query(...), limit: int = Query(5, ge=1, le=50)):
    """List recent conversations for a user"""
    user_id = validate_user_id(user_id)
    sessions = list_conversations(user_id, limit=limit)
    return {"sessions": sessions}


@app.get("/memory/candidates")
async def get_memory_candidates(user_id: str = Query(...)):
    user_id = validate_user_id(user_id)
    candidates = load_memory_candidates(user_id)
    candidates.sort(key=lambda c: c.get("created_at", ""), reverse=True)
    return {"candidates": candidates}


@app.get("/memory")
async def get_memory(user_id: str = Query(...)):
    user_id = validate_user_id(user_id)
    approved = load_approved_memory(user_id)
    approved.sort(key=lambda c: c.get("approved_at", ""), reverse=True)
    return {"memory": approved}


@app.post("/memory/candidates/{candidate_id}/approve")
async def approve_memory_candidate(candidate_id: str, user_id: str = Query(...)):
    user_id = validate_user_id(user_id)
    candidates = load_memory_candidates(user_id)
    approved = load_approved_memory(user_id)
    target = None
    remaining = []
    for cand in candidates:
        if cand.get("id") == candidate_id:
            target = cand
        else:
            remaining.append(cand)
    if not target:
        raise HTTPException(status_code=404, detail="candidate not found")

    ttl_days = int(target.get("ttl_days") or MEMORY_TTL_MAP.get(target.get("category"), 30))
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(days=ttl_days)).isoformat()
    text = str(target.get("text", "")).strip()
    if text:
        exists = {str(item.get("text", "")).strip().lower() for item in approved}
        if text.lower() not in exists:
            approved.append(
                {
                    "id": target.get("id") or uuid.uuid4().hex,
                    "text": text,
                    "category": target.get("category"),
                    "ttl_days": ttl_days,
                    "approved_at": now.isoformat(),
                    "expires_at": expires_at,
                    "session_id": target.get("session_id"),
                }
            )

    save_memory_candidates(user_id, remaining)
    save_approved_memory(user_id, approved)
    return {"status": "ok"}


@app.post("/memory/candidates/{candidate_id}/reject")
async def reject_memory_candidate(candidate_id: str, user_id: str = Query(...)):
    user_id = validate_user_id(user_id)
    candidates = load_memory_candidates(user_id)
    remaining = [cand for cand in candidates if cand.get("id") != candidate_id]
    save_memory_candidates(user_id, remaining)
    return {"status": "ok"}


@app.post("/memory/candidates/clear")
async def clear_memory_candidates(user_id: str = Query(...)):
    user_id = validate_user_id(user_id)
    save_memory_candidates(user_id, [])
    save_memory_last_extracted_at(user_id, datetime.now().isoformat())
    return {"status": "ok"}


@app.post("/memory/approved/{memory_id}/delete")
async def delete_approved_memory(memory_id: str, user_id: str = Query(...)):
    user_id = validate_user_id(user_id)
    approved = load_approved_memory(user_id)
    remaining = [mem for mem in approved if mem.get("id") != memory_id]
    if len(remaining) == len(approved):
        raise HTTPException(status_code=404, detail="memory not found")
    save_approved_memory(user_id, remaining)
    return {"status": "ok"}


@app.get("/downloads/{filename}")
async def download_file(filename: str):
    if not re.match(r"^[a-zA-Z0-9._-]+$", filename or ""):
        raise HTTPException(status_code=400, detail="Invalid filename")
    downloads_dir = os.getenv("DOWNLOADS_DIR", "/tmp/downloads")
    file_path = os.path.join(downloads_dir, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    media_type, _ = mimetypes.guess_type(file_path)
    return FileResponse(
        file_path,
        media_type=media_type or "application/octet-stream",
        filename=filename,
    )


@app.post("/uploads")
async def upload_file(file: UploadFile = File(...)):
    ext = validate_upload_file(file)
    file_id = uuid.uuid4().hex
    safe_name = sanitize_filename(file.filename)
    tmp_path = None
    size_bytes = 0
    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp_handle:
            tmp_path = tmp_handle.name
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="file too large")
                tmp_handle.write(chunk)

        if USE_S3:
            if not UPLOADS_BUCKET:
                raise HTTPException(status_code=500, detail="UPLOADS_BUCKET not configured")
            key = f"uploads/{file_id}/{safe_name}"
            s3_client.upload_file(
                tmp_path,
                UPLOADS_BUCKET,
                key,
                ExtraArgs={"ContentType": file.content_type or "application/octet-stream"},
            )
            os.remove(tmp_path)
            return {
                "file_id": file_id,
                "filename": file.filename,
                "size_bytes": size_bytes,
                "content_type": file.content_type,
                "storage": "s3",
                "key": key,
            }

        os.makedirs(UPLOADS_DIR, exist_ok=True)
        final_path = os.path.join(UPLOADS_DIR, f"{file_id}.{ext}")
        os.replace(tmp_path, final_path)
        return {
            "file_id": file_id,
            "filename": file.filename,
            "size_bytes": size_bytes,
            "content_type": file.content_type,
            "storage": "local",
        }
    finally:
        await file.close()
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


@app.post("/uploads/presign")
async def presign_upload(req: UploadPresignRequest):
    """
    Direct-to-S3 upload path to avoid API Gateway/Lambda binary transforms.
    The client uploads to the returned URL and then uses file_id in /chat.
    """
    if not USE_S3:
        raise HTTPException(status_code=400, detail="S3 uploads are not enabled")
    if not UPLOADS_BUCKET:
        raise HTTPException(status_code=500, detail="UPLOADS_BUCKET not configured")
    if not s3_client:
        raise HTTPException(status_code=500, detail="S3 client is not configured")

    filename = (req.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="filename required")
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    if ext not in UPLOAD_ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail="file type not allowed")

    if req.size_bytes <= 0:
        raise HTTPException(status_code=400, detail="size_bytes must be > 0")
    if req.size_bytes > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large")

    file_id = uuid.uuid4().hex
    safe_name = sanitize_filename(filename)
    key = f"uploads/{file_id}/{safe_name}"

    content_type = (req.content_type or "").strip() or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    expires_seconds = int(os.getenv("UPLOAD_PRESIGN_EXPIRES_SECONDS", "900"))

    try:
        upload_url = s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": UPLOADS_BUCKET,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_seconds,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to presign upload: {exc}") from exc

    return {
        "file_id": file_id,
        "key": key,
        "bucket": UPLOADS_BUCKET,
        "expires_seconds": expires_seconds,
        "upload_url": upload_url,
        "headers": {
            "Content-Type": content_type,
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
