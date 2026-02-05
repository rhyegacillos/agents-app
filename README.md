# Autonomous Trader Web App

This repo runs a single-container web app with all backend logic under `api/`.

## Architecture

- `api/` - FastAPI backend, trader engine, MCP servers, data, and scripts
- `web/` - Next.js dashboard for control + monitoring
- `Dockerfile` - single-container build (FastAPI + exported Next.js)
- `docker-compose.yml` - local run helper for the single container

## Project Docs

- `ARCHITECTURE.md` - detailed system, API, agent, and data-flow internals
- `ROADMAP.md` - future feature plan for holdings-only market trend chart
- `DEPLOY_ECR_TO_EC2.md` - step-by-step ECR -> EC2 deployment guide
- `MVP_LIVE_TRADING_COST.md` - live-trading MVP cost model (subscriptions, premium tiers, upgrade path)

## Recent Implementation Updates

### 1) Price source fallback (no random fallback)

Share-price lookup now follows this order in `api/trader_engine/market.py`:

1. `POLYGON` via Polygon API (plan-aware behavior)
2. `CACHE` via in-memory last-known symbol price
3. `WEB` via Brave Search API (`get_share_price_brave`)
4. `UNAVAILABLE` with numeric price `0.0` if all sources fail

Important:
- Random fallback was removed from the runtime price path.
- Trade execution now rejects unavailable prices (`price <= 0`) instead of silently trading on synthetic values.

### 2) Cash vs Market Value vs Total Equity

Account reporting now separates core portfolio metrics:

- `cash_balance`: available cash balance
- `holdings_market_value`: mark-to-market value of holdings only
- `total_equity`: `cash_balance + holdings_market_value`
- `total_portfolio_value`: backward-compatible alias to `total_equity`

UI updates:
- Holdings panel now shows `Cash`, `Market Value`, and `Total Equity`.
- Top portfolio card shows combined totals with a cash/market breakdown.

### 3) Trading safety guardrails

Execution guards are now enforced in backend:

- `buy_shares` and `sell_shares` require `quantity > 0`.
- `buy_shares` requires sufficient cash (`balance`) for total cost.
- buy/sell both require valid positive market price.

Additional visibility:
- Failed trades are logged explicitly in live logs:
  - `BUY FAILED <SYMBOL> x<QTY>: <reason>`
  - `SELL FAILED <SYMBOL> x<QTY>: <reason>`
- Successful trade logs still include source tagging:
  - `<SYMBOL> - <PRICE> - POLYGON|CACHE|WEB`

### 4) MCP runtime hardening

Researcher MCP servers are now launched from preinstalled commands (not runtime `npx` in normal flow):

- `mcp-server-fetch`
- `mcp-server-brave-search`
- `mcp-memory-libsql`

Trader lifecycle now keeps MCP sessions alive per trader instance and reuses them across cycles, reducing startup churn and protocol instability.

### 5) Multi-model tool-call compatibility

For non-OpenAI chat-completions providers (DeepSeek/Grok/Gemini), tool output message content is normalized to string format before sending back to the model.  
This prevents provider-side tool-response schema errors during multi-model runs.

## API Endpoints

- `GET /health`
- `GET /api/traders`
- `GET /api/traders/{name}`
- `GET /api/traders/{name}/logs?limit=50`
- `GET /api/scheduler/status`
- `POST /api/scheduler/start`
- `POST /api/scheduler/stop`
- `POST /api/reset`

### Trader payload notes

`GET /api/traders` and `GET /api/traders/{name}` summaries now include:

- `cash_balance`
- `holdings_market_value`
- `total_equity`
- `total_portfolio_value` (compatibility alias)
- `total_profit_loss`

## Run with Docker

1. Copy environment values:

```bash
cp .env.example .env
# fill the API keys you need in .env
```

2. Build and start (single container):

```bash
docker compose up --build
```

3. Open:

- Web UI + API host: `http://localhost:8000`
- Health check: `http://localhost:8000/health`

If Brave MCP fails to start, the trader runtime now skips that MCP server and continues with remaining tools.
Researcher MCP startup failures are isolated per server and soft-disabled for future cycles in-process.

### Read-only + market-auto mode (AWS-friendly)

Set these in `.env`:

```bash
READ_ONLY_MODE=true
AUTO_TRADE_BY_MARKET=true
MARKET_WATCH_INTERVAL_SEC=60
STRICT_FLAT_WHEN_NO_TRADE=true
```

Behavior:
- Trade controls (`start/stop/reset`) are API-blocked with `403` in read-only mode.
- Backend watchdog auto-starts trading when market is open and auto-stops when market is closed.
- Portfolio valuation can be frozen between trades when `STRICT_FLAT_WHEN_NO_TRADE=true`.

### Valuation + UI semantics (current behavior)

- `STRICT_FLAT_WHEN_NO_TRADE=true` (recommended for demo clarity):
  - account reads do not move valuation between executions
  - timeline snapshots are written on `buy`/`sell` and reset baseline only
  - holdings + total cards use `Profit` / `Loss` wording based on sign
- `STRICT_FLAT_WHEN_NO_TRADE=false`:
  - API-derived portfolio value is live mark-to-market on read
  - useful when you want holdings price movement reflected even without new trades

## Local Dev (without Docker)

### Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r api/requirements.txt
TRADER_ENGINE_DIR=$(pwd)/api/trader_engine TRADER_DATA_DIR=$(pwd)/api/data uvicorn app.main:app --app-dir api --reload --port 8000
```

### Frontend

```bash
cd web
npm install
npm run dev
```
