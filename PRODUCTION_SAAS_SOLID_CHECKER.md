# Production SaaS Solid Checker

Use this checklist to decide when IdeaGen is ready for public, paid usage.
This is a release gate document, not a roadmap. Every "Must" item should be
completed before broad monetized launch.

---

## 1) How to Use This Checker

Run this checker at three points:

1. Pre-launch (before enabling paid subscriptions publicly)
2. Every release candidate
3. Monthly operations review

Use the status values:

- `PASS`: Implemented and verified with evidence
- `PARTIAL`: Implemented but missing verification, coverage, or hardening
- `FAIL`: Not implemented
- `N/A`: Not applicable for current release

Evidence can be links to:

- test output,
- dashboards,
- runbooks,
- incident drills,
- screenshots,
- config snapshots,
- PRs.

---

## 2) Launch Gate Levels

### Gate A - Public Demo (non-critical)

- Public URL, TLS, basic auth, basic limits, and core flow works.

### Gate B - Private Beta (limited customers)

- All Gate A + backup/restore tested, alerting in place, support process exists.

### Gate C - Paid GA (monetized public)

- All Gate B + durable data architecture, billing reliability, legal/compliance baseline, incident readiness.

### Gate D - Scale Ready

- All Gate C + SLOs consistently met, capacity planning, load tests, cost optimization controls.

For paid public rollout, **minimum required gate is Gate C**.

---

## 3) Hard Requirements (Must Pass for Monetized Public Launch)

## 3.1 Product Reliability

- [ ] Core flow always works: Generate -> Compare -> Decision -> Execution Plan
- [ ] Empty states, loading states, and error states are user-safe and actionable
- [ ] Long-running actions have timeout + retry strategy
- [ ] Client-side crashes are captured and monitored
- [ ] API error contract is consistent (stable status codes + response shape)

Evidence:

- [ ] End-to-end test run for core flow in production-like environment
- [ ] Error tracking dashboard screenshot (last 7 days)

## 3.2 Data Durability and Recovery

- [ ] Production data is stored in durable managed storage (not ephemeral container FS)
- [ ] Automated backups exist and are verified
- [ ] Restore procedure tested and documented
- [ ] Data retention policy defined (runs/reports/logs)
- [ ] Destructive actions support confirmation and auditability

Evidence:

- [ ] Backup schedule + retention config
- [ ] Successful restore drill timestamp and notes

## 3.3 Security Baseline

- [ ] Auth + authorization boundaries verified for all write/read endpoints
- [ ] Host allowlist and trusted origin checks configured for production
- [ ] Secrets stored in managed secret/env system (never hardcoded)
- [ ] Rate limiting and abuse controls enforced
- [ ] Input validation and output encoding across user-controlled data paths

Evidence:

- [ ] Security review checklist signed
- [ ] Pen-test or structured abuse test report (internal is acceptable initially)

## 3.4 Billing and Entitlements

- [ ] Plan enforcement is server-side authoritative
- [ ] Subscription webhook handling is idempotent
- [ ] Upgrade/downgrade/cancel flows tested end-to-end
- [ ] Usage counters are accurate and reset behavior is deterministic
- [ ] Billing failures do not corrupt entitlement state

Evidence:

- [ ] Billing lifecycle test matrix with pass/fail
- [ ] Webhook replay test proof

## 3.5 Observability and Operations

- [ ] Structured logs with request IDs and user-safe context
- [ ] Metrics and alerts for API errors, latency, job failures, billing failures
- [ ] On-call runbook exists for high-severity incidents
- [ ] Health endpoint and readiness checks are monitored
- [ ] Deploy rollback process tested

Evidence:

- [ ] Alert policy snapshot
- [ ] Incident drill notes (at least one simulation)

## 3.6 Legal and Trust Baseline

- [ ] Terms of Service published
- [ ] Privacy Policy published
- [ ] Data processing statement and contact channel published
- [ ] Export/email disclaimers for generated content included
- [ ] Security contact and support contact visible

Evidence:

- [ ] Public URLs to legal docs
- [ ] In-app footer/help links verified

---

## 4) Strongly Recommended (Should Pass Within First 30 Days of GA)

## 4.1 Quality Engineering

- [ ] Unit tests for key business logic (compare, decision generation, plan gating)
- [ ] Integration tests for API contracts
- [ ] E2E tests for all major user paths
- [ ] Regression suite in CI for each release

## 4.2 Performance and Capacity

- [ ] P95 latency target defined per key endpoint
- [ ] Load test run with expected concurrency
- [ ] Capacity threshold alerts configured
- [ ] Background tasks/jobs profiled for cost and latency

## 4.3 Anti-Abuse and Cost Protection

- [ ] Per-user/day/month limits tuned for pricing model
- [ ] Bot and scripted abuse detection patterns
- [ ] Circuit breaker for external model/provider failures
- [ ] Budget alerts for model/API spend

## 4.4 Customer Experience

- [ ] In-app guidance for first-time users and experts is consistent
- [ ] Support workflow for failed exports/emails exists
- [ ] "How to recover" guidance on every blocking error state
- [ ] Changelog and known issues section maintained

---

## 5) SaaS Metrics to Track (Launch Dashboard Minimum)

Track weekly at minimum:

- Activation: % users who generate first run
- Progression:
  - % who reach Compare
  - % who reach Decision
  - % who reach Execution Plan
- Reliability:
  - API error rate
  - client crash rate
  - export/email failure rate
- Monetization:
  - trial -> paid conversion
  - MRR/ARR
  - churn rate
- Cost:
  - model cost per active user
  - gross margin per plan

---

## 6) Release Readiness Sign-Off Template

Use this before each paid launch or major change:

| Area | Owner | Status | Evidence | Notes |
|---|---|---|---|---|
| Product reliability |  |  |  |  |
| Data durability/recovery |  |  |  |  |
| Security baseline |  |  |  |  |
| Billing/entitlements |  |  |  |  |
| Observability/operations |  |  |  |  |
| Legal/trust baseline |  |  |  |  |
| Performance/capacity |  |  |  |  |
| Anti-abuse/cost controls |  |  |  |  |

Final decision:

- [ ] Approve launch
- [ ] Approve with risk acceptance
- [ ] Block launch

Approver: ____________________  
Date: ____________________

---

## 7) IdeaGen-Specific Notes (Current Stack Implications)

- If running on App Runner with ephemeral containers, local SQLite is not
  sufficient for paid production durability. Move persistent data to managed
  storage (for example PostgreSQL/RDS) before Gate C.
- Keep `ALLOWED_HOSTS` set to production domain(s) and verify health-check path
  behavior after each deployment.
- Keep server-side usage enforcement authoritative; UI limits are guidance only.

---

## 8) Suggested Minimum Definition of "Production SaaS Solid"

IdeaGen is "production SaaS solid" when:

1. All section 3 items are `PASS`
2. No unresolved P1/P2 incident from the last 14 days
3. Backup restore drill succeeded in the last 30 days
4. Billing lifecycle test matrix is fully passing
5. Reliability metrics are within agreed thresholds for two consecutive weeks

