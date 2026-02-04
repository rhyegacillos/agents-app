# Autonomous Trader Architecture Diagrams

This companion doc visualizes the architecture described in `ARCHITECTURE.md`.

## 1) System Context

```mermaid
flowchart LR
    user[User Browser] -->|HTTP :8000| app[Single Container App]
    app --> fastapi[FastAPI API<br/>api/app/main.py]
    app --> static[Static Next.js Export<br/>api/static]
    fastapi --> engine[Trader Engine<br/>api/trader_engine]
    engine --> data[(SQLite + Memory DBs<br/>api/data)]
    engine --> polygon[Polygon API]
    engine --> llm[LLM Providers<br/>OpenAI / DeepSeek / Gemini / Grok]
    engine --> mcp[MCP Tool Servers<br/>uvx / npx / stdio]
```

## 2) Deployment Topology (Single Docker Image)

```mermaid
flowchart TB
    subgraph build[Docker Build]
        n1[Stage 1: node:22-alpine<br/>Build Next.js static export]
        n2[Stage 2: python:3.12-slim<br/>Install API + engine deps]
        n1 --> n2
    end

    subgraph runtime[Runtime Container :8000]
        f[Uvicorn + FastAPI]
        s[Mounted static frontend<br/>/app/api/static]
        e[Trader engine modules<br/>/app/api/trader_engine]
        d[Persistent data volume<br/>/app/api/data]
    end

    build --> runtime
    f --> s
    f --> e
    e --> d
```

## 3) Backend Layering (`api/app`)

```mermaid
flowchart TD
    main[main.py<br/>Routes + app wiring] --> svc1[trader_service.py]
    main --> svc2[scheduler_service.py]
    main --> svc3[market_service.py]

    svc1 --> repo[trader_repository.py]
    svc3 --> repo

    repo --> loader[engine_loader.py]
    loader --> cfg[core/config.py]
    loader --> eng[(Imported modules in api/trader_engine)]
```

## 4) API Endpoint Map

```mermaid
flowchart LR
    subgraph API[FastAPI Endpoints]
      h[GET /health]
      t1[GET /api/traders]
      t2[GET /api/traders/{name}]
      t3[GET /api/traders/{name}/logs]
      s1[POST /api/scheduler/start]
      s2[POST /api/scheduler/stop]
      s3[GET /api/scheduler/status]
      m1[GET /api/market/status]
      r1[POST /api/reset]
    end

    t1 --> traderSvc[trader_service]
    t2 --> traderSvc
    t3 --> traderSvc
    r1 --> traderSvc

    s1 --> schedSvc[scheduler_service]
    s2 --> schedSvc
    s3 --> schedSvc

    m1 --> marketSvc[market_service]
    marketSvc --> traderRepo[trader_repository]

    traderSvc --> traderRepo
    traderRepo --> engine[api/trader_engine/*]
```

## 5) Dashboard Refresh Sequence

```mermaid
sequenceDiagram
    autonumber
    participant UI as Next.js Dashboard
    participant API as FastAPI
    participant Svc as Services
    participant Repo as Repository
    participant Eng as Trader Engine
    participant DB as SQLite

    UI->>API: GET /api/traders
    API->>Svc: list_trader_summaries()
    Svc->>Repo: get_trader_definitions() + get_trader_account()
    Repo->>Eng: import trading_floor/accounts
    Eng->>DB: read account + compute report
    DB-->>Eng: account JSON
    Eng-->>Repo: account report
    Repo-->>Svc: structured rows
    Svc-->>API: TraderListResponse
    API-->>UI: traders[]

    UI->>API: GET /api/scheduler/status
    API-->>UI: running/pid/started_at

    UI->>API: GET /api/market/status
    API->>Svc: get_market_status()
    Svc->>Repo: is_market_open()
    Repo->>Eng: market.is_market_open()
    Eng-->>Repo: bool or exception
    Repo-->>Svc: open/closed
    API-->>UI: MarketStatus

    UI->>API: GET /api/traders/{name}
    API->>Svc: get_trader_detail(name)
    Svc->>Repo: get_trader_account + get_trader_logs
    Repo->>DB: read account + logs
    API-->>UI: TraderDetail
```

## 6) Scheduler Start/Stop Sequence

```mermaid
sequenceDiagram
    autonumber
    participant UI as Dashboard
    participant API as FastAPI
    participant SM as SchedulerManager
    participant P as Child Process trading_floor.py

    UI->>API: POST /api/scheduler/start
    API->>SM: start()
    alt already running
        SM-->>API: current status
    else not running
        SM->>P: spawn python trading_floor.py
        SM-->>API: running=true, pid, started_at
    end
    API-->>UI: SchedulerStatus

    UI->>API: POST /api/scheduler/stop
    API->>SM: stop()
    SM->>P: terminate (then kill fallback)
    SM-->>API: running=false
    API-->>UI: SchedulerStatus
```

## 7) Trading Tick Internals

```mermaid
flowchart TD
    tick[trading_floor.run_every_n_minutes] --> check{Market open<br/>or override?}
    check -->|No| sleep[Sleep N minutes]
    check -->|Yes| all[Run all traders concurrently]

    all --> tw[Trader Warren]
    all --> tg[Trader George]
    all --> tr[Trader Ray]
    all --> tc[Trader Cathie]

    subgraph traderLoop[Per Trader]
        a1[Start MCP servers]
        a2[Fetch account + strategy resources]
        a3[Build trade/rebalance prompt]
        a4[Runner.run agent]
        a5[Tool/resource calls]
        a6[Persist account/log updates]
    end

    tw --> traderLoop
    tg --> traderLoop
    tr --> traderLoop
    tc --> traderLoop

    traderLoop --> sleep
```

## 8) MCP Server Graph

```mermaid
flowchart LR
    trader[Trader Agent] --> tmcp[Trader MCP Server Set]
    trader --> rmcp[Researcher MCP Server Set]

    tmcp --> acc[accounts_server.py]
    tmcp --> mkt[market_server.py OR mcp_massive]

    rmcp --> fetch[mcp-server-fetch via uvx]
    rmcp --> brave[@modelcontextprotocol/server-brave-search via npx]
    rmcp --> memory[mcp-memory-libsql via npx]

    acc --> db[(accounts.db)]
    mkt --> poly[Polygon API]
    memory --> memdb[(api/data/memory/*.db)]
```

## 9) Data Model Overview

```mermaid
erDiagram
    ACCOUNTS {
      text name PK
      text account_json
    }

    LOGS {
      int id PK
      text name
      datetime datetime
      text type
      text message
    }

    MARKET {
      text date PK
      text data_json
    }

    ACCOUNTS ||--o{ LOGS : "emits events for"
```

## 10) Frontend Component/Data Flow

```mermaid
flowchart TD
    page[web/app/page.tsx] --> apiClient[web/lib/api.ts]
    page --> chart[PortfolioLineChart]

    apiClient --> e1[/GET /api/traders/]
    apiClient --> e2[/GET /api/traders/{name}/]
    apiClient --> e3[/GET /api/scheduler/status/]
    apiClient --> e4[/GET /api/market/status/]
    apiClient --> e5[/POST /api/scheduler/start|stop/]
    apiClient --> e6[/POST /api/reset/]

    e2 --> chart
    chart --> marks[Buy/Sell markers]
    chart --> axes[Date X-axis + Amount Y-axis]
```

## 11) Failure Handling Paths

```mermaid
flowchart TD
    start[Researcher MCP startup] --> ok{Server starts?}
    ok -->|Yes| use[Use server normally]
    ok -->|No| disable[Add command signature to _BROKEN_RESEARCHER_MCP]
    disable --> skip[Skip this MCP server in future runs]
    skip --> continue[Continue trading with remaining tools]

    market[Market status check] --> mkok{Polygon call succeeds?}
    mkok -->|Yes| mopen[open/closed result]
    mkok -->|No| unknown[status=unknown + detail]
```

