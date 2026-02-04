import os
from dotenv import load_dotenv
from market import is_paid_polygon, is_realtime_polygon
import sys
from pathlib import Path

load_dotenv(override=True)

brave_env = {"BRAVE_API_KEY": os.getenv("BRAVE_API_KEY")}
polygon_api_key = os.getenv("POLYGON_API_KEY")
enable_brave_mcp = os.getenv("ENABLE_BRAVE_MCP", "true").strip().lower() == "true"
enable_memory_mcp = os.getenv("ENABLE_MEMORY_MCP", "true").strip().lower() == "true"
enable_fetch_mcp = os.getenv("ENABLE_FETCH_MCP", "true").strip().lower() == "true"
ENGINE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("TRADER_DATA_DIR", str(ENGINE_DIR.parent / "data"))).resolve()
MEMORY_DIR = DATA_DIR / "memory"
NPM_CACHE_ROOT = DATA_DIR / ".npm-cache"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)
NPM_CACHE_ROOT.mkdir(parents=True, exist_ok=True)


def _npx_env(cache_key: str, extra_env: dict[str, str] | None = None) -> dict[str, str]:
    cache_dir = NPM_CACHE_ROOT / cache_key
    cache_dir.mkdir(parents=True, exist_ok=True)
    env = {
        "NPM_CONFIG_CACHE": str(cache_dir),
        "npm_config_yes": "true",
        "npm_config_update_notifier": "false",
        "npm_config_fund": "false",
        "npm_config_audit": "false",
    }
    if extra_env:
        env.update(extra_env)
    return env

# The MCP server for the Trader to read Market Data



# The full set of MCP servers for the trader: Accounts, Push Notification and the Market
def trader_mcp_server_params():
    if is_paid_polygon or is_realtime_polygon:
        market_mcp = {
            "command": "uvx",
            "args": ["--from", "git+https://github.com/massive-com/mcp_massive@v0.6.0", "mcp_massive"],
            "env": {"POLYGON_API_KEY": polygon_api_key},
        }
    else:
        market_mcp = {"command": sys.executable, "args": ["market_server.py"]}

    return [
        {"command": sys.executable, "args": ["accounts_server.py"]},
      #  {"command": "uv", "args": ["run", "push_server.py"]},
        market_mcp,
    ]

# The full set of MCP servers for the researcher: Fetch, Brave Search and Memory
def researcher_mcp_server_params(name: str):
    servers = []
    if enable_fetch_mcp:
        # mcp-server-fetch can emit noisy BrokenPipe traces on normal stdio teardown.
        # Route stderr away from container logs while keeping MCP stdio channel intact.
        servers.append(
            {
                "command": "sh",
                "args": ["-lc", "uvx mcp-server-fetch 2>/dev/null"],
            }
        )
    if enable_brave_mcp and brave_env.get("BRAVE_API_KEY"):
        servers.append(
            {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-brave-search"],
                "env": _npx_env(f"{name}-brave", brave_env),
            }
        )
    if enable_memory_mcp:
        servers.append(
            {
                "command": "npx",
                "args": ["-y", "mcp-memory-libsql"],
                "env": _npx_env(
                    f"{name}-memory",
                    {"LIBSQL_URL": f"file:{(MEMORY_DIR / f'{name}.db').as_posix()}"},
                ),
            }
        )
    return servers
