import os
from dotenv import load_dotenv
from market import is_paid_polygon, is_realtime_polygon
import sys
from pathlib import Path

load_dotenv(override=True)

brave_env = {"BRAVE_API_KEY": os.getenv("BRAVE_API_KEY")}
polygon_api_key = os.getenv("POLYGON_API_KEY")
polygon_plan = os.getenv("POLYGON_PLAN")
enable_brave_mcp = os.getenv("ENABLE_BRAVE_MCP", "true").strip().lower() == "true"
enable_memory_mcp = os.getenv("ENABLE_MEMORY_MCP", "true").strip().lower() == "true"
enable_fetch_mcp = os.getenv("ENABLE_FETCH_MCP", "true").strip().lower() == "true"
ENGINE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("TRADER_DATA_DIR", str(ENGINE_DIR.parent / "data"))).resolve()
MEMORY_DIR = DATA_DIR / "memory"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

# The MCP server for the Trader to read Market Data



# The full set of MCP servers for the trader: Accounts, Push Notification and the Market
def trader_mcp_server_params():
    common_trader_env: dict[str, str] = {}
    if polygon_api_key:
        common_trader_env["POLYGON_API_KEY"] = polygon_api_key
    if polygon_plan:
        common_trader_env["POLYGON_PLAN"] = polygon_plan
    common_trader_env.update(brave_env)

    if is_paid_polygon or is_realtime_polygon:
        market_mcp = {
            "command": "uvx",
            "args": ["--from", "git+https://github.com/massive-com/mcp_massive@v0.6.0", "mcp_massive"],
            "env": {"POLYGON_API_KEY": polygon_api_key},
        }
    else:
        market_mcp = {
            "command": sys.executable,
            "args": ["market_server.py"],
            "env": common_trader_env if common_trader_env else None,
        }

    return [
        {
            "command": sys.executable,
            "args": ["accounts_server.py"],
            "env": common_trader_env if common_trader_env else None,
        },
      #  {"command": "uv", "args": ["run", "push_server.py"]},
        market_mcp,
    ]

# The full set of MCP servers for the researcher: Fetch, Brave Search and Memory
def researcher_mcp_server_params(name: str):
    servers = []
    if enable_fetch_mcp:
        servers.append(
            {
                "command": "mcp-server-fetch",
                "args": [],
            }
        )
    if enable_brave_mcp and brave_env.get("BRAVE_API_KEY"):
        servers.append(
            {
                "command": "mcp-server-brave-search",
                "args": [],
                "env": brave_env,
            }
        )
    if enable_memory_mcp:
        memory_env = {"LIBSQL_URL": f"file:{(MEMORY_DIR / f'{name}.db').as_posix()}"}
        servers.append(
            {
                "command": "mcp-memory-libsql",
                "args": [],
                "env": memory_env,
            }
        )
    return servers
