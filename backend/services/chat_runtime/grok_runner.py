import asyncio
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional, Tuple

from agents import Agent, OpenAIChatCompletionsModel, Runner
from agents.mcp import MCPServerStdio
from fastapi import HTTPException
from openai import AsyncOpenAI


def _parse_timeout(value: str) -> Optional[float]:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _build_openai_client_kwargs(*, api_key: str, base_url: str, llm_timeout_seconds: str) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {"api_key": api_key, "base_url": base_url}
    llm_timeout = _parse_timeout(llm_timeout_seconds)
    if llm_timeout:
        kwargs["timeout"] = llm_timeout
    return kwargs


def usage_total_tokens(result: Any) -> int:
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


async def _run_agent_with_timeout(agent: Agent, user_input: str, *, runner_timeout_seconds: str) -> Any:
    run_timeout = _parse_timeout(runner_timeout_seconds)
    if run_timeout:
        return await asyncio.wait_for(Runner.run(agent, user_input), timeout=run_timeout)
    return await Runner.run(agent, user_input)


async def _enter_mcp_server(
    stack: AsyncExitStack,
    *,
    name: str,
    params: Dict[str, Any],
    timeout_seconds: Optional[float],
) -> Any:
    server_ctx = MCPServerStdio(
        name=name,
        params=params,
        client_session_timeout_seconds=360000,
    )
    try:
        if timeout_seconds:
            return await asyncio.wait_for(stack.enter_async_context(server_ctx), timeout=timeout_seconds)
        return await stack.enter_async_context(server_ctx)
    except asyncio.TimeoutError as e:
        msg = f"MCP startup timeout for {name} after {timeout_seconds}s"
        raise HTTPException(status_code=504, detail=msg) from e
    except Exception as e:
        msg = f"MCP startup failed for {name}: {e}"
        raise HTTPException(status_code=500, detail=msg) from e


async def _start_mcp_servers(
    stack: AsyncExitStack,
    *,
    mcp_specs: List[Dict[str, Any]],
    mcp_startup_timeout_seconds: str,
) -> List[Any]:
    timeout_seconds = _parse_timeout(mcp_startup_timeout_seconds)
    servers: List[Any] = []
    for spec in mcp_specs:
        server = await _enter_mcp_server(
            stack,
            name=spec["name"],
            params=spec["params"],
            timeout_seconds=timeout_seconds,
        )
        servers.append(server)
    return servers


async def run_grok_with_mcp_once(
    *,
    api_key: str,
    base_url: str,
    model_id: str,
    llm_timeout_seconds: str,
    runner_timeout_seconds: str,
    mcp_startup_timeout_seconds: str,
    instructions: str,
    user_input: str,
    mcp_specs: List[Dict[str, Any]],
    agent_name: str = "Digital Assistant",
) -> Tuple[Any, int]:
    client_kwargs = _build_openai_client_kwargs(
        api_key=api_key,
        base_url=base_url,
        llm_timeout_seconds=llm_timeout_seconds,
    )
    async with AsyncOpenAI(**client_kwargs) as client:
        model = OpenAIChatCompletionsModel(model=model_id, openai_client=client)
        async with AsyncExitStack() as stack:
            mcp_servers = await _start_mcp_servers(
                stack,
                mcp_specs=mcp_specs,
                mcp_startup_timeout_seconds=mcp_startup_timeout_seconds,
            )
            agent = Agent(
                name=agent_name,
                instructions=instructions,
                model=model,
                mcp_servers=mcp_servers,
            )
            result = await _run_agent_with_timeout(
                agent,
                user_input,
                runner_timeout_seconds=runner_timeout_seconds,
            )
            return result, len(mcp_servers)


async def run_grok_once(
    *,
    api_key: str,
    base_url: str,
    model_id: str,
    llm_timeout_seconds: str,
    runner_timeout_seconds: str,
    instructions: str,
    user_input: str,
    agent_name: str = "Digital Assistant",
) -> Any:
    client_kwargs = _build_openai_client_kwargs(
        api_key=api_key,
        base_url=base_url,
        llm_timeout_seconds=llm_timeout_seconds,
    )
    async with AsyncOpenAI(**client_kwargs) as client:
        model = OpenAIChatCompletionsModel(model=model_id, openai_client=client)
        agent = Agent(
            name=agent_name,
            instructions=instructions,
            model=model,
        )
        return await _run_agent_with_timeout(
            agent,
            user_input,
            runner_timeout_seconds=runner_timeout_seconds,
        )
