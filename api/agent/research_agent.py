import os
from typing import List, Dict, Any
from .utils import get_logger

try:
    from agents import Agent, Runner
    from agents.mcp import MCPServerStdio
except ImportError:
    try:
        from openai_agents import Agent, Runner
        from openai_agents.mcp import MCPServerStdio
    except ImportError:  # pragma: no cover - handled at runtime
        Agent = None
        Runner = None
        MCPServerStdio = None

logger = get_logger(__name__)

MCP_SERVER_COMMAND = "npx"
MCP_SERVER_ARGS = ["-y", "@brave/brave-search-mcp-server", "--transport", "stdio"]
MCP_SERVER_TIMEOUT_SECONDS = 120
OPENAI_RESEARCH_MODEL = "gpt-4o-mini"


def _build_mcp_params() -> Dict[str, Any]:
    env: Dict[str, str] = {}
    brave_key = os.getenv("BRAVE_API_KEY")
    if brave_key:
        env["BRAVE_API_KEY"] = brave_key

    return {"command": MCP_SERVER_COMMAND, "args": MCP_SERVER_ARGS, "env": env}


async def _run_research_request(request: str, instructions: str) -> List[str]:
    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("Research agent skipped: OPENAI_API_KEY not set.")
        logger.warning("OPENAI_API_KEY is not set; skipping research agent.")
        return []

    if MCPServerStdio is None or Agent is None or Runner is None:
        logger.error("openai-agents SDK not available; cannot use MCPServerStdio.")
        return []

    params = _build_mcp_params()
    logger.info("Executing MCP search via MCPServerStdio")

    try:
        async with MCPServerStdio(
            params=params,
            client_session_timeout_seconds=MCP_SERVER_TIMEOUT_SECONDS,
        ) as mcp_server:
            agent = Agent(
                name="research-agent",
                instructions=instructions,
                model=OPENAI_RESEARCH_MODEL,
                mcp_servers=[mcp_server],
            )
            result = await Runner.run(agent, request)
    except Exception as exc:
        logger.error(f"Research agent failed: {exc}")
        return []

    output = getattr(result, "final_output", None) or getattr(result, "output_text", None)
    if not output:
        logger.warning("Research agent completed with empty output.")
        return []

    logger.info("Research agent completed successfully.")
    return [str(output).strip()]


async def check_drug_interactions(medications: List[str]) -> List[str]:
    if len(medications) < 2:
        logger.info("Research agent skipped: fewer than 2 medications.")
        return []

    instructions = (
        "You can use MCP tools to search the web. "
        "Return a short, plain-language summary of potential drug-drug interactions. "
        "If none are found, say so clearly."
    )
    request = f"Check potential drug interactions between: {', '.join(medications)}."
    return await _run_research_request(request, instructions)


async def search_medical_guidelines(condition: str) -> List[str]:
    condition = (condition or "").strip()
    if not condition:
        logger.info("Research agent skipped: no condition provided.")
        return []

    instructions = (
        "You can use MCP tools to search the web. "
        "Summarize relevant clinical guideline recommendations for the condition. "
        "Keep the response concise and clinically focused."
    )
    request = f"Find clinical guideline recommendations for: {condition}."
    return await _run_research_request(request, instructions)
