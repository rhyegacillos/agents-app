# MVP Live Trading Plan and Cost Model

This document explains how to move this project from simulation to a real-money MVP, including:

- required subscriptions,
- premium-tier options,
- estimated monthly cost ranges,
- what each upgrade unlocks.

All prices are time-sensitive. Estimates below are based on publicly posted pricing as of **2026-02-04** and should be re-checked before purchase.

---

## 1) Scope of "Live Trading MVP"

For this project, "live trading MVP" means:

1. Strategy decisions come from the current agent pipeline.
2. Orders execute through a real broker API (real money).
3. Positions/cash are synced from broker account state.
4. Risk limits block unsafe orders.
5. Dashboard remains operator-facing (monitor + controlled actions).

Non-goals for MVP:
- HFT/ultra-low-latency trading
- multi-region active-active deployment
- enterprise compliance automation

---

## 2) Cost Components (What You Actually Pay For)

## 2.1 Market data provider (Polygon/Massive)

Individual stocks plans (published):
- **Basic**: USD 0/mo (5 req/min, EOD-oriented usage)
- **Starter**: USD 29/mo (delayed data)
- **Developer**: USD 79/mo (delayed data + more history)
- **Advanced**: USD 199/mo (real-time data)

Business plans:
- **Business Stocks** starts around USD 1,999/mo
- **Enterprise** custom

Why this matters:
- This is the main lever for freshness and rate-limit stability.
- Free works for demos, but paid plans materially reduce throttling pain.

## 2.2 LLM inference cost

This app runs frequent multi-agent cycles, so token usage becomes recurring OpEx.

Use this formula:

`monthly_llm_cost = (input_tokens_m / 1,000,000 * input_price) + (output_tokens_m / 1,000,000 * output_price)`

Where:
- `input_tokens_m` and `output_tokens_m` are monthly totals across all agents.
- model prices depend on your selected model(s).

Practical expectation for this app:
- low activity (hourly cycles, compact prompts): roughly **USD 10-40/mo**
- medium activity (more tools/log context): roughly **USD 40-150/mo**
- high activity (short cycles + heavier prompts): **USD 150+/mo**

## 2.3 Search/research APIs (optional but useful)

Brave Search API pricing includes:
- free tier (limited monthly quota),
- paid tiers (example: base and pro tiers priced per 1,000 requests).

Why this matters:
- research sub-agent quality improves with search depth.
- cost scales with request volume, not trading capital.

## 2.4 Broker layer

Real broker costs depend on provider and market:
- commissions/spread/slippage,
- regulatory/exchange fees,
- premium data/add-ons if enabled.

For MVP planning, treat broker cost as:
- **fixed subscription**: often low/none for API access
- **variable execution cost**: grows with turnover and order count

## 2.5 Cloud hosting (EC2 + storage + logs)

Expected monthly categories:
- EC2 instance runtime
- EBS disk
- CloudWatch logs/metrics
- data transfer

For one-instance MVP (always-on):
- small instance profile: roughly **USD 20-70/mo** total infra range (region + traffic dependent)
- medium profile with heavier logging: roughly **USD 70-180/mo**

Use AWS Pricing Calculator for exact region-specific totals.

---

## 3) Recommended Subscription Paths

## Path A: "Capstone + guarded live pilot" (minimum paid)

Recommended stack:
- Polygon/Massive: **Starter (USD 29/mo)**
- LLM budget: **USD 20-80/mo**
- Optional Brave paid search: **USD 0-50/mo**
- Cloud: **USD 20-70/mo**

Estimated monthly total:
- **USD 69-229/mo**

Use when:
- you want better-than-free reliability,
- still cost-sensitive,
- okay with delayed market data.

## Path B: "Serious real-time MVP"

Recommended stack:
- Polygon/Massive: **Advanced (USD 199/mo)**
- LLM budget: **USD 50-200/mo**
- Optional Brave paid search: **USD 20-150/mo**
- Cloud: **USD 70-180/mo**

Estimated monthly total:
- **USD 339-729/mo**

Use when:
- you need real-time-ish operator experience,
- want fewer provider bottlenecks,
- plan to demo to stakeholders/users regularly.

## Path C: "Commercial / team-facing premium"

Recommended stack:
- Polygon/Massive: **Business/Enterprise (USD 1,999+/mo)**
- LLM budget: **USD 200+/mo** (depends on volume)
- Cloud + observability hardening: **USD 200+/mo**
- security/compliance overhead (tooling/legal): variable

Estimated monthly total:
- **USD 2,500+/mo** (can be much higher depending on scale/compliance)

Use when:
- external users depend on uptime/SLA,
- contractual/compliance posture is required.

---

## 4) What You Gain by Upgrading Plans

## 4.1 Polygon/Massive upgrades

- **Basic -> Starter**
  - fewer throttling issues vs free tier
  - better dashboard freshness (delayed but usable)

- **Starter -> Developer**
  - better historical depth for analytics windows
  - stronger historical chart features

- **Developer -> Advanced**
  - real-time data access path
  - cleaner intraday monitoring and risk reaction

- **Advanced -> Business/Enterprise**
  - stronger commercial posture and scalability expectations
  - better fit for productized multi-user deployment

## 4.2 Infrastructure upgrades

- `t3.small -> t3.medium+`
  - reduced hangs under concurrent agent/tool load
  - faster dashboard/API response under heavy polling

- single EC2 -> managed/containerized production stack
  - cleaner deployments, safer rollbacks, better scaling controls

## 4.3 LLM budget upgrades

- higher budget lets you:
  - keep richer context windows,
  - run more frequent cycles,
  - increase research depth per run.

Tradeoff:
- cost grows with prompt size, run frequency, and tool chatter.

---

## 5) MVP Build Sequence (Cost-Aware)

1. Start with **Path A** and strict controls:
   - `READ_ONLY_MODE=true` for public-facing monitoring
   - conservative `RUN_EVERY_N_MINUTES` (e.g., 30-60)
2. Enforce risk gates before scaling volume:
   - max position size, max daily loss, kill switch
3. Measure 2 weeks of:
   - fill quality,
   - PnL consistency,
   - LLM + data API spend
4. Upgrade data plan only when blocked by:
   - stale/delayed decisions,
   - frequent throttling,
   - stakeholder requirement for real-time views
5. Upgrade infra once CPU/memory and API latency become a bottleneck

---

## 6) Budgeting Checklist (Monthly)

- [ ] Market data subscription selected
- [ ] LLM spend cap set (soft + hard alert thresholds)
- [ ] Broker execution fee model estimated
- [ ] EC2/EBS/logging transfer estimated
- [ ] Search API quota + budget set
- [ ] "No trade" fallback semantics documented in UI
- [ ] Monitoring alerts configured for runaway costs

---

## 7) Sources (Pricing/Plans)

- Massive/Polygon pricing: https://massive.com/pricing
- Massive business stocks pricing: https://massive.com/business-stocks
- Polygon request-limit guidance: https://polygon.io/knowledge-base/article/what-is-the-request-limit-for-polygons-restful-apis
- OpenAI API pricing: https://platform.openai.com/pricing
- Brave Search API pricing: https://brave.com/search/api/
- AWS pricing calculator: https://calculator.aws/

---

## 8) Notes

- These are planning estimates, not invoices.
- Real trading adds execution costs (slippage/fees) that can exceed API costs for high turnover strategies.
- Do paper trading and strict risk controls first before increasing live capital.
