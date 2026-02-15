# Roadmap: Contract-First Rewrite (No Patchwork)

Legend:
- [ ] Planned
- [~] In progress
- [x] Done

## Goal
Replace reactive post-processing with deterministic contracts:
- LLM decides intent.
- Server executes tools.
- Server renders final output from canonical results.
- Truth gate validates only; it does not rewrite user-facing content.

## Phase 1 — Contract Freeze
- [x] 1.1 Define intent contract (`chat_prose`, `tool_action`, `needs_retry`, `blocked`)
- [x] 1.2 Define canonical artifact/outcome schema (PDF/email/search)
- [x] 1.3 Define citation/source schema (claim -> source URL mapping)
- [x] 1.4 Freeze acceptance criteria and error codes

## Phase 2 — Instruction Simplification
- [x] 2.1 Rewrite tool instructions to intent-only behavior
- [x] 2.2 Remove hardcoded procedural text and fragile “self-repair” prose directives
- [x] 2.3 Keep only enforceable constraints (schema, required fields, retry budget)

## Phase 3 — Truth Gate Rewrite
- [x] 3.1 Replace mutation-heavy truth gate with deterministic validator
- [x] 3.2 Truth gate outputs only pass/block + machine-readable reasons
- [x] 3.3 Remove regex-based content rewriting in gate path

## Phase 4 — Canonical Rendering
- [x] 4.1 Add server renderer for chat output templates
- [x] 4.2 Add server renderer for email bodies (clickable canonical links only)
- [x] 4.3 Add server renderer for PDF export payload handoff
- [x] 4.4 Ensure all links in final output come from canonical tool results

## Phase 5 — Retry Policy
- [x] 5.1 Retry malformed PDF input by re-calling LLM once with strict constraints
- [x] 5.2 No local JSON auto-repair for semantic payloads
- [x] 5.3 If retry fails, return structured error with trace id and reason

## Phase 6 — Verification and Rollout
- [x] 6.1 Add regression tests from real failures (invalid link, missing citation URL, page-count claim, malformed JSON)
- [x] 6.2 Add traceability logs per phase (`classify`, `execute`, `validate`, `render`)
- [x] 6.3 Gate rollout behind feature flags and run side-by-side comparison
- [x] 6.4 Remove legacy patch paths after parity is proven

## Non-Negotiables
- Do not invent links.
- Do not claim unverified actions.
- Do not mutate facts during repair.
- No placeholder tokens in user-visible output.
- Any citation-like claim in high-risk research output must include a canonical URL.
