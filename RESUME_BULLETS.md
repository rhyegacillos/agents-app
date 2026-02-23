# Resume Bullets: Digital Assistant

Use these as copy-ready bullets and adjust scope/metrics to match your exact contribution.

Live App: https://digital-assistant.agentairg.site

## Senior Full-Stack / AI Engineer
- Built and deployed a serverless, agentic AI assistant with tool orchestration (web search, PDF export, email delivery, file ingestion, memory extraction) using FastAPI, Next.js, and MCP.
- Designed a hybrid truth-gated execution model that routes low-risk chat through guarded prose and high-risk actions through canonical tool-validated rendering.
- Implemented event-driven asynchronous job execution (`job_id` polling + worker Lambda) to eliminate synchronous API timeout failures for tool-heavy workflows.
- Added deterministic link/source validation and action-claim checks to prevent invalid download links and unverified "email sent" responses.
- Delivered daily quota governance (tokens, PDF exports, email sends) with server-side enforcement and real-time UI counters.

## Backend / Platform Focus
- Architected serverless backend on AWS (Lambda + API Gateway + S3 + CloudFront + ECR) provisioned fully through Terraform across dev/prod environments.
- Integrated Upstash Redis for async job state and quota tracking with S3-backed fallback and CAS-style concurrency hardening.
- Implemented provider-usage-based token accounting instead of heuristic text-length estimation for accurate quota controls.
- Built operational safeguards for side-effect tools (PDF/email), including canonical URL allowlisting and verifier-driven output blocking on unsafe responses.
- Implemented OpenTelemetry traces + logs (OTLP export) for API + worker with consistent trace tags (`trace_id`, `job_id`, `session_id`), enabling vendor portability and faster incident triage.

## Serverless Impact Bullets
- Replaced always-on backend hosting with on-demand Lambda execution, reducing operational surface area to managed services.
- Separated synchronous API and background worker Lambdas to scale independently by workload type.
- Used API Gateway + Lambda + S3 + CloudFront as a fully managed runtime path with no server fleet maintenance.
- Shipped infrastructure and runtime config as code (Terraform variables + tfvars), enabling consistent dev/prod rollouts.

## Frontend / Product Engineering Focus
- Built a production-ready chat interface in Next.js/TypeScript with tool controls, artifact links, and daily quota telemetry in the header.
- Fixed markdown rendering hydration issues (invalid nested `figure/figcaption` inside paragraph contexts) for stable SSR/CSR behavior.
- Implemented UX patterns for async agent runs, deterministic failure messaging, and quota-limit feedback.
- Cleaned lint violations and stabilized frontend code paths used by tool-rich conversational responses.

## DevOps / Delivery Focus
- Shipped infrastructure-as-code deployment and runtime configuration via Terraform variables and environment-specific tfvars.
- Wired runtime controls (model routing, timeouts, quotas, feature flags) through deploy-time env vars for repeatable operations.
- Maintained CI-ready backend tests and frontend lint gates to reduce regressions during rapid feature iteration.

## Optional Quantified Variants (fill in your measured numbers)
- Reduced tool-action failure rate from `X%` to `Y%` by introducing canonical output validation + retry/fix loops.
- Cut user-facing timeout incidents by `X%` after moving tool-heavy requests to async worker execution.
- Improved incident triage time by `X%` using trace-correlated logs and explicit verifier issue codes.
