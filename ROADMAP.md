# Digital Assistant Roadmap

This document tracks planned capabilities and delivery status.

Legend:
- [ ] Planned
- [~] In progress
- [x] Done

## Phase 1 — Core Agent UX
- [x] Conversation history polish (drawer UX, refresh, empty states) — done: 2026-02-07
- [x] History + memory panel animations and hover polish — done: 2026-02-07
- [x] Streaming status indicators (searching/generating) with animation — done: 2026-02-07
- [x] Chat panel expand/collapse controls + max height guard — done: 2026-02-07
- [ ] Session summaries (auto‑generate short summary after each chat)
- [ ] Prompt modes (concise / detailed / tutor)
- [ ] Better error UI (timeouts, retries, provider unavailable)
- [ ] Evaluation mode (self‑audit: confidence, known unknowns, next questions)

## Phase 2 — Memory + Retrieval
- [x] Long‑term memory store (approved preferences) — done: 2026-02-07
- [x] Memory candidate extraction + approval workflow — done: 2026-02-07
- [x] Memory conflict detection on approval (model‑decided) — done: 2026-02-07
- [x] Approved memory injection into system prompt — done: 2026-02-07
- [ ] RAG pipeline (docs ingestion + retrieval)
- [ ] Knowledge base indexing (S3/Notion/GitHub)
- [ ] RAG with citations from KB (not open web)
- [ ] Auto‑refresh KB from repo/drive changes
- [ ] Source citations in responses
- [~] Memory controls (clear, export, per‑topic)

## Phase 3 — Tooling + Automation
- [x] Tool calling framework (MCP servers) — done: 2026-02-07
- [x] Web search tool (Brave MCP + strict policy) — done: 2026-02-07
- [x] PDF export tool (chat content → PDF) — done: 2026-02-07
- [x] Email tool (Resend MCP) — done: 2026-02-07
- [x] File upload tool (upload + summarize) — done: 2026-02-07
- [ ] Chart/diagram image generation (charts, graphs, flowcharts only)
- [ ] File intelligence: citation‑aware summaries (quotes + page refs)
- [ ] File intelligence: multi‑file compare (diff/merge/consensus)
- [ ] Task plans + progress tracking
- [ ] Task mode: structured checklist with milestones + ownership
- [ ] Task mode: task board output (JSON/CSV)
- [ ] Tool result caching + cooldowns
- [ ] Tool routing guardrails: confidence threshold + ask‑before‑call
- [ ] Multi‑provider fallback (Grok ↔ Bedrock)

## Phase 4 — Observability + Cost
- [ ] Trace IDs per request
- [ ] Metrics dashboard (latency, errors, token/cost)
- [ ] Budget alerts (daily/weekly caps)
- [ ] Audit log for tool calls
- [ ] Admin view for failures + slow queries

## Phase 5 — Security + Multi‑user
- [ ] Authentication (email/OAuth)
- [x] Per‑user data isolation (user_id scoped history + memory) — done: 2026-02-07
- [ ] Role‑based access control (admin/user)
- [ ] Workspace / tenant support

## Notes
- Keep roadmap items small and shippable.
- Move items between phases as priorities change.
