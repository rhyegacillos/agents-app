from __future__ import annotations

from contextlib import AsyncExitStack
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

from otel_observability import get_tracer as get_otel_tracer


ToolSpec = Dict[str, Any]


def _get_tool_fields(tool: Any) -> Tuple[str, str, Dict[str, Any]]:
    name = ""
    description = ""
    schema: Dict[str, Any] = {"type": "object", "properties": {}}
    if isinstance(tool, dict):
        name = tool.get("name") or ""
        description = tool.get("description") or ""
        schema = tool.get("inputSchema") or tool.get("input_schema") or schema
    else:
        name = getattr(tool, "name", "") or ""
        description = getattr(tool, "description", "") or ""
        schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None) or schema
    return name, description, schema or {"type": "object", "properties": {}}


async def _open_mcp_sessions(
    specs: List[Dict[str, Any]],
    stack: AsyncExitStack,
) -> Tuple[List[Dict[str, Any]], Dict[str, ClientSession]]:
    tool_specs: List[Dict[str, Any]] = []
    tool_sessions: Dict[str, ClientSession] = {}

    for spec in specs:
        params = spec.get("params") or {}
        read, write = await stack.enter_async_context(
            stdio_client(
                StdioServerParameters(
                    command=params.get("command"),
                    args=params.get("args") or [],
                    env=params.get("env") or {},
                )
            )
        )
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        tools_resp = await session.list_tools()
        tools = tools_resp.get("tools") if isinstance(tools_resp, dict) else getattr(tools_resp, "tools", None)
        tools = tools or []
        for tool in tools:
            name, description, schema = _get_tool_fields(tool)
            if not name or name in tool_sessions:
                continue
            tool_specs.append(
                {
                    "toolSpec": {
                        "name": name,
                        "description": description or "",
                        "inputSchema": {"json": schema},
                    }
                }
            )
            tool_sessions[name] = session

    return tool_specs, tool_sessions


def _extract_tool_uses(content_blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    uses: List[Dict[str, Any]] = []
    for block in content_blocks or []:
        tool_use = block.get("toolUse")
        if tool_use:
            uses.append(tool_use)
    return uses


def _extract_text(content_blocks: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for block in content_blocks or []:
        if "text" in block:
            parts.append(block.get("text") or "")
    return "".join(parts).strip()


def _tool_result_payload(result: Any) -> Any:
    payload = None
    if isinstance(result, dict):
        payload = result
    elif hasattr(result, "structuredContent") and result.structuredContent is not None:
        payload = result.structuredContent
    elif hasattr(result, "structured_content") and result.structured_content is not None:
        payload = result.structured_content
    if payload is None:
        payload = {"result": str(result)}
    return payload


def _tool_result_block(tool_use_id: str, result: Any) -> Dict[str, Any]:
    payload = _tool_result_payload(result)

    return {
        "toolResult": {
            "toolUseId": tool_use_id,
            "content": [{"json": payload}],
        }
    }


async def run_bedrock_with_tools(
    *,
    bedrock_client: Any,
    model_id: str,
    system_text: str,
    user_text: str,
    mcp_specs: List[Dict[str, Any]],
    required_tool_names: Optional[List[str]] = None,
    max_tool_rounds: int = 6,
    inference_config: Optional[Dict[str, Any]] = None,
) -> Tuple[str, int, List[Dict[str, Any]]]:
    inference_config = inference_config or {"maxTokens": 2000, "temperature": 0.7, "topP": 0.9}
    tracer = get_otel_tracer("digital_assistant.bedrock_tools")
    async with AsyncExitStack() as stack:
        tool_specs, tool_sessions = await _open_mcp_sessions(mcp_specs, stack)
        base_tool_config = {"tools": tool_specs} if tool_specs else None
        pending_required_tools = [
            name
            for name in (required_tool_names or [])
            if isinstance(name, str) and name and name in tool_sessions
        ]
        total_tokens_used = 0
        tool_events: List[Dict[str, Any]] = []

        messages = [{"role": "user", "content": [{"text": user_text}]}]

        for _ in range(max_tool_rounds):
            tool_config = dict(base_tool_config) if base_tool_config else None
            next_required_tool = pending_required_tools[0] if pending_required_tools else None
            if tool_config and next_required_tool:
                tool_config["toolChoice"] = {"tool": {"name": next_required_tool}}
            response = bedrock_client.converse(
                modelId=model_id,
                system=[{"text": system_text}],
                messages=messages,
                toolConfig=tool_config,
                inferenceConfig=inference_config,
            )
            usage = response.get("usage", {}) or {}
            try:
                total_tokens_used += int(
                    usage.get("totalTokens")
                    or usage.get("total_tokens")
                    or (
                        int(usage.get("inputTokens", 0) or 0)
                        + int(usage.get("outputTokens", 0) or 0)
                    )
                )
            except (TypeError, ValueError):
                pass
            content_blocks = response.get("output", {}).get("message", {}).get("content", []) or []
            tool_uses = _extract_tool_uses(content_blocks)
            messages.append({"role": "assistant", "content": content_blocks})

            if not tool_uses:
                return _extract_text(content_blocks), total_tokens_used, tool_events

            tool_result_blocks: List[Dict[str, Any]] = []
            called_tool_names: List[str] = []
            for tool_use in tool_uses:
                tool_name = tool_use.get("name")
                tool_use_id = tool_use.get("toolUseId")
                tool_input = tool_use.get("input") or {}
                if not tool_name or not tool_use_id:
                    continue
                with tracer.start_as_current_span(f"tool.{tool_name}"):
                    span = None
                    try:
                        from opentelemetry import trace as otel_trace

                        span = otel_trace.get_current_span()
                    except Exception:
                        span = None
                    if span is not None:
                        span.set_attribute("tool.name", str(tool_name))
                        span.set_attribute("tool.use_id", str(tool_use_id))
                    session = tool_sessions.get(tool_name)
                    if span is not None:
                        span.set_attribute("tool.available", bool(session))
                    if not session:
                        tool_result = {"error": f"Tool not available: {tool_name}"}
                        if span is not None:
                            span.set_attribute("tool.status", "error")
                    else:
                        tool_result = await session.call_tool(tool_name, arguments=tool_input)
                        payload = _tool_result_payload(tool_result)
                        status = "ok"
                        if isinstance(payload, dict):
                            status = str(payload.get("status") or ("error" if payload.get("error") else "ok"))
                        if span is not None:
                            span.set_attribute("tool.status", status)
                tool_events.append(
                    {
                        "tool_name": str(tool_name),
                        "output": _tool_result_payload(tool_result),
                    }
                )
                called_tool_names.append(str(tool_name))
                tool_result_blocks.append(_tool_result_block(tool_use_id, tool_result))

            if tool_result_blocks:
                messages.append(
                    {
                        "role": "user",
                        "content": tool_result_blocks,
                    }
                )
            while pending_required_tools and pending_required_tools[0] in called_tool_names:
                pending_required_tools.pop(0)

    tool_counter = Counter(str(evt.get("tool_name") or "unknown") for evt in tool_events if isinstance(evt, dict))
    summary = ", ".join(f"{name}x{count}" for name, count in tool_counter.items()) or "none"
    raise RuntimeError(
        "Bedrock tool loop exceeded maximum rounds "
        f"(required_tools={','.join(required_tool_names or []) or '-'}, "
        f"next_required_tool={pending_required_tools[0] if pending_required_tools else '-'}, "
        f"tool_summary={summary})"
    )
