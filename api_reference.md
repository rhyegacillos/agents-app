# API Reference

Base URL: `/api`
Auth: Clerk bearer token in `Authorization: Bearer <token>`

## Documentation Sync: Adaptive Decision Flow + Step Guide (2026-02-20)

This document is synchronized with the latest UX/flow implementation in `pages/product.tsx`.

- **Adaptive flow modes**: UI now shifts between `guided` and `status` modes.
- **Hysteresis guard**: mode switching uses `guided -> status` at `<= 40` and `status -> guided` at `>= 60` to avoid flip-flop around a single threshold.
- **Persistent Step Guide**: every workspace step includes a structured guide panel (`What you do`, `What you get`, `When to use`, `To move forward`).
- **Per-step memory**: collapse/expand is saved per user and per step using local storage (`collapsedByStep`, `touchedByStep`).
- **Adaptive Step Guide defaults**: untouched guides auto-expand in guided mode and auto-collapse in status mode.
- **User override priority**: once a user manually toggles a step guide, that preference is preserved and not auto-overridden.
- **Generated empty-state scenarios**: first-time vs returning-with-library cases are explicitly separated for clearer onboarding.
- **Decision Summary behavior**: supports single-run and multi-run (1-5) synthesis; compare-first is recommended but not mandatory.
- **Compare behavior**: compares two selected saved runs and surfaces winner/diff insight; best quality when config alignment is preserved.
- **Execution handoff**: Decision Summary remains the source artifact for Execution Plan generation and export workflow.
- **Scope note**: this update is primarily frontend UX/state orchestration; backend endpoint contracts remain unchanged unless otherwise stated in backend/API docs.


## Error shape (current)
- Some endpoints return `HTTPException` with `{ "detail": "..." }`.
- Some rate-limit endpoints return `{ "error": "..." }` with HTTP 429.

---

## GET /api/subscription
Returns plan status and usage stats.

Response (200):
```json
{
  "user_id": "user_123",
  "plan": "u:free_user",
  "is_premium": false,
  "status": "active",
  "usage": {
    "total_tokens": 1200,
    "api_calls_count": 1,
    "emails_sent_count": 0
  }
}
```

---

## POST /api
Generate ideas and optional model ranking.

Request:
```json
{
  "industry": "HealthTech",
  "constraints": ["Low Startup Cost (<$5k)", "B2B SaaS"],
  "tone": "Experienced Operator",
  "models": ["openai", "gemini", "deepseek", "grok"],
  "temperature": 0.7,
  "top_p": 0.9
}
```

Response (200):
```json
{
  "results": {
    "gpt-5-mini": "<html...>",
    "gemini-2.5-pro": "<html...>"
  },
  "usage": {
    "prompt_tokens": 120,
    "completion_tokens": 480,
    "total_tokens": 600,
    "api_calls_count": 2,
    "emails_sent_count": 0
  },
  "rank_result": {
    "summary": "...",
    "ranked_models": [
      {"model_id": "gpt-5-mini", "rank": 1, "score": 85, "title": "...", "rationale": "..."}
    ],
    "highlights": ["..."],
    "title_map": {"gpt-5-mini": "..."}
  }
}
```

Errors:
- 429 if API rate limit or token limit reached.
- 502/500 if model call fails.

---

## POST /api/saved-results
Save a generated run.

Request:
```json
{
  "industry": "FinTech",
  "constraints": ["Regulated Environment"],
  "tone": "Experienced Operator",
  "models": ["openai", "gemini"],
  "results": {"gpt-5-mini": "<html...>"},
  "rank_result": {"summary": "..."}
}
```

Response (200):
```json
{"id": 12, "created_at": "2026-01-25T12:00:00+00:00"}
```

Errors:
- 400 if results are empty.
- 413 if storage limit is exceeded.

---

## GET /api/saved-results
List saved runs.

Response:
```json
{
  "results": [{"id": 12, "created_at": "...", "industry": "FinTech", "tone": "..."}],
  "usage_bytes": 102400,
  "limit_bytes": 104857600
}
```

---

## GET /api/saved-results/{id}
Load a saved run.

Response:
```json
{
  "id": 12,
  "created_at": "...",
  "industry": "FinTech",
  "tone": "...",
  "constraints": ["Regulated Environment"],
  "models": ["openai"],
  "results": {"gpt-5-mini": "<html...>"},
  "rank_result": {"summary": "..."}
}
```

Errors:
- 404 if not found.

---

## DELETE /api/saved-results/{id}
Delete a saved run.

Response:
```json
{"status": "deleted"}
```

---

## DELETE /api/saved-results
Bulk delete all saved generated runs for the current user.

Response:
```json
{"status": "deleted", "count": 6}
```

---

## POST /api/compare-results
Compare two saved runs with the same configuration.

Request:
```json
{"run_a_id": 10, "run_b_id": 11}
```

Response:
```json
{
  "comparison_id": 5,
  "created_at": "...",
  "run_a_id": 10,
  "run_b_id": 11,
  "winner_run_id": 10,
  "comparison": {
    "winner": "A",
    "summary": "...",
    "key_changes": ["..."],
    "winner_rationale": "...",
    "risks": ["..."],
    "top_outputs": {"run_a": {"title": "..."}, "run_b": {"title": "..."}}
  },
  "cached": false
}
```

Errors:
- 400 if runs are the same or configurations differ.
- 404 if run not found.

---

## GET /api/compare-results
List saved comparisons.

Response:
```json
{"comparisons": [{"id": 5, "created_at": "...", "run_a_id": 10, "run_b_id": 11}]}
```

---

## DELETE /api/compare-results
Bulk delete all saved comparisons for the current user.

Response:
```json
{"status": "deleted", "count": 4}
```

---

## DELETE /api/compare-results/{id}
Delete one saved comparison.

Response:
```json
{"status": "deleted"}
```

---

## GET /api/compare-results/{id}/pdf
Download compare report PDF.

Response:
- `application/pdf` stream with `Content-Disposition` header.

---

## POST /api/compare-results/{id}/email
Email compare report PDF.

Request:
```json
{"to_email": "user@example.com"}
```

Response:
```json
{"status": "sent"}
```

Errors:
- 502 if email delivery fails.

---

## GET /api/rank-reports
List decision summary reports.

Response:
```json
{"reports": [{"id": 7, "created_at": "...", "run_ids": [10, 11]}]}
```

---

## DELETE /api/rank-reports
Bulk delete all saved decision summary reports for the current user.

Response:
```json
{"status": "deleted", "count": 3}
```

---

## GET /api/rank-reports/{id}
Get a saved decision summary report.

Response:
```json
{"id": 7, "created_at": "...", "run_ids": [10, 11], "report": {"summary": "..."}}
```

---

## DELETE /api/rank-reports/{id}
Delete one saved decision summary report.

Response:
```json
{"status": "deleted"}
```

---

## GET /api/rank-reports/{id}/pdf
Download decision summary report PDF.

Response:
- `application/pdf` stream with `Content-Disposition` header.

---

## POST /api/rank-reports/{id}/email
Email a decision summary report PDF.

Request:
```json
{"to_email": "user@example.com"}
```

Response:
```json
{"status": "sent"}
```

---

## POST /api/rank-report
Generate a decision summary report from saved runs.

Request:
```json
{
  "run_ids": [10, 11],
  "output": "pdf",
  "email": "user@example.com",
  "include_all_runs": false
}
```

Response:
- If `output=pdf` or `both`, returns `application/pdf` stream.
- If `output=email`, returns JSON:
```json
{"status": "sent", "email_sent": true, "email_failed": false, "cached": false}
```

---

## POST /api/stakeholder-report
Create a saved Execution Plan dossier.

Request:
```json
{
  "source": {
    "mode": "decision_report",
    "decision_report_id": 42,
    "selected_run_id": 101,
    "selected_model_id": "gpt-5-nano"
  },
  "scenario_profile": "base",
  "horizon_months": 12,
  "currency": "USD",
  "region": "US",
  "output": "json",
  "finance_mode": "grounded_v2"
}
```

Response:
```json
{
  "id": 9001,
  "created_at": "2026-02-14T12:00:00+00:00",
  "status": "ready",
  "model": "gpt-5-mini",
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  },
  "dossier": { "...": "detailed execution, cost, and profit payload" }
}
```

Notes:
- Supported source modes: `decision_report`, `compare_result`, `saved_run`
- Supports only `output=json`.
- `finance_mode` options:
  - `grounded_v2` (default): deterministic financial model + narrative LLM
    - baseline from industry assumption pack
    - deterministic run-conditioned adjustment from selected run constraints/persona/output signals/model confidence
    - bounded multipliers and deterministic recomputation of projections/scenario mix
  - `llm_v1`: legacy generation path
- Currency/region currently supported: `USD` / `US`.

---

## GET /api/stakeholder-reports
List saved stakeholder reports.

Response:
```json
{
  "reports": [
    {
      "id": 9001,
      "created_at": "...",
      "source_type": "decision_report",
      "source_id": 42,
      "scenario_profile": "base",
      "horizon_months": 12,
      "currency": "USD",
      "region": "US",
      "model": "gpt-5-mini"
    }
  ]
}
```

---

## GET /api/stakeholder-reports/{id}
Get one saved stakeholder report.

Response:
```json
{
  "id": 9001,
  "created_at": "...",
  "source_type": "decision_report",
  "source_id": 42,
  "scenario_profile": "base",
  "horizon_months": 12,
  "currency": "USD",
  "region": "US",
  "model": "gpt-5-mini",
  "assumptions": [
    { "key": "selected_output_title", "value": "LedgerLatch", "unit": "label", "source": "selected ranked model output", "confidence": "high" },
    { "key": "scenario_probability_mix", "value": "conservative=0.33,base=0.49,aggressive=0.18", "unit": "mix", "source": "deterministic risk-adjusted probability rules", "confidence": "medium" }
  ],
  "dossier": {
    "decision": {},
    "decision_support": {},
    "proposal_disclaimer": {},
    "sensitivity_analysis": {},
    "provenance": {}
  }
}
```

---

## GET /api/stakeholder-reports/{id}/pdf
Download one Execution Plan PDF.

Response:
- `application/pdf` stream

---

## GET /api/stakeholder-reports/{id}/presentation
Download one Execution Plan presentation PDF deck.

Response:
- `application/pdf` stream

---

## DELETE /api/stakeholder-reports/{id}
Delete one saved stakeholder report.

Response:
```json
{"status": "deleted"}
```

---

## DELETE /api/stakeholder-reports
Delete all saved stakeholder reports for current user.

Response:
```json
{"status": "deleted", "count": 3}
```

---

## POST /api/download-pdf
Generate a PDF for the current run.

Request:
```json
{
  "industry": "FinTech",
  "constraints": ["Regulated"],
  "tone": "Experienced Operator",
  "models": ["openai"],
  "results": {"gpt-5-mini": "<html...>"},
  "rank_result": {"summary": "..."}
}
```

Response:
- `application/pdf` stream.

---

## POST /api/email
Email the generated results PDF.

Request:
```json
{
  "to_email": "user@example.com",
  "industry": "FinTech",
  "constraints": ["Regulated"],
  "tone": "Experienced Operator",
  "models": ["openai"],
  "results": {"gpt-5-mini": "<html...>"},
  "rank_result": {"summary": "..."}
}
```

Response:
```json
{"status": "sent", "subject": "IdeaGen Report: FinTech"}
```

---

## POST /api/recommend-combination
Recommend constraints and persona.

Request:
```json
{
  "industry": "FinTech",
  "constraints": ["B2B SaaS", "Low Startup Cost (<$5k)", "Regulated Environment"],
  "personas": [{"id": "experienced_operator", "label": "Experienced Operator"}]
}
```

Response:
```json
{
  "recommended_constraints": ["B2B SaaS"],
  "recommended_persona": "experienced_operator",
  "reason_html": "<section...>",
  "usage": {"total_tokens": 320}
}
```

---

## GET /health
Health check.

Response:
```json
{"status": "healthy"}
```
