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

## API Endpoints

- `GET /health`
- `GET /api/traders`
- `GET /api/traders/{name}`
- `GET /api/traders/{name}/logs?limit=50`
- `GET /api/scheduler/status`
- `POST /api/scheduler/start`
- `POST /api/scheduler/stop`
- `POST /api/reset`

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
If fetch MCP emits noisy BrokenPipe shutdown traces, they are now suppressed by default wrapper command.

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
