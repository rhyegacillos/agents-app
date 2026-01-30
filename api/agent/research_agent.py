import os
import json
import time
import hashlib
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

# --- Caching Configuration ---
RESEARCH_CACHE: Dict[str, Any] = {}
CACHE_TTL_SECONDS = 3600  # 1 hour
# ---------------------------

MCP_SERVER_COMMAND = "npx"
MCP_SERVER_ARGS = ["-y", "@brave/brave-search-mcp-server", "--transport", "stdio"]
MCP_SERVER_TIMEOUT_SECONDS = 60
OPENAI_RESEARCH_MODEL = "gpt-4o-mini"


def _build_mcp_params() -> Dict[str, Any]:
    env: Dict[str, str] = {}
    brave_key = os.getenv("BRAVE_API_KEY")
    if brave_key:
        env["BRAVE_API_KEY"] = brave_key

    return {"command": MCP_SERVER_COMMAND, "args": MCP_SERVER_ARGS, "env": env}


def _parse_research_output(output: str) -> List[Dict[str, Any]]:
    if not output:
        return []
    content = output.strip()
    start_obj = content.find("{")
    start_list = content.find("[")
    if start_list != -1 and (start_obj == -1 or start_list < start_obj):
        start = start_list
        end = content.rfind("]")
    else:
        start = start_obj
        end = content.rfind("}")

    if start != -1 and end > start:
        try:
            data = json.loads(content[start : end + 1])
            if isinstance(data, dict):
                return [_normalize_research_item(data)]
            if isinstance(data, list):
                return [_normalize_research_item(item) for item in data if isinstance(item, dict)]
        except Exception:
            pass

    return [_normalize_research_item({"summary": content, "sources": []})]


def _normalize_research_item(item: Dict[str, Any]) -> Dict[str, Any]:
    summary = str(item.get("summary") or item.get("text") or "").strip()
    sources = item.get("sources") or []
    cleaned_sources = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        url = str(source.get("url") or "").strip()
        if not url:
            continue
        title = str(source.get("title") or "").strip()
        cleaned_sources.append({"title": title, "url": url})
    return {"summary": summary, "sources": cleaned_sources}


async def _run_research_request(request: str, instructions: str) -> List[Dict[str, Any]]:
    # --- Cache Check ---
    cache_key = hashlib.sha256((request + instructions).encode("utf-8")).hexdigest()
    if cache_key in RESEARCH_CACHE:
        result, timestamp = RESEARCH_CACHE[cache_key]
        if time.time() - timestamp < CACHE_TTL_SECONDS:
            logger.info("Research cache hit.")
            return result
        else:
            logger.info("Research cache expired.")
            del RESEARCH_CACHE[cache_key]
    else:
        logger.info("Research cache miss.")
    # ------------------

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
    parsed_output = _parse_research_output(str(output))
    
    # Cache the successful result
    if parsed_output:
        RESEARCH_CACHE[cache_key] = (parsed_output, time.time())
        
    return parsed_output


async def check_drug_interactions(medications: List[str]) -> List[Dict[str, Any]]:
    if len(medications) < 2:
        logger.info("Research agent skipped: fewer than 2 medications.")
        return []

    instructions = (
        "You are a clinical research assistant. Your job is to find drug interaction information. "
        "Search the web for potential interactions between the provided medications. "
        "Return a valid JSON object with two keys: 'summary' (string) and 'sources' (list of objects).\n"
        "RULES:\n"
        "1. The 'summary' MUST be a concise, plain-text summary of the findings. DO NOT include URLs or markdown in the summary.\n"
        "2. The 'sources' array MUST contain objects, each with 'title' and 'url' keys.\n"
        "3. Every source you find MUST be a separate object in the 'sources' array.\n"
        "4. If no interactions are found, the summary should state that, and the 'sources' array should be empty."
    )
    request = f"Check potential drug interactions between: {', '.join(medications)}."
    return await _run_research_request(request, instructions)


async def search_medical_guidelines(condition: str) -> List[Dict[str, Any]]:
    condition = (condition or "").strip()
    if not condition:
        logger.info("Research agent skipped: no condition provided.")
        return []

    instructions = (
        "You are a clinical research assistant. Your job is to find clinical guideline recommendations. "
        "Search the web for guidelines related to the provided condition. Prefer official publishers (e.g., AAFP, AHA, EFNS).\n"
        "Return a valid JSON object with two keys: 'summary' (string) and 'sources' (list of objects).\n"
        "RULES:\n"
        "1. The 'summary' MUST be a concise, plain-text summary of the guideline recommendations. DO NOT include URLs or markdown in the summary.\n"
        "2. The 'sources' array MUST contain objects, each with 'title' and 'url' keys.\n"
        "3. Every source guideline you find MUST be a separate object in the 'sources' array.\n"
        "4. If no guidelines are found, the summary should state that, and the 'sources' array should be empty."
    )
    request = f"Find clinical guideline recommendations for: {condition}."
    return await _run_research_request(request, instructions)
