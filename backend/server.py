from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
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
import logging
import boto3

from context import prompt
from api.routers import chat_router, core_router, files_router, memory_router
from api.schemas import ChatRequest, ChatResponse, Message, UploadPresignRequest
from tool_instructions import build_tool_instructions
from mcp_tools.mcp_servers import build_mcp_server_specs

from agents import set_tracing_disabled

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
from services.prose_guard import apply_low_risk_prose_guard
from services.risk_router import classify_risk
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
from services.chat_runtime import (
    finalize_high_risk_response,
    run_bedrock_chat,
    run_grok_once,
    run_grok_with_mcp_once,
    usage_total_tokens,
)
from observability import (
    TRACE_ID,
    log_event,
    new_trace_id,
    now_local_iso,
    reset_job_id,
    reset_trace_id,
    set_job_id,
    set_trace_id,
)
from otel_observability import (
    get_tracer as get_otel_tracer,
    instrument_fastapi_app,
    record_current_span_exception,
    set_current_span_attributes,
)

# Disable openai-agents tracing to avoid noisy log errors
set_tracing_disabled(disabled=True)

app = FastAPI()
instrument_fastapi_app(app)
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
app.include_router(core_router)
app.include_router(chat_router)
app.include_router(memory_router)
app.include_router(files_router)

# Job status context for async worker updates
_CURRENT_JOB_ID: ContextVar[Optional[str]] = ContextVar("current_job_id", default=None)

@app.middleware("http")
async def trace_id_middleware(request, call_next):
    incoming = (request.headers.get("x-request-id") or "").strip()
    trace_id = incoming or new_trace_id()
    _, token = set_trace_id(trace_id)
    set_current_span_attributes({"trace_id": trace_id, "http.path": request.url.path})
    try:
        response = await call_next(request)
        response.headers["x-request-id"] = trace_id
        return response
    finally:
        reset_trace_id(token)


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
        job["updated_at"] = now_local_iso()
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
        {"role": "user", "content": user_message, "timestamp": now_local_iso()}
    )
    conversation.append(
        {
            "role": "assistant",
            "content": assistant_response,
            "timestamp": now_local_iso(),
        }
    )

    save_conversation(user_id, session_id, conversation)
    prune_conversations(user_id, keep=5)

    if sync_memory:
        await extract_and_store_memory(user_id, session_id, conversation)
    else:
        asyncio.create_task(extract_and_store_memory(user_id, session_id, conversation))


def _should_sync_memory_extraction(job_id: Optional[str]) -> bool:
    # In Lambda worker runs we must avoid fire-and-forget tasks; the event loop is
    # closed right after asyncio.run returns, which can drop pending background tasks.
    return MEMORY_EXTRACT_SYNC or bool(job_id)


async def _generate_response_for_risk(
    *,
    user_id: str,
    conversation: List[Dict],
    agent_message: str,
    session_id: str,
    tier: str,
    require_sources: bool,
) -> tuple[str, int]:
    if tier == "high":
        return await call_grok_with_mcp(
            user_id,
            conversation,
            agent_message,
            session_id=session_id,
            require_sources=require_sources,
        )
    if AI_PROVIDER == "grok":
        return await call_grok_prose_guarded(user_id, conversation, agent_message)
    if AI_PROVIDER == "bedrock":
        return await call_bedrock(user_id, conversation, agent_message)
    raise HTTPException(
        status_code=500,
        detail=f"Unsupported AI_PROVIDER '{AI_PROVIDER}'. Use 'bedrock' or 'grok'.",
    )


def _build_quota_increments(user_id: str, tier: str, llm_tokens: int) -> Dict[str, int]:
    increments: Dict[str, int] = {
        "tokens": max(0, int(llm_tokens or 0)),
        "pdf": 0,
        "email": 0,
    }
    if tier == "high":
        truth_context = _load_truth_context_for_trace(TRACE_ID.get())
        action_counts = count_quota_actions_from_truth_context(truth_context)
        increments["pdf"] = int(action_counts.get("pdf", 0))
        increments["email"] = int(action_counts.get("email", 0))

    log_event(
        "quota.increments",
        user_id=user_id,
        tokens=increments["tokens"],
        pdf=increments["pdf"],
        email=increments["email"],
    )
    set_current_span_attributes(
        {
            "quota.tokens.increment": increments["tokens"],
            "quota.pdf.increment": increments["pdf"],
            "quota.email.increment": increments["email"],
        }
    )
    return increments


def _apply_quota_exceeded_message(
    assistant_response: str,
    *,
    quota_result: Dict[str, Any],
    quota_snapshot: Dict[str, Any],
) -> str:
    exceeded = set(quota_result.get("exceeded") or [])
    snapshot = quota_result.get("snapshot") or quota_snapshot
    if "tokens" in exceeded:
        return quota_exceeded_message("tokens", snapshot)
    if "pdf" in exceeded:
        return quota_exceeded_message("pdf", snapshot)
    if "email" in exceeded:
        return quota_exceeded_message("email", snapshot)
    return assistant_response


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
    _update_job_status_message("Generating response...", 85)
    result, _ = await run_grok_with_mcp_once(
        api_key=GROK_API_KEY,
        base_url=GROK_API_URL,
        model_id=GROK_MODEL_ID,
        llm_timeout_seconds=LLM_TIMEOUT_SECONDS,
        runner_timeout_seconds=RUNNER_TIMEOUT_SECONDS,
        mcp_startup_timeout_seconds=MCP_STARTUP_TIMEOUT_SECONDS,
        instructions=instructions,
        user_input=user_input,
        mcp_specs=mcp_specs,
    )
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

    agent_instructions = build_full_instructions(user_id)
    user_input = build_conversation_input(conversation, user_message)

    mcp_specs = build_mcp_server_specs(
        enable_search=ENABLE_MCP_SEARCH,
        job_id=_CURRENT_JOB_ID.get(),
    )
    log_event("execute.run_start", provider="grok", mcp_servers=len(mcp_specs))
    result, mcp_server_count = await run_grok_with_mcp_once(
        api_key=GROK_API_KEY,
        base_url=GROK_API_URL,
        model_id=GROK_MODEL_ID,
        llm_timeout_seconds=LLM_TIMEOUT_SECONDS,
        runner_timeout_seconds=RUNNER_TIMEOUT_SECONDS,
        mcp_startup_timeout_seconds=MCP_STARTUP_TIMEOUT_SECONDS,
        instructions=agent_instructions,
        user_input=user_input,
        mcp_specs=mcp_specs,
    )
    total_llm_tokens = usage_total_tokens(result)
    log_event("execute.run_done", provider="grok", mcp_servers=mcp_server_count)
    output = str(result.final_output or "")
    _update_job_status_message("Finalizing response...", 95)

    async def _rerun_with_fix(fix_instructions: str) -> Any:
        return await rerun_with_fix_instructions_result(
            user_id=user_id,
            conversation=conversation,
            user_message=user_message,
            fix_instructions=fix_instructions,
        )

    return await finalize_high_risk_response(
        user_id=user_id,
        user_message=user_message,
        session_id=session_id,
        require_sources=require_sources,
        initial_result=result,
        initial_output=output,
        total_llm_tokens=total_llm_tokens,
        rerun_with_fix=_rerun_with_fix,
    )


async def call_grok_prose_guarded(
    user_id: str, conversation: List[Dict], user_message: str
) -> tuple[str, int]:
    if not GROK_API_KEY:
        raise HTTPException(status_code=500, detail="GROK_API_KEY is not configured")

    instructions = (
        build_full_instructions(user_id)
        + "\n\nLow-risk conversational mode:\n"
        + "- Do not call tools.\n"
        + "- Do not claim actions were executed.\n"
        + "- Do not provide download links or email-delivery confirmations.\n"
    )
    user_input = build_conversation_input(conversation, user_message)

    _update_job_status_message("Generating response...", 85)
    result = await run_grok_once(
        api_key=GROK_API_KEY,
        base_url=GROK_API_URL,
        model_id=GROK_MODEL_ID,
        llm_timeout_seconds=LLM_TIMEOUT_SECONDS,
        runner_timeout_seconds=RUNNER_TIMEOUT_SECONDS,
        instructions=instructions,
        user_input=user_input,
    )
    llm_tokens = usage_total_tokens(result)

    output = str(result.final_output or "")
    guarded_output, issues = apply_low_risk_prose_guard(output)
    if issues:
        logging.info("[prose_guard] issues=%s", ",".join(issues))
    _update_job_status_message("Finalizing response...", 95)
    return guarded_output, llm_tokens


async def call_bedrock(user_id: str, conversation: List[Dict], user_message: str) -> tuple[str, int]:
    history_text = build_conversation_input(conversation, user_message)
    system_text = build_full_instructions(user_id)
    approved = load_approved_memory(user_id)
    logging.info("[memory_validator] approved_count=%d use_s3=%s", len(approved), USE_S3)
    _update_job_status_message("Starting tools...", 20)
    mcp_specs = build_mcp_server_specs(
        enable_search=ENABLE_MCP_SEARCH,
        job_id=_CURRENT_JOB_ID.get(),
    )
    return await run_bedrock_chat(
        bedrock_client=bedrock_client,
        bedrock_model_id=BEDROCK_MODEL_ID,
        default_aws_region=DEFAULT_AWS_REGION,
        system_text=system_text,
        history_text=history_text,
        user_message=user_message,
        mcp_specs=mcp_specs,
        approved_memory=approved,
    )


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


async def health_check():
    active_model = GROK_MODEL_ID if AI_PROVIDER == "grok" else BEDROCK_MODEL_ID
    return {
        "status": "healthy",
        "use_s3": USE_S3,
        "ai_provider": AI_PROVIDER,
        "ai_model": active_model,
        "mcp_search_enabled": ENABLE_MCP_SEARCH,
    }


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
    tracer = get_otel_tracer("digital_assistant.server")
    with tracer.start_as_current_span("chat.flow"):
        set_current_span_attributes(
            {
                "user.id": user_id,
                "session.id": session_id,
                "has_file": bool(file_id),
                "job.id": _CURRENT_JOB_ID.get() or "-",
            }
        )
        conversation = load_conversation(user_id, session_id)
        agent_message = build_agent_message(message, file_id)
        job_id = _CURRENT_JOB_ID.get()
        if _is_job_canceled(job_id):
            raise HTTPException(status_code=499, detail="canceled")

        should_sync_memory = _should_sync_memory_extraction(job_id)

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
        set_current_span_attributes(
            {"risk.tier": tier, "risk.reason": reason, "require_sources": require_sources}
        )
        log_event("classify", risk_tier=tier, reason=reason, provider=AI_PROVIDER)

        assistant_response, llm_tokens = await _generate_response_for_risk(
            user_id=user_id,
            conversation=conversation,
            agent_message=agent_message,
            session_id=session_id,
            tier=tier,
            require_sources=require_sources,
        )

        quota_increments = _build_quota_increments(user_id, tier, llm_tokens)

        try:
            quota_result = consume_daily_quota(user_id, quota_increments)
        except Exception as exc:
            log_event("quota.consume_failed", level=logging.WARNING, user_id=user_id, error=str(exc))
            record_current_span_exception(exc)
            quota_result = {"snapshot": quota_snapshot, "exceeded": [], "applied": {}}

        assistant_response = _apply_quota_exceeded_message(
            assistant_response,
            quota_result=quota_result,
            quota_snapshot=quota_snapshot,
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


def _new_async_job_record(*, job_id: str, user_id: str, session_id: str, trace_id: str) -> Dict[str, Any]:
    created_at = now_local_iso()
    return {
        "job_id": job_id,
        "user_id": user_id,
        "session_id": session_id,
        "status": "queued",
        "trace_id": trace_id,
        "created_at": created_at,
        "updated_at": created_at,
    }


def _mark_async_job_failed(job_record: Dict[str, Any], error_message: str) -> None:
    job_record["status"] = "failed"
    job_record["error"] = error_message
    job_record["updated_at"] = now_local_iso()
    _upstash_set(_job_key(job_record["job_id"]), job_record, ASYNC_JOB_TTL_SECONDS)


async def chat(request: ChatRequest):
    try:
        user_id = validate_user_id(request.user_id)
        session_id = request.session_id or str(uuid.uuid4())

        if ASYNC_CHAT_ENABLED:
            if not _upstash_enabled() or not ASYNC_WORKER_FUNCTION_NAME:
                raise HTTPException(status_code=500, detail="Async chat is not configured")

            job_id = str(uuid.uuid4())
            trace_id = new_trace_id()
            job_record = _new_async_job_record(
                job_id=job_id,
                user_id=user_id,
                session_id=session_id,
                trace_id=trace_id,
            )
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
                _mark_async_job_failed(job_record, f"Failed to enqueue job: {e}")
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
        record_current_span_exception(e)
        logging.exception("event=chat.unhandled_exception")
        raise HTTPException(status_code=500, detail=str(e))


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
    job["updated_at"] = now_local_iso()
    _upstash_set(_job_key(job_id), job, ASYNC_JOB_TTL_SECONDS)
    return {"status": "canceled", "job_id": job_id}


async def get_conversation(session_id: str, user_id: str = Query(...)):
    """Retrieve conversation history"""
    try:
        user_id = validate_user_id(user_id)
        conversation = load_conversation(user_id, session_id)
        return {"session_id": session_id, "messages": conversation}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_conversations(user_id: str = Query(...), limit: int = Query(5, ge=1, le=50)):
    """List recent conversations for a user"""
    user_id = validate_user_id(user_id)
    sessions = list_conversations(user_id, limit=limit)
    return {"sessions": sessions}


async def get_memory_candidates(user_id: str = Query(...)):
    user_id = validate_user_id(user_id)
    candidates = load_memory_candidates(user_id)
    candidates.sort(key=lambda c: c.get("created_at", ""), reverse=True)
    return {"candidates": candidates}


async def get_memory(user_id: str = Query(...)):
    user_id = validate_user_id(user_id)
    approved = load_approved_memory(user_id)
    approved.sort(key=lambda c: c.get("approved_at", ""), reverse=True)
    return {"memory": approved}


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


async def reject_memory_candidate(candidate_id: str, user_id: str = Query(...)):
    user_id = validate_user_id(user_id)
    candidates = load_memory_candidates(user_id)
    remaining = [cand for cand in candidates if cand.get("id") != candidate_id]
    save_memory_candidates(user_id, remaining)
    return {"status": "ok"}


async def clear_memory_candidates(user_id: str = Query(...)):
    user_id = validate_user_id(user_id)
    save_memory_candidates(user_id, [])
    save_memory_last_extracted_at(user_id, now_local_iso())
    return {"status": "ok"}


async def delete_approved_memory(memory_id: str, user_id: str = Query(...)):
    user_id = validate_user_id(user_id)
    approved = load_approved_memory(user_id)
    remaining = [mem for mem in approved if mem.get("id") != memory_id]
    if len(remaining) == len(approved):
        raise HTTPException(status_code=404, detail="memory not found")
    save_approved_memory(user_id, remaining)
    return {"status": "ok"}


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
