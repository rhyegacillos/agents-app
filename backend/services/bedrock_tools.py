from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional, Tuple

from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters


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


def _tool_result_block(tool_use_id: str, result: Any) -> Dict[str, Any]:
    payload = None
    if isinstance(result, dict):
        payload = result
    elif hasattr(result, "structuredContent") and result.structuredContent is not None:
        payload = result.structuredContent
    elif hasattr(result, "structured_content") and result.structured_content is not None:
        payload = result.structured_content
    if payload is None:
        payload = {"result": str(result)}

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
    max_tool_rounds: int = 6,
    inference_config: Optional[Dict[str, Any]] = None,
) -> str:
    inference_config = inference_config or {"maxTokens": 2000, "temperature": 0.7, "topP": 0.9}
    async with AsyncExitStack() as stack:
        tool_specs, tool_sessions = await _open_mcp_sessions(mcp_specs, stack)
        tool_config = {"tools": tool_specs} if tool_specs else None

        messages = [{"role": "user", "content": [{"text": user_text}]}]

        for _ in range(max_tool_rounds):
            response = bedrock_client.converse(
                modelId=model_id,
                system=[{"text": system_text}],
                messages=messages,
                toolConfig=tool_config,
                inferenceConfig=inference_config,
            )
            content_blocks = response.get("output", {}).get("message", {}).get("content", []) or []
            tool_uses = _extract_tool_uses(content_blocks)
            messages.append({"role": "assistant", "content": content_blocks})

            if not tool_uses:
                return _extract_text(content_blocks)

            tool_result_blocks: List[Dict[str, Any]] = []
            for tool_use in tool_uses:
                tool_name = tool_use.get("name")
                tool_use_id = tool_use.get("toolUseId")
                tool_input = tool_use.get("input") or {}
                if not tool_name or not tool_use_id:
                    continue
                session = tool_sessions.get(tool_name)
                if not session:
                    tool_result = {"error": f"Tool not available: {tool_name}"}
                else:
                    tool_result = await session.call_tool(tool_name, arguments=tool_input)
                tool_result_blocks.append(_tool_result_block(tool_use_id, tool_result))

            if tool_result_blocks:
                messages.append(
                    {
                        "role": "user",
                        "content": tool_result_blocks,
                    }
                )

    raise RuntimeError("Bedrock tool loop exceeded maximum rounds")
