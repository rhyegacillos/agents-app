# Output Truth Gate Spec v3 (Contract-First)

## Goal
Eliminate reactive patching by separating responsibilities:
- LLM chooses intent.
- Tools produce canonical facts.
- Server renders output from canonical facts.
- Truth gate validates contracts only (no text rewriting).

## Scope
Applies to high-risk paths:
- PDF generation and delivery.
- Email delivery.
- Search/news/research responses requiring citations.

Low-risk chat remains prose-only with no action claims.

## Core Architecture
1. `classify`: route request (`low` vs `high` risk).
2. `plan`: LLM returns strict intent payload (not final delivery prose).
3. `execute`: server runs tools and captures canonical context.
4. `validate`: truth gate checks context + intent contract.
5. `render`: server generates final user-visible output from canonical context.

No direct LLM draft is sent for high-risk actions.

## Contracts
### 1) Intent Contract (`IntentEnvelope`)
```json
{
  "intent_type": "chat_prose|research_answer|generate_pdf|send_email|search_and_answer",
  "requires_tools": true,
  "requested_actions": ["generate_pdf_from_text", "send_resend_email"],
  "constraints": {
    "must_preserve_user_facts": true,
    "max_retry": 1,
    "require_sources": true
  }
}
```

### 2) Canonical Context (`TruthContext`)
```json
{
  "trace_id": "uuid",
  "artifacts": [
    {
      "artifact_id": "artf_x",
      "kind": "pdf",
      "download_url": "/downloads/file.pdf",
      "filename": "file.pdf",
      "page_count": 4,
      "status": "ok"
    }
  ],
  "outcomes": [
    {
      "tool": "send_resend_email",
      "status": "ok",
      "email_id": "..."
    }
  ],
  "sources": [
    {
      "title": "A Survey ...",
      "url": "https://arxiv.org/abs/2507.18910"
    }
  ]
}
```

### 3) Validation Contract (`TruthVerdict`)
```json
{
  "status": "pass|block",
  "issues": [
    {
      "code": "SEARCH_CONTEXT_EMPTY",
      "severity": "error",
      "detail": "Search intent requires canonical source URLs."
    }
  ]
}
```

Truth gate never mutates user-facing text in v3.

## Rendering Contract
Server templates create final output from `TruthContext`:
- PDF chat response: include labeled link from canonical artifact URL.
- Email confirmation: success only when canonical outcome status is `ok`.
- Research output: inline citations must resolve to canonical `sources[]`.

If render cannot satisfy contract, return structured block message with `issue codes`.

## Retry Policy
- Allowed only for `PDF_INPUT_INVALID`.
- Retry strategy: re-call LLM once with strict constraints (`no semantic changes`).
- If retry fails: return block with `PDF_INPUT_INVALID` and trace id.
- No local JSON auto-repair of semantic payloads.

## Error Codes (v3)
- `INTENT_SCHEMA_INVALID`
- `TOOL_EXECUTION_FAILED`
- `PDF_INPUT_INVALID`
- `PDF_ARTIFACT_MISSING`
- `EMAIL_OUTCOME_MISSING`
- `CLAIM_UNVERIFIED_EMAIL_SENT`
- `CLAIM_UNVERIFIED_PAGE_COUNT`
- `SEARCH_CONTEXT_EMPTY`
- `SOURCE_LINK_MISSING`
- `SOURCE_URL_INVALID`

## Acceptance Criteria
- 0 placeholder links in chat/email/PDF outputs.
- 0 unverified `email sent` claims.
- 0 unverified page-count claims.
- 100% of citation-like claims in high-risk research outputs map to canonical URLs.
- Malformed PDF payloads never render raw JSON into PDF.

## Rollout
1. Shadow mode: run v3 validator/renderer in parallel and log diffs.
2. Soft switch: v3 authoritative for high-risk output, fallback to current path only on internal errors.
3. Hard switch: remove legacy mutation/patch paths after parity target is met.
