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

- “Did PnL improve because the agent traded well?”
- or “Did prices rise for everything it already held?”

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

What it does not show:

- Symbols not in current holdings.
- Full market benchmark universe (unless explicitly added later).

## 4) Benefits

1. **Clear attribution**: separates strategy execution from market movement.
2. **Higher trust**: users can validate if gains came from decision quality.
3. **Better UX storytelling**: cleaner “why PnL changed” narrative.
4. **Capstone strength**: demonstrates agent + market data + observability maturity.
5. **Risk insight**: concentration and co-movement become visually obvious.

## 5) Disadvantages / Tradeoffs

1. **More API pressure** on market provider (Polygon rate limits).
2. **Data freshness limits** on free plans (delayed/EOD restrictions).
3. **More frontend complexity** (extra controls, legends, overlays).
4. **Potential confusion** if users mix this with execution chart semantics.
5. **Caching correctness work** needed to avoid noisy or inconsistent lines.

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
- “Data as of” timestamp + “delayed/stale” badge.

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

### Phase C: Frontend Visualization

- Add dedicated panel under timeline area (not merged into execution chart).
- Render multi-line chart (symbols + optional aggregate).
- Add clear chart subtitle:
  - “Tracks market movement of current holdings, not trade execution.”
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
  **Mitigation:** “Delayed market data” label + “as of” timestamp.

- **Risk:** Confusion with existing execution chart.  
  **Mitigation:** explicit panel titles and help tooltip that explains chart differences.

## 10) Success Criteria

Feature is successful if:

1. Users can explain “strategy vs market” effect using two charts.
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
