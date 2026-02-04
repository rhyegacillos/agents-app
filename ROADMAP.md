# Roadmap: Holdings-Only Market Trend Chart

## Status

- Planned (not implemented yet)

## 1) Purpose

The dashboard currently focuses on trader execution outcomes (buy/sell actions and portfolio results).  
This roadmap adds a **separate chart** that tracks the **market trend of current holdings only**, so users can distinguish:

- strategy impact (what agents decided to do), vs
- market drift (what prices did regardless of trading).

This is important for demos, post-trade analysis, and fair performance attribution.

## 2) Problem To Solve

Without a separate holdings-market chart, users may misread portfolio moves:

- "Did PnL improve because the agent traded well?"
- or "Did prices rise for everything it already held?"

Current pain points:

- Hard to explain attribution in interviews/demos.
- Confusion when timeline changes and no new trade happened.
- No side-by-side view of execution quality vs market direction.

## 3) Proposed Feature (Future)

Add a new panel: **Holdings Market Trend (Current Holdings)**.

What it shows:

- Each currently held symbol as a normalized line (base=100 at window start).
- Optional weighted aggregate line (weighted by current position value).
- Date/time x-axis, normalized value y-axis.
- Tooltip per point: symbol, price, normalized index, weight contribution.
- Data source metadata (Polygon mode: realtime/delayed/EOD) so users understand data recency.

What it does not show:

- Symbols not in current holdings.
- Full market benchmark universe (unless explicitly added later).

## 4) Benefits

1. **Clear attribution**: separates strategy execution from market movement.
2. **Higher trust**: users can validate if gains came from decision quality.
3. **Better UX storytelling**: cleaner "why PnL changed" narrative.
4. **Capstone strength**: demonstrates agent + market data + observability maturity.
5. **Risk insight**: concentration and co-movement become visually obvious.
6. **Provider leverage**: Polygon endpoints give structured, consistent OHLC/last-price access across symbols.

## 5) Disadvantages / Tradeoffs

1. **More API pressure** on market provider (Polygon rate limits).
2. **Data freshness limits** on free plans (delayed/EOD restrictions).
3. **More frontend complexity** (extra controls, legends, overlays).
4. **Potential confusion** if users mix this with execution chart semantics.
5. **Caching correctness work** needed to avoid noisy or inconsistent lines.
6. **Provider dependence**: endpoint behavior/limits can change and must be version-monitored.

## 6) Constraints To Design Around

- Polygon free-plan limitations (429, delayed or prior-close restrictions).
- Need stable behavior when market API is unavailable.
- Must avoid random fallback for this chart (random values hurt trust).
- Must keep current execution chart untouched and explicit about semantics.

## 7) Functional Scope

### In scope (Phase 1 roadmap)

- New holdings-market chart panel.
- Window filters (`1D`, `1W`, `1M`, `ALL`).
- Symbol legend with toggle on/off per symbol.
- Weighted aggregate overlay (toggle).
- "Data as of" timestamp + "delayed/stale" badge.

### Out of scope (for first release)

- Tick-level real-time streaming.
- Benchmark backtesting engine.
- Historical holdings reconstruction by date (point-in-time portfolio).

## 8) High-Level Implementation Plan

### Phase A: Data Model and API Contract

- Define response schema for holdings trend:
  - holdings snapshot (symbol, qty, last_price, weight)
  - series per symbol (`[{ts, price, norm}]`)
  - aggregate series (`[{ts, norm}]`)
  - metadata (`source`, `is_stale`, `as_of`, `window`)
- Add endpoint proposal:
  - `GET /api/traders/{name}/holdings-market-trend?window=1d|1w|1m|all`

### Phase B: Market Data Access + Caching

- Use server-side cache with TTL by `(symbol, window_bucket)`.
- Reuse last known valid prices on provider failure.
- Add stale-while-revalidate behavior:
  - return cached data immediately,
  - refresh in background when safe.
- Add per-request symbol batching/coalescing where possible.
- Route to Polygon endpoints by window + plan capability:
  - `1D`: intraday-capable endpoint when available; otherwise delayed/EOD fallback.
  - `1W`, `1M`, `ALL`: aggregate/daily bars to reduce request load.
- Normalize all provider payloads into one internal schema (`ts`, `price`, `source_recency`).

### Phase C: Frontend Visualization

- Add dedicated panel under timeline area (not merged into execution chart).
- Render multi-line chart (symbols + optional aggregate).
- Add clear chart subtitle:
  - "Tracks market movement of current holdings, not trade execution."
- Add hover tooltip card with full data point details.

### Phase D: Reliability and UX Guardrails

- Never use random fallback in this chart.
- If market data unavailable:
  - show last cached value,
  - label as stale,
  - keep UI responsive.
- Add graceful empty state when no holdings exist.

### Phase E: Testing and Validation

- Unit tests:
  - normalization math,
  - weighting math,
  - cache hit/miss + expiry behavior.
- API tests:
  - valid windows,
  - stale responses,
  - market provider outage behavior.
- UI tests:
  - filter interactions,
  - legend toggles,
  - tooltip formatting.

## 9) Key Risks and Mitigations

- **Risk:** Polygon quota exceeded (`429`).  
  **Mitigation:** aggressive cache TTL, deduped requests, scheduled refresh intervals.

- **Risk:** Users assume real-time precision.  
  **Mitigation:** "Delayed market data" label + "as of" timestamp.

- **Risk:** Confusion with existing execution chart.  
  **Mitigation:** explicit panel titles and help tooltip that explains chart differences.

## 10) Success Criteria

Feature is successful if:

1. Users can explain "strategy vs market" effect using two charts.
2. Holdings market chart remains stable under API failures (stale fallback works).
3. No random data appears in holdings market chart.
4. Median API response stays fast with cache enabled.
5. UI remains readable with up to 15 held symbols.

## 11) Future Extensions (After Phase 1)

- Benchmark overlays (`SPY`, `QQQ`) for excess-return context.
- Point-in-time holdings trend (historical holdings composition).
- Sector grouping and factor decomposition.
- Trade annotation overlay directly on holdings market chart.
- Export report (PNG/CSV) for interview/capstone artifacts.

## 12) Polygon Integration Plan (How It Solves Drawbacks + Improves Performance)

This section explains how Polygon specifically helps make the feature practical despite free-plan constraints.

### 12.1 Purpose of Polygon in this roadmap

- Provide consistent per-symbol market prices for currently held positions.
- Avoid random/fake movement in the holdings trend chart.
- Enable time-windowed trend data (`1D`, `1W`, `1M`, `ALL`) using one provider contract.

### 12.2 Drawbacks addressed by planned Polygon design

1. **429/rate-limit spikes**
   - Use request coalescing (same symbol/window requests collapse into one upstream call).
   - Use multi-layer cache:
     - in-memory hot cache for active symbols,
     - SQLite/shared cache for cross-request reuse.
   - Add cooldown after repeated upstream errors to prevent retry storms.

2. **Free-plan delayed/EOD limitations**
   - Expose recency explicitly (`realtime`, `delayed`, `prior-close`) in API response.
   - Show recency badge + "as of" timestamp in chart UI.
   - Choose lower-frequency endpoints for longer windows to reduce both staleness confusion and call volume.

3. **Data gaps or transient provider errors**
   - Fallback order:
     1) latest valid cached value
     2) stale cached series with warning
     3) explicit "data unavailable" state
   - No random-number fallback for this chart.

4. **Chart trust issues due to hidden data quality**
   - Attach source metadata per series.
   - Add legend-level stale marker so users know which symbol line is delayed.

### 12.3 Performance architecture using Polygon

- **Request budgeting:** one upstream pull per unique `(symbol, window, bucket)` during TTL.
- **Batch refresh policy:** refresh only visible symbols (current holdings), not global watchlists.
- **Incremental updates:** append newest points instead of reloading full series when possible.
- **Background refresh:** serve cached result first, refresh async, then update UI.
- **Window-aware TTL examples:**
  - `1D`: short TTL (fresher UX)
  - `1W`/`1M`: medium TTL
  - `ALL`: longer TTL (historical data changes rarely)

### 12.4 API contract additions for transparency and speed

Proposed fields in `GET /api/traders/{name}/holdings-market-trend`:

- `source`: `polygon`
- `source_mode`: `realtime | delayed | prior_close`
- `as_of`: timestamp of newest point returned
- `is_stale`: boolean
- `cache_hit_ratio`: optional debug metric (non-production UI toggle)

Benefit:
- Users and operators can quickly distinguish "slow API" from "stale but valid cached data."

### 12.5 Expected performance gains

With the above design:

- Lower p95 API latency for trend endpoint under repeated dashboard refresh.
- Lower upstream request count per minute.
- More stable chart behavior during provider throttling.
- Better perceived responsiveness because cached data renders immediately.

### 12.6 Future plan evolution

- If upgraded to higher Polygon tiers, reuse same contract and only switch recency mode.
- Keep UI unchanged; only source recency badge and freshness improve.
- Optionally add benchmark overlays using same cached provider pipeline.

## 13) Polygon Plan Cost, Recommendation, and Upgrade Path

Pricing changes over time. Numbers below are documented from provider pricing pages as of **2026-02-04**.

### 13.1 Individual plan ladder (Stocks)

- **Basic**: USD 0/month
  - 5 requests/minute
  - End-of-day oriented usage
- **Starter**: USD 29/month
  - delayed market data (15-minute)
  - higher throughput for app workloads
- **Developer**: USD 79/month
  - delayed market data (15-minute)
  - longer historical coverage than Starter
- **Advanced**: USD 199/month
  - real-time stocks data
  - trades/quotes + stronger intraday capabilities

### 13.2 Business plan ladder (Stocks)

- **Business**: USD 1,999/month
  - business-use oriented plan with real-time fair market value and broader commercial posture
- **Enterprise**: custom pricing
  - SLA and tailored exchange/feed options

### 13.3 Recommended plan by stage for this project

1. **Development and capstone demo (low budget): Basic**
   - Use strict-flat mode, caching, and lower refresh frequency.
   - Best when goal is architecture demo, not real-time fidelity.

2. **Demo with better responsiveness: Starter (recommended minimum paid)**
   - Biggest practical improvement per dollar for dashboard smoothness.
   - Reduces 429 pain versus free tier and supports delayed near-live UX.

3. **Backtesting and richer history analysis: Developer**
   - Same delayed recency class as Starter, but better for deeper historical trend windows.

4. **Real-time operator experience: Advanced**
   - Enables truly reactive holdings-market chart behavior.
   - Supports higher-confidence intraday mark-to-market experiences.

5. **Commercial multi-user product: Business/Enterprise**
   - Needed when usage rights, reliability guarantees, and scaling commitments become contractual requirements.

### 13.4 What each upgrade unlocks in this roadmap

- **Basic -> Starter**
  - Higher practical request capacity and delayed streaming/snapshot style workflows.
  - Enables more frequent chart refresh and better multi-symbol holdings updates.

- **Starter -> Developer**
  - More historical depth for trend analytics.
  - Enables more convincing long-window comparisons and feature engineering.

- **Developer -> Advanced**
  - Real-time data path.
  - Enables tighter polling/stream cadence, lower staleness, and better intraday anomaly detection.

- **Advanced -> Business/Enterprise**
  - Enterprise-grade posture (support model, governance, and feed customization).
  - Enables safer external-user productization and contractual uptime expectations.

### 13.5 Drawback resolution by plan tier

- **Main drawback: 429/rate pressure**
  - Basic: must rely heavily on cache and coarse refresh.
  - Paid tiers: easier to maintain responsive holdings trend with fewer throttling interruptions.

- **Main drawback: delayed data**
  - Starter/Developer remain delayed.
  - Advanced and above solve this with real-time path.

- **Main drawback: production reliability expectations**
  - Individual tiers are excellent for development and single-user operation.
  - Business/Enterprise better align for team and external customer expectations.

### 13.6 Implementation profile by plan (proposed defaults)

- **Basic**
  - `STRICT_FLAT_WHEN_NO_TRADE=true`
  - trend endpoint TTL: longer
  - refresh cadence: slower

- **Starter / Developer**
  - `STRICT_FLAT_WHEN_NO_TRADE` optional (depends on UX preference)
  - medium TTL
  - moderate refresh cadence

- **Advanced / Business**
  - `STRICT_FLAT_WHEN_NO_TRADE=false` viable for live mark-to-market UX
  - shorter TTL + optional streaming path
  - near-real-time updates with stale fallback guardrails

## 14) Pricing and Capability Sources

- Massive pricing (individual tiers): https://massive.com/pricing
- Massive business stocks pricing: https://massive.com/business-stocks
- Polygon/knowledge base request limits: https://polygon.io/knowledge-base/article/what-is-the-request-limit-for-polygons-restful-apis
