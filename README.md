# IdeaGen

IdeaGen is a multi-model business idea generator and report engine. It generates ideas, ranks model outputs, compares runs, and produces decision-ready reports for stakeholders.

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


## Why this project (LLM engineering focus)
- Multi-provider orchestration (OpenAI, Gemini, DeepSeek, Grok).
- Agentic validation loops for structured JSON outputs.
- Automated ranking and diff analysis across runs.
- Exportable PDF/email reports with consistent formatting.

## Architecture (high level)
```
UI (Next.js) ---> FastAPI API ---> LLM Providers
     |                |               |-- OpenAI
     |                |               |-- Gemini
     |                |               |-- DeepSeek
     |                |               |-- Grok
     |                |
     |                +--> SQLite (saved runs, reports, usage)
     |                +--> PDF renderer (WeasyPrint)
     |                +--> Resend email
```

## LLM engineering highlights
- Provider routing and fallback chains for resilience.
- Agentic JSON validation and retries for structured outputs.
- Separate analysis agents for ranking and comparisons.
- Strict prompts to avoid assumptions and keep outputs factual.
- Grounded Finance v2 for Execution Plans (deterministic financial model + narrative-only LLM).

## Agent flows
- Idea generation: multi-model outputs for the same config.
- Model ranking (per run): ranks model outputs using a rubric.
- Compare results (across runs): compares top-ranked outputs for the same config.
- Decision Summary Report: ranks multiple runs and summarizes insights.
- Execution Plan: generates implementation and finance dossier from saved decision artifacts.
- Recommend combination: suggests constraints/persona for a target industry.
- Email agent: centralized report email sending.

## Saved Results modal UX (implemented)
- One draggable, viewport-constrained floating modal shell with 4 modes: Generated, Compare, Decision, Execution Plan.
- Per-item actions:
  - Generated: `Load`, `Delete`
  - Compare: `View`, `Delete`
  - Decision: `View`, `Delete`
  - Execution Plan: `View`, `Delete`
- Bulk actions:
  - `Delete All` in Generated header (beside Refresh)
  - `Delete All` in Saved Comparisons header
  - `Delete All` in Saved Decision Summary Reports header
  - `Delete All` in Saved Execution Plans header
- Delete-all actions are disabled when the list is empty and always require confirmation.
- During compare/report generation and bulk deletion, conflicting modal actions are locked.
- Delete confirmation dialogs no longer trigger parent modal auto-close from outside-click listeners.

## Decision Flow + Step Guide UX (implemented)

The workspace now uses a dual-mode onboarding system so first-time users are guided while experienced users get a lighter status view.

- **Decision Flow strip** (top of workspace) shows 4 stages:
  1. Generate Results
  2. Compare Results
  3. Decision Summary
  4. Execution Plan
- **Adaptive mode switching with hysteresis**:
  - `guided -> status` only when global guidedness drops to `<= 40`
  - `status -> guided` only when global guidedness rises to `>= 60`
  - values between `41-59` keep current mode (prevents rapid mode flip/flop)
- **Guided mode** emphasizes prerequisites and next-step actions.
- **Status mode** emphasizes artifact counts and compact navigation context.

### Persistent Step Guide panel

A persistent **Step Guide** panel is rendered directly below the Decision Flow strip in all workspace tabs.

- Same structure on every tab:
  - What you do here
  - What you get
  - When you should use it
  - To move forward
- Tab-specific CTA in "To move forward":
  - Compare -> Generate Decision Summary
  - Decision -> Generate Execution Plan
  - Execution Plan -> Export Plan
- Collapse/expand is remembered per step and per user.
- Defaults are adaptive:
  - guided mode: expanded by default
  - status mode: collapsed by default
  - once user manually toggles a step guide, that preference is respected and not auto-overridden

### Generated tab onboarding behavior

Generated empty state now follows explicit scenarios:

- Fresh user (no saved artifacts): start with Generate Ideas.
- Returning user with saved artifacts but no selected run: prompt to Load from Library or Generate Ideas.

This keeps first-run onboarding explicit without blocking expert backtracking from Library.

## Bulk delete APIs (implemented)
- `DELETE /api/saved-results` -> bulk delete generated runs, returns `{ status, count }`
- `DELETE /api/compare-results` -> bulk delete comparisons, returns `{ status, count }`
- `DELETE /api/rank-reports` -> bulk delete decision reports, returns `{ status, count }`
- `DELETE /api/stakeholder-reports` -> bulk delete execution plans, returns `{ status, count }`

## Ranking rubric (per run)
The model ranking agent scores outputs on:
- Clarity
- Feasibility
- Differentiation
- Actionability
- Risk awareness
- Stakeholder readiness

## Guardrails
- JSON schema validation in agent responses.
- Retry loops with capped attempts.
- Fallback summaries for failed validations.
- Consistent model label mapping (user-friendly provider names).

## Evaluation approach (portfolio ready)
- Per-run ranking uses the rubric above.
- Compare Results uses top-ranked outputs only and highlights key changes.
- Decision Summary Report ranks runs and summarizes risks and next steps.
- Execution Plan uses grounded deterministic finance and rule-based gates for `go | conditional_go | no_go`.
- Manual spot checks verify that outputs match the configuration and avoid hallucination.

## Execution Plan (Grounded Finance v2)

Execution Plans are generated from saved artifacts (`decision_report`, `compare_result`, or `saved_run`) and support strict finance grounding.

- Default mode: `finance_mode=grounded_v2`
  - financial sections are deterministic (`resources`, `costs`, `revenue_profit`, `scenarios`, `stakeholder_ask`)
  - LLM is used only for narrative sections (thesis, execution blueprint, risks, decision wording)
- Compatibility mode: `finance_mode=llm_v1`
- Report includes:
  - proposal estimate disclaimer banner,
  - sensitivity analysis stress tests (ARPU, conversion, OpEx),
  - assumption source + confidence fields,
  - decision support gates and profitability recovery plan,
  - per-card `Info` pill tooltips in the Execution Plan UI with plain-English explanations for non-technical readers.

## Local development

### Frontend
```bash
npm install
npm run dev
```

### Backend (FastAPI)
```bash
cd api
uvicorn index:app --reload --port 8000
```

### Docker (recommended)
```bash
export $(cat .env | grep -v '^#' | xargs)
docker build \
  --build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY" \
  --build-arg NODE_ENV=dev \
  -t ideagen-app .

docker run -p 8000:8000 \
  -v ideagen_data:/app/data \
  -e CLERK_SECRET_KEY="$CLERK_SECRET_KEY" \
  -e CLERK_JWKS_URL="$CLERK_JWKS_URL" \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -e RESEND_API_KEY="$RESEND_API_KEY" \
  -e DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" \
  -e GROK_API_KEY="$GROK_API_KEY" \
  -e GEMINI_API_KEY="$GEMINI_API_KEY" \
  -e DEEPSEEK_API_URL="$DEEPSEEK_API_URL" \
  -e GROK_API_URL="$GROK_API_URL" \
  -e GEMINI_API_URL="$GEMINI_API_URL" \
  ideagen-app
```

## Documentation
- API reference: `api_reference.md`
- Data model/schema: `data_model.md`
- Deployment runbook: `deployment_runbook.md`
- Troubleshooting: `troubleshooting.md`
- Security/privacy: `security_privacy.md`
- Billing/limits: `billing_limits.md`
- UX flow guide: `ux_flow.md`
- User guide: `user guide.md`
- Deep architecture reference: `ARCHITECTURE.md`
- Stakeholder dossier schema spec: `stakeholder_report_schema.md`
- Launch checklist: `checklist.md`
- Roadmap: `roadmap.md`


## AWS DEPLOYMENT ECR

# aws configure

Enter:

AWS Access Key ID: (paste your key)
AWS Secret Access Key: (paste your secret)
Default region: Choose based on your location:
US East Coast: us-east-1 (N. Virginia)
US West Coast: us-west-2 (Oregon)
Europe: eu-west-1 (Ireland)
Asia: ap-southeast-1 (Singapore)
Pick the closest region for best performance!
Default output format: json
Important: Remember your region choice


# 1. Authenticate Docker to ECR (using your .env values!)
aws ecr get-login-password --region $DEFAULT_AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$DEFAULT_AWS_REGION.amazonaws.com

docker build --platform linux/amd64 \
  --build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY" \
  --build-arg NEXT_PUBLIC_CLERK_JWT_TEMPLATE="$NEXT_PUBLIC_CLERK_JWT_TEMPLATE" \
  -t ideagen-app .

# 3. Tag your image (using your .env values!)
docker tag ideagen-app:latest $AWS_ACCOUNT_ID.dkr.ecr.$DEFAULT_AWS_REGION.amazonaws.com/ideagen-app:latest

# 4. Push to ECR
docker push $AWS_ACCOUNT_ID.dkr.ecr.$DEFAULT_AWS_REGION.amazonaws.com/ideagen-app:latest

## AWS APP RUNNER CUSTOM DOMAIN

Target domain:

- `ideagen.agentairg.site`

Setup steps:

1. In App Runner service, open `Custom domains` -> `Link custom domain`.
2. Select Route 53 hosted zone `agentairg.site`.
3. Set subdomain to `ideagen`.
4. Choose `CNAME` record type for subdomain mapping.
5. Wait until domain status is `Active`.

Verify:

```bash
dig ideagen.agentairg.site +short
curl -I https://ideagen.agentairg.site
```

## HOST RESTRICTION (`ALLOWED_HOSTS`)

Backend middleware enforces allowed hosts for app traffic.

- Set `ALLOWED_HOSTS=ideagen.agentairg.site` in App Runner env vars.
- Non-allowed hosts (including default `*.awsapprunner.com`) return `403`.
- `/health` remains allowed for App Runner health checks.
