# Twin

Twin is a web-based digital assistant that presents a single curated persona through a static Next.js frontend and a FastAPI backend running on AWS Lambda. The system supports normal conversational replies, tool-backed actions such as PDF generation and email delivery, optional web search, user-scoped memory, and a verification pipeline for high-risk outputs.

This repository already contains the detailed operational and deployment material. The intended doc split is:

- `README.md`: guided map of the product and repo
- `ARCHITECTURE.md`: source-of-truth technical reference
- `OPERATIONS.md`: KPIs, observability, QA, and runtime hardening
- `DEPLOYMENT_TERRAFORM.md`: Terraform rollout details
- `DEPLOYMENT_GITHUB_ACTIONS.md`: CI/CD and GitHub Actions details

## What the app is

At runtime the app behaves like a persona-specific assistant:

- The browser loads a static frontend from S3 + CloudFront.
- The frontend generates a local sync code and uses it as `user_id`.
- The backend stores each user’s conversation history separately.
- The runtime routes requests into either a low-risk prose path or a high-risk tool path.
- High-risk outputs are rendered into a canonical format and checked by a truth gate before they are returned.
- Candidate memory is extracted from user turns, but it is only injected back into the assistant after explicit approval.

The persona itself is assembled from curated files in `backend/data/` and loaded into the system prompt at runtime.

## How it runs end to end

The high-level flow is:

1. The frontend sends `POST /chat` with `user_id`, `session_id`, the message, and optionally a `file_id`.
2. The backend loads prior conversation state, checks quota, and classifies the request as low risk or high risk.
3. Low-risk requests run as prose-only completions with tools disabled.
4. High-risk requests run through MCP-backed tools such as search, PDF generation, upload reading, and email delivery.
5. Tool output is normalized into a truth context containing artifacts, action outcomes, and search sources.
6. The response is canonically rendered, validated, optionally auto-fixed, then persisted together with the turn.
7. Memory extraction runs after the turn and produces approval candidates for later review.

Async mode is supported when API Gateway timeout risk is high. In that mode `POST /chat` returns `202 Accepted`, the API enqueues a worker job, and the frontend polls `/jobs/{job_id}` until completion.

## Repo map

- `frontend/`: static Next.js app and chat UI
- `backend/`: FastAPI app, Lambda handlers, runtime orchestration, MCP tools, tests
- `terraform/`: AWS infrastructure for frontend hosting, Lambda, API Gateway, ECR, CloudFront, and optional domain wiring
- `scripts/deploy.sh`: end-to-end deployment script
- `memory/`: local dev storage when `USE_S3=false`

## Run locally

The simplest local setup is:

- run the backend with local file storage
- disable async mode
- point the frontend at `http://localhost:8000`

### 1. Configure environment

Copy `.env.example` to `.env` and adjust at least these values for local work:

```dotenv
USE_S3=false
ASYNC_CHAT_ENABLED=false
OTEL_ENABLED=false
AI_PROVIDER=bedrock
DEFAULT_AWS_REGION=ap-southeast-1
```

Provider notes:

- If you use `AI_PROVIDER=bedrock`, your AWS credentials must already allow Bedrock runtime access.
- If you use `AI_PROVIDER=grok`, set `GROK_API_KEY` and keep the Grok URL/model values valid.
- Search, email, and some action flows require their own provider keys such as `BRAVE_API_KEY` and `RESEND_API_KEY`.

### 2. Start the backend

Using `uv`:

```bash
cd backend
uv sync
uv run uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

Or using a virtual environment and `pip`:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

Notes:

- The backend entrypoint is `backend/server.py`.
- Lambda deployments use `backend/lambda_handler.py`, but local development uses Uvicorn directly.
- PDF generation depends on WeasyPrint, which may require native system libraries on a fresh machine.

### 3. Start the frontend

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Then open `http://localhost:3000`.

Because `frontend/next.config.ts` uses `output: 'export'`, the production frontend is a static export even though local development uses the standard Next.js dev server.

## How it deploys

The repo’s default deployment path is the shell script:

```bash
./scripts/deploy.sh dev
```

That script performs the full rollout:

1. Initializes/selects the Terraform workspace.
2. Ensures the Lambda ECR repository exists.
3. Builds the backend Lambda container image and pushes it to ECR.
4. Applies Terraform to create or update AWS infrastructure.
5. Forces both Lambda functions to pull the new image digest.
6. Builds the frontend static export with the deployed API URL.
7. Syncs the frontend export to the S3 bucket.
8. Invalidates CloudFront so the new `index.html` is served immediately.

The deployed topology is:

- static frontend in S3 behind CloudFront
- REST API on API Gateway
- FastAPI API Lambda
- separate worker Lambda for async jobs
- S3-backed conversation and memory storage
- Upstash Redis for async job state and truth-gate state
- ECR for the backend container image

## Where to go next

- Read `ARCHITECTURE.md` for the full runtime, persistence, artifact, and infrastructure explanation.
- Read `OPERATIONS.md` for observability, QA, and production-hardening expectations.
- Read `DEPLOYMENT_TERRAFORM.md` if you are changing AWS resources or environment variables.
- Read `DEPLOYMENT_GITHUB_ACTIONS.md` if you are changing CI/CD or GitHub OIDC setup.

## Current doc intent

This README should stay opinionated and navigational. If a section starts turning into implementation truth, move that material into `ARCHITECTURE.md` and keep only the short link and summary here.

The exact route inventory, runtime defaults, and required-tool contract summary are intentionally maintained only in the generated reference block inside `ARCHITECTURE.md`.
