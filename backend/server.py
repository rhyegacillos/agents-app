from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import os
from typing import Optional, List, Dict, Any
import json
import uuid
from datetime import datetime, timedelta
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
    bedrock_client,
    s3_client,
    MEMORY_TTL_MAP,
)
from services.memory import extract_and_store_memory
from services.bedrock_tools import run_bedrock_with_tools
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

# Disable openai-agents tracing to avoid noisy log errors
set_tracing_disabled(disabled=True)

app = FastAPI()

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


def _parse_timeout(value: str) -> Optional[float]:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _set_current_job_id(job_id: Optional[str]):
    return _CURRENT_JOB_ID.set(job_id)


def _reset_current_job_id(token) -> None:
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


def build_agent_instructions() -> str:
    return prompt()

def build_tool_instructions() -> str:
    return """
## Tool Use (Available Capabilities)

You have access to tools. Use them when the user asks for these actions:
- **Read attached files**: if the user asks to summarize/inspect an uploaded file, call `read_uploaded_file` using the provided `file_id`.
- **Send email**: if the user asks to send an email or deliver a PDF by email, call `send_resend_email`.
- **Generate PDF**: if the user asks for a PDF, call `generate_pdf_from_text` with the content.
- **Download PDF**: if the user provides a PDF URL to fetch, call `download_pdf`.
- **Web search**: if the user asks for current information and web search is enabled, use the search tool.

Tool-call formatting rules:
- If you decide to call a tool, respond with **only** tool calls in that turn (no extra text).
- After tool results return, produce the final user-facing response.

Do not claim you cannot access files or send email when these tools are available.
If a tool fails, explain the failure briefly and ask the user for the next best option.
"""

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
        return result.final_output


async def call_grok_with_mcp(user_id: str, conversation: List[Dict], user_message: str) -> str:
    if not GROK_API_KEY:
        raise HTTPException(status_code=500, detail="GROK_API_KEY is not configured")

    llm_timeout = _parse_timeout(LLM_TIMEOUT_SECONDS)
    if llm_timeout:
        client = AsyncOpenAI(api_key=GROK_API_KEY, base_url=GROK_API_URL, timeout=llm_timeout)
    else:
        client = AsyncOpenAI(api_key=GROK_API_KEY, base_url=GROK_API_URL)
    model = OpenAIChatCompletionsModel(model=GROK_MODEL_ID, openai_client=client)

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

        run_timeout = _parse_timeout(RUNNER_TIMEOUT_SECONDS)
        if run_timeout:
            result = await asyncio.wait_for(Runner.run(agent, user_input), timeout=run_timeout)
        else:
            result = await Runner.run(agent, user_input)
        output = result.final_output
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
                output = await rerun_with_fix_instructions(
                    user_id, conversation, user_message, verdict.get("fix_instructions", "")
                )
        else:
            logging.info("[memory_validator] skipped (no approved memory)")

        return output


async def call_bedrock(user_id: str, conversation: List[Dict], user_message: str) -> str:
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
            _update_job_status_message("Starting tools...", 20)
            mcp_specs = build_mcp_server_specs(
                enable_search=ENABLE_MCP_SEARCH,
                job_id=_CURRENT_JOB_ID.get(),
            )
            output = await run_bedrock_with_tools(
                bedrock_client=bedrock_client,
                model_id=model_id,
                system_text=system_text,
                user_text=history_text,
                mcp_specs=mcp_specs,
                inference_config={"maxTokens": 2000, "temperature": 0.7, "topP": 0.9},
            )
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
                    output = await run_bedrock_with_tools(
                        bedrock_client=bedrock_client,
                        model_id=model_id,
                        system_text=system,
                        user_text=user_text,
                        mcp_specs=mcp_specs,
                        inference_config={"maxTokens": 2000, "temperature": 0.0, "topP": 0.9},
                    )
            else:
                logging.info("[memory_validator] skipped (no approved memory)")
            return output
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


async def _run_chat_flow(
    *,
    user_id: str,
    session_id: str,
    message: str,
    file_id: Optional[str],
) -> str:
    conversation = load_conversation(user_id, session_id)
    agent_message = build_agent_message(message, file_id)

    tool_intent = bool(file_id) or bool(
        re.search(
            r"\b(email|pdf|download|upload|file|attach|attachment|summari[sz]e|search|web|news|latest|cite|citation|source|sources)\b",
            message or "",
            re.IGNORECASE,
        )
    )

    if AI_PROVIDER == "grok":
        assistant_response = await call_grok_with_mcp(user_id, conversation, agent_message)
    elif AI_PROVIDER == "bedrock":
        if tool_intent:
            logging.info("[routing] tool_intent=true -> using grok for tool call")
            assistant_response = await call_grok_with_mcp(user_id, conversation, agent_message)
        else:
            assistant_response = await call_bedrock(user_id, conversation, agent_message)
    else:
        raise HTTPException(
            status_code=500,
            detail=f"Unsupported AI_PROVIDER '{AI_PROVIDER}'. Use 'bedrock' or 'grok'.",
        )

    await _persist_chat_turn(
        user_id=user_id,
        session_id=session_id,
        conversation=conversation,
        user_message=message,
        assistant_response=assistant_response,
        sync_memory=MEMORY_EXTRACT_SYNC,
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
            job_record = {
                "job_id": job_id,
                "user_id": user_id,
                "session_id": session_id,
                "status": "queued",
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
    now = datetime.utcnow()
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
    return FileResponse(
        file_path,
        media_type="application/pdf",
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
