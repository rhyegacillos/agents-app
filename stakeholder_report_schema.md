# Execution Plan Dossier Schema (Implemented)

This document describes the **implemented** Execution Plan artifact used by IdeaGen.

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


- API artifact name in code/storage: `stakeholder report`
- Product label in UI: **Execution Plan**
- Generation source: saved `decision_report`, `compare_result`, or `saved_run`

---

## 1) API Surface

### 1.1 Create execution plan

`POST /api/stakeholder-report`

Request example:

```json
{
  "source": {
    "mode": "decision_report",
    "decision_report_id": 42,
    "selected_run_id": 101,
    "selected_model_id": "gpt-5-mini"
  },
  "scenario_profile": "base",
  "horizon_months": 12,
  "currency": "USD",
  "region": "US",
  "output": "json",
  "finance_mode": "grounded_v2"
}
```

Response example:

```json
{
  "id": 9001,
  "created_at": "2026-02-16T03:17:37+00:00",
  "status": "ready",
  "model": "gpt-5-mini",
  "usage": {
    "prompt_tokens": 1234,
    "completion_tokens": 980,
    "total_tokens": 2214
  },
  "dossier": {}
}
```

### 1.2 List saved execution plans

`GET /api/stakeholder-reports?limit=6`

### 1.3 Get one execution plan

`GET /api/stakeholder-reports/{id}`

### 1.4 Delivery endpoints

- `GET /api/stakeholder-reports/{id}/pdf`
- `GET /api/stakeholder-reports/{id}/presentation`

### 1.5 Delete endpoints

- `DELETE /api/stakeholder-reports/{id}`
- `DELETE /api/stakeholder-reports`

---

## 2) Request Contract (Current)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ExecutionPlanCreateRequest",
  "type": "object",
  "required": ["source", "scenario_profile", "horizon_months", "currency", "region", "output"],
  "properties": {
    "source": {
      "type": "object",
      "required": ["mode"],
      "properties": {
        "mode": {
          "type": "string",
          "enum": ["decision_report", "compare_result", "saved_run"]
        },
        "decision_report_id": { "type": "integer", "minimum": 1 },
        "compare_result_id": { "type": "integer", "minimum": 1 },
        "selected_run_id": { "type": "integer", "minimum": 1 },
        "selected_model_id": { "type": "string", "minLength": 1 }
      }
    },
    "scenario_profile": {
      "type": "string",
      "enum": ["conservative", "base", "aggressive", "all"]
    },
    "horizon_months": {
      "type": "integer",
      "minimum": 6,
      "maximum": 24
    },
    "currency": { "type": "string", "enum": ["USD"] },
    "region": { "type": "string", "enum": ["US"] },
    "output": { "type": "string", "enum": ["json"] },
    "finance_mode": { "type": "string", "enum": ["grounded_v2", "llm_v1"] }
  },
  "additionalProperties": false
}
```

Notes:

- `finance_mode` defaults to `grounded_v2`.
- `grounded_v2` keeps financial sections deterministic and uses LLM for narrative sections only.
- `llm_v1` is retained for compatibility.

---

## 3) Dossier Contract (Current)

Core required sections:

- `meta`
- `decision`
- `execution_blueprint`
- `resources`
- `costs`
- `revenue_profit`
- `scenarios`
- `risks`
- `stakeholder_ask`
- `assumptions`
- `provenance`

Additional implemented sections:

- `decision_support`
- `proposal_disclaimer`
- `sensitivity_analysis`

### 3.1 Key object definitions

`decision`:

- `winner.run_id`, `winner.model_id`, `winner.title`
- `thesis`
- `go_no_go` (`go`, `conditional_go`, `no_go`)
- `confidence` (`0..1`)

`execution_blueprint`:

- `phases[]` with month ranges and owner/workstream/deliverable details
- `critical_path[]`
- `gates[]`
- `kill_criteria[]`

`revenue_profit`:

- `pricing`
- `funnel_assumptions`
- `monthly_projection[]`
- `break_even_month`

`decision_support`:

- `status` (`viable`, `conditional`, `not_viable`)
- `forced_by_rules` (boolean)
- `reasons[]`
- `required_actions[]`
- `gates` (year1 net, expected year1 net, break-even, gross margin, horizon)
- `profitability_recovery` (enabled, gap, levers, scenarios, experiments, approval gate)

`proposal_disclaimer`:

- `title`
- `message`
- `data_basis`
- `updated_at` (`YYYY-MM-DD`)

`sensitivity_analysis`:

- `baseline`
- `tests[]` (ARPU/conversion/OpEx stress cases)
- `interpretation`

`assumptions[]`:

- `key`, `value`, `unit`, `source`, `confidence`
- includes both baseline finance assumptions and run-conditioned audit entries, such as:
  - `selected_output_title`
  - `selected_model_confidence`
  - `scenario_probability_mix`
  - `finance_adjustment_tags`

`provenance`:

- `source_artifacts[]`
- `selected_run_id`
- `selected_model_id`
- `selected_output_title`
- `formula_version`
- `generator_version`
- `financials_grounded` (boolean)
- `finance_mode`
- `narrative_model`

---

## 4) Grounded Finance v2 Rules

When `finance_mode=grounded_v2`:

1. Financial objects are sourced from deterministic baseline logic:
   - `resources`
   - `costs`
   - `revenue_profit`
   - `scenarios`
   - `stakeholder_ask`
   - finance-related assumptions
2. Deterministic **run-conditioned adjustments** are applied before final projection:
   - inputs: selected run constraints, persona, selected model output text/title, selected model confidence
   - behavior: bounded multiplier adjustments (clamped ranges) for customer start point, ARPU, setup/opex/cogs, and scenario probabilities
   - goal: report-specific but reproducible financials (no free-form financial invention)
3. Narrative objects are LLM-assisted:
   - thesis phrasing
   - execution blueprint detail language
   - risk wording
   - decision wording
4. Full dossier is re-validated using server-side schema/range checks.
5. If narrative composition fails, deterministic fallback dossier remains available.

---

## 5) Storage Model

PostgreSQL table: `saved_stakeholder_reports`

Columns:

- `id`, `user_id`, `created_at`
- `source_type`, `source_id`
- `scenario_profile`, `horizon_months`
- `currency`, `region`
- `dossier_json`
- `assumptions_json`
- `model`

Notes:

- `model` stores narrative generation model identifier.
- Deterministic finance mode information is stored in `dossier_json.provenance`.
- JSON payloads are stored as `JSONB` in the current schema.

---

## 6) Rendering Contract

Execution Plan dossier supports:

- main workspace rendering (`pages/product.tsx`)
- standard PDF export (`create_execution_plan_report_html`)
- presentation deck PDF export (`create_execution_plan_presentation_html`)

All renderers consume the same dossier JSON contract and assumptions payload.

---

## 7) Operational Caveats

- Existing saved execution plans are immutable snapshots.
- New schema fields appear after regenerating plans created before schema updates.
- Currency/region currently fixed to `USD`/`US`.
