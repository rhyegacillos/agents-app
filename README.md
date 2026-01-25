# IdeaGen

IdeaGen is a multi-model business idea generator and report engine. It generates ideas, ranks model outputs, compares runs, and produces decision-ready reports for stakeholders.

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
     |                +--> PDF renderer (xhtml2pdf)
     |                +--> Resend email
```

## LLM engineering highlights
- Provider routing and fallback chains for resilience.
- Agentic JSON validation and retries for structured outputs.
- Separate analysis agents for ranking and comparisons.
- Strict prompts to avoid assumptions and keep outputs factual.

## Agent flows
- Idea generation: multi-model outputs for the same config.
- Model ranking (per run): ranks model outputs using a rubric.
- Compare results (across runs): compares top-ranked outputs for the same config.
- Decision Summary Report: ranks multiple runs and summarizes insights.
- Recommend combination: suggests constraints/persona for a target industry.
- Email agent: centralized report email sending.

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
- Manual spot checks verify that outputs match the configuration and avoid hallucination.

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
docker build --build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY" -t ideagen-app .
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
- Launch checklist: `checklist.md`
- Roadmap: `roadmap.md`
