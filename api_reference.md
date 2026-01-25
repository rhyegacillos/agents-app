# API Reference

Base URL: `/api`
Auth: Clerk bearer token in `Authorization: Bearer <token>`

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

## GET /api/rank-reports/{id}
Get a saved decision summary report.

Response:
```json
{"id": 7, "created_at": "...", "run_ids": [10, 11], "report": {"summary": "..."}}
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
