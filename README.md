# Agentic Healthcare SaaS (AWS)

`healthcare-saas-aws` is a clinician-facing summarization and patient-history application built as a single Next.js + FastAPI service and deployed on AWS App Runner.

The app is no longer a manually configured App Runner project. It now runs on a Terraform-managed AWS stack with:

- App Runner for runtime
- ECR for container images
- DynamoDB for long-term patient memory
- Secrets Manager for runtime secrets
- Route53 for the custom domain
- GitHub Actions for deploy and destroy workflows

This README is the guided map to the system. It is intentionally not the deepest technical reference.

The split is deliberate:

- `README.md`
  - start here if you want the coherent walkthrough
  - use it to understand what the app is, how it behaves end to end, how to run it locally, and how deploys work at a practical level
- `ARCHITECTURE.md`
  - use it as the full source-of-truth technical reference
  - it carries the deep explanation of request flows, artifact lifecycle, persistence internals, backend orchestration, Terraform, AWS, GitHub Actions, tradeoffs, and known gaps

When behavior changes:

- update `ARCHITECTURE.md` if the exact technical behavior changed
- update `README.md` only if the guided walkthrough, local-run path, deploy shape, or operator entry guidance changed
- use the PR template checklist during review, because merging to `healthcare-saas-aws` leads to the automatic `prod` deploy path

If you want the full technical source of truth, start here:

- [ARCHITECTURE.md](/home/repos/healthcare-saas-aws/ARCHITECTURE.md)

For focused operational docs:

- [Deployment + ops runbook](/home/repos/healthcare-saas-aws/deployment_runbook.md)
- [GitHub Actions runbook](/home/repos/healthcare-saas-aws/github_actions_runbook.md)
- [Terraform infrastructure guide](/home/repos/healthcare-saas-aws/terraform/README.md)
- [GitHub environment runbook](/home/repos/healthcare-saas-aws/healthcare_github_environment_setup.md)

## 1. What the app is

MediNotes is designed for clinicians who need to turn messy consultation inputs into structured outputs while preserving patient continuity across visits.

The application supports:

- typed consultation notes
- uploaded clinical documents
- audio recordings
- handwritten or prescription images
- patient-history retrieval across prior visits
- assistant chat grounded in current and historical context
- patient-facing email drafting and send

At a practical level, the product gives the user:

- structured summary generation
- evidence-linked outputs
- next-action extraction
- patient-history browsing
- soft delete and restore of stored visit artifacts
- longitudinal memory that survives redeploys

## 2. How it runs end to end

The main operational path is:

1. the user enters notes or uploads consultation material
2. the backend extracts and normalizes the visit context
3. the system recalls prior patient history from DynamoDB
4. the summary pipeline generates a draft
5. research is added when needed
6. a critic review checks the draft
7. evidence is mapped to the final result
8. the final visit memory is stored for future retrieval
9. the UI receives streamed progress and final output

The assistant flow uses the same persisted patient memory, which is why it can answer questions about prior visits instead of only the current screen state.

If you want the detailed breakdown of what each stage does, where the artifacts live, and how the agents coordinate that work, use [ARCHITECTURE.md](/home/repos/healthcare-saas-aws/ARCHITECTURE.md). This README is intentionally stopping at the operational walkthrough level.

## 3. How to run it locally

Local development uses the same application code but not the exact same process topology as production.

In production, App Runner serves one container where:

- FastAPI is the runtime entrypoint
- the exported Next.js frontend is served as static files by FastAPI

Locally, the repo currently supports two separate development loops:

- frontend iteration with `npm run dev`
- backend/API iteration with `uvicorn api.index:app --reload --port 8000`

That distinction matters because the frontend code calls relative `/api/...` routes, while `npm run dev` only starts the Next.js dev server.

### 3.1 Start DynamoDB Local

```bash
docker compose -f docker-compose.local.yml up -d
```

### 3.2 Set local memory environment variables

```bash
export DYNAMODB_TABLE_NAME=medinotes-memory
export DYNAMODB_ENDPOINT_URL=http://localhost:8001
export AWS_REGION=ap-southeast-1
export AWS_ACCESS_KEY_ID=dummy
export AWS_SECRET_ACCESS_KEY=dummy
```

### 3.3 Create the local table

```bash
bash tools/create_memory_table.sh medinotes-memory
```

### 3.4 Run the app

For frontend-only work:

```bash
npm run dev
```

For backend/API work:

```bash
uvicorn api.index:app --reload --host 0.0.0.0 --port 8000
```

Local notes:

- `.env` and `.env.local` are used for local runtime configuration
- local DynamoDB is only for local development
- AWS deploys must not set `DYNAMODB_ENDPOINT_URL`
- `npm run dev` does not start the FastAPI backend
- `uvicorn api.index:app ...` does not provide the Next.js dev server
- the repo does not currently define a local dev proxy that makes `next dev` and FastAPI behave as one seamless same-origin local stack
- the production-like combined behavior is the containerized path, where FastAPI serves the exported frontend from `static/`

For the deeper local-versus-AWS explanation, including why patient memory is durable in AWS but App Runner itself is still stateless, use [ARCHITECTURE.md](/home/repos/healthcare-saas-aws/ARCHITECTURE.md).

## 4. How it deploys

The current production branch is:

- `healthcare-saas-aws`

Pushes to that branch run:

- `Test`
- `Docker Build`
- `Deploy / prod`

Current production deployment shape:

- GitHub Actions assumes the dedicated healthcare deploy role
- Terraform reconciles infrastructure and service configuration
- deploy tooling syncs runtime secrets into AWS Secrets Manager
- Docker image is built and pushed to ECR
- App Runner auto-deploys the new image
- health is verified after rollout

Production currently uses these important names:

- App Runner service: `consultation-app-service`
- ECR repository: `consultation-app`
- DynamoDB table: `medinotes-prod-memory`
- custom domain: `medinotes.agentairg.site`

`dev` still exists as an environment, but it is manual-only right now.

This is the practical deploy description only. The deeper explanation of why the deploy order is structured this way, how GitHub environments map to AWS OIDC trust, how secrets move from GitHub to Secrets Manager to App Runner, and how destroy semantics work lives in [ARCHITECTURE.md](/home/repos/healthcare-saas-aws/ARCHITECTURE.md), [deployment_runbook.md](/home/repos/healthcare-saas-aws/deployment_runbook.md), and [github_actions_runbook.md](/home/repos/healthcare-saas-aws/github_actions_runbook.md).

## 5. Where to go next

Use [ARCHITECTURE.md](/home/repos/healthcare-saas-aws/ARCHITECTURE.md) if you want the full explanation of:

- all backend layers
- request flows
- artifact lifecycle
- persistence internals
- Terraform/AWS/GitHub Actions details
- constraints, tradeoffs, and current gaps

Use these focused docs when needed:

- runtime and deploy operations: [deployment_runbook.md](/home/repos/healthcare-saas-aws/deployment_runbook.md)
- GitHub environments, workflows, and IAM role wiring: [github_actions_runbook.md](/home/repos/healthcare-saas-aws/github_actions_runbook.md)
- Terraform resource ownership and deploy/destroy mechanics: [terraform/README.md](/home/repos/healthcare-saas-aws/terraform/README.md)
- backend API and agent-focused behavior: [backend.md](/home/repos/healthcare-saas-aws/backend.md)
