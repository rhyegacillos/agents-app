# IdeaGen Architecture

This is the main architecture document for `ideagen-saas-aws`.

Its job is to describe how the app actually works end to end:

- what the product does
- how the frontend and backend collaborate
- how data is stored and reused
- how generation, comparison, reporting, and execution planning work
- how the app is packaged and deployed

If this document and another repo document disagree, trust the runtime code first, then update the docs. This file is intended to stay aligned with the current implementation in:

- [api/index.py](/home/repos/ideagen-saas-aws/api/index.py)
- [pages/product.tsx](/home/repos/ideagen-saas-aws/pages/product.tsx)
- [api/db.py](/home/repos/ideagen-saas-aws/api/db.py)
- [api/database/models.py](/home/repos/ideagen-saas-aws/api/database/models.py)
- [terraform/main.tf](/home/repos/ideagen-saas-aws/terraform/main.tf)
- [Dockerfile](/home/repos/ideagen-saas-aws/Dockerfile)

Use [README.md](/home/repos/ideagen-saas-aws/README.md) as the guided walkthrough. Use this file as the full explanation of how the system works internally.

## 1. System Summary

IdeaGen is a single web application that helps a signed-in user move from idea exploration to execution planning.

At a high level, the system looks like this:

```text
Browser
  -> Next.js static frontend
  -> Clerk auth session / JWT template token
  -> FastAPI API
       -> auth + host checks
       -> quota and premium gates
       -> multi-provider LLM orchestration
       -> comparison / decision / execution-plan generation
       -> PDF rendering
       -> email sending
       -> PostgreSQL persistence

AWS deployment
  -> Docker image in ECR
  -> App Runner service
  -> RDS PostgreSQL in private subnets
  -> Secrets Manager for runtime secrets
  -> VPC connector for private DB access
```

The application is not an asynchronous job system. It is a request/response product:

- the frontend drives each action
- FastAPI orchestrates each request
- agent modules are invoked inside the request lifecycle
- artifacts are saved to PostgreSQL for later reload, comparison, export, and email

### 1.1 What The System Is Actually Doing

The easiest way to misunderstand IdeaGen is to think of it as a simple "prompt in, answer out" app. That is not how the implemented product behaves.

In practice, the system is organized around durable decision artifacts. A user does not come to the app only to generate text. They come to build a chain of evidence:

- a generated run that captures one exploration of an idea
- a comparison that explains which of two runs is stronger
- a decision summary that ranks one or more runs and recommends a direction
- an execution plan that turns the selected direction into an operational plan

This matters architecturally because the backend is not optimized only for one-shot inference. It is optimized for preserving state between those steps. That is why the persistence layer stores generated runs, comparisons, decision summaries, and execution plans as first-class objects. It is also why the frontend keeps a library panel and treats loading historical artifacts as a normal workflow rather than an edge case.


The deployment model reflects the same assumption. The frontend is statically built and served from the same container as the API, but the durable system state lives outside the container in PostgreSQL. The app container can be replaced during deployment without losing application history because the real product memory is in the database, not on disk inside the runtime.

## 2. Product Operation

### 2.1 User-facing surfaces

The repo has two main frontend entry points:

- [pages/index.tsx](/home/repos/ideagen-saas-aws/pages/index.tsx): landing and marketing page
- [pages/product.tsx](/home/repos/ideagen-saas-aws/pages/product.tsx): authenticated product workspace

The product workspace is the operational center of the app. It is built around four workflow steps:

1. Generate Results
2. Compare Results
3. Decision Summary
4. Execution Plan

### 2.2 Frontend flow model

The frontend is not a thin API wrapper. It contains a fairly large state machine that manages:

- current step via `resultsView`
- guided vs status UI mode
- per-step guidance panels
- saved library panel modes for runs, comparisons, decision reports, and execution plans
- compare-run selections
- decision selection state
- execution-plan source selection state
- export and email actions

Important UX behavior implemented in [pages/product.tsx](/home/repos/ideagen-saas-aws/pages/product.tsx):

- guidedness is persisted in local storage per user
- the workspace switches between `guided` and `status` modes using hysteresis
- each step has a persistent, collapsible Step Guide
- the Library acts as the cross-step artifact loader
- the frontend silently auto-saves newly generated runs after a successful `/api` generation call

### 2.3 End-to-end user workflow

The product normally operates like this:

1. The user chooses industry, constraints, persona, and one or more model providers.
2. If the user is premium, they can call `POST /api/recommend-combination` to ask the backend to recommend a persona and constraint combination before generation. The frontend applies that recommendation directly back into the current form state.
3. The frontend calls `POST /api` to generate outputs.
4. The frontend stores the returned outputs in local UI state and then calls `POST /api/saved-results` to auto-save the run.
5. The user can compare two saved runs with `POST /api/compare-results`.
6. The user can generate a decision summary over 1-5 runs with `POST /api/rank-report`, or reload an existing saved decision report.
7. The user can generate an execution plan from a decision report, comparison, or saved run with `POST /api/stakeholder-report`.
8. At multiple points the user can export PDFs, and some artifact types also support email delivery. Execution plans currently do not.

This is an artifact-centric product. The user does not just get transient LLM output; they build a library of saved evidence.

### 2.4 Artifact Lifecycle Across The Whole Product

The most important cross-cutting concept in the app is the artifact lifecycle. Everything else in the architecture exists to support it.

A generation request creates the base artifact: a saved run. A saved run contains the request context the user chose, the outputs returned by one or more models, and optional per-run ranking metadata. That object is the raw material for later steps. Comparisons do not operate on arbitrary text. They operate on saved runs. Decision summaries do not operate on arbitrary prompts. They operate on one or more saved runs. Execution plans do not operate on arbitrary summaries typed into a form. They operate on a decision report, a comparison, or a saved run that already exists in the library.

Because of that, the database is not just a persistence convenience. It is the backbone of the product workflow. The app would lose most of its value if artifacts were ephemeral because the user would have to regenerate, re-rank, and re-justify every step each time they revisited the app. The current architecture prevents that by caching derived artifacts and, in the case of decision summaries, snapshotting the underlying runs so the report remains renderable even if source rows later change.

The frontend reflects this same lifecycle. The product page silently saves generated runs after a successful generation, exposes a library for every major artifact class, and treats hydrate-from-library as a normal state transition. The UI is therefore not simply rendering backend responses. It is coordinating movement between artifact states.

## 3. Frontend Architecture

### 3.1 Frontend stack

The frontend uses:

- Next.js static export
- React 19
- Clerk for auth UI and token retrieval
- Tailwind-based styling

Build behavior is defined in [next.config.ts](/home/repos/ideagen-saas-aws/next.config.ts):

- `output: "export"`
- `trailingSlash: true`

That means the frontend is built into static assets, then served by FastAPI from the same container.

### 3.2 Frontend responsibilities

The frontend is responsible for:

- collecting idea-generation inputs
- constraining free-tier actions in the UI
- retrieving Clerk JWTs with the configured template
- calling the API
- tracking current artifact context
- silently auto-saving generated runs
- driving the compare, decision, and execution-plan flows
- rendering saved artifacts and step guidance
- triggering export/email actions for the currently active artifact

### 3.3 Frontend-to-backend contract

The product page calls the backend for:

- subscription and usage state
- generation
- saved run CRUD
- comparison generation and CRUD
- decision report generation and CRUD
- execution plan generation and CRUD
- PDF export
- email sending
- premium recommendation flow

The frontend assumes artifact reuse is normal. The backend is therefore designed around saved runs and saved derived artifacts, not only live generation responses.

The recommendation flow deserves explicit mention because it is not just a cosmetic helper. The frontend sends the full allowed persona and constraint sets to `POST /api/recommend-combination`, the backend enforces premium access and normal API rate limits, and the returned recommendation mutates the active generation inputs in place. Architecturally, that means recommendation sits before generation as an input-shaping step rather than after generation as an analysis step.

### 3.4 How `pages/product.tsx` Actually Orchestrates The App

The product page is a large orchestration component, not just a visual shell around API calls.

At runtime it coordinates five different concerns at once:

1. input collection for generation
2. step-based workflow guidance
3. artifact loading and hydration
4. plan and quota awareness
5. delivery actions such as PDF export and email

That coordination explains why the file is large. The app needs to remember which step the user is in, what artifact is currently loaded, whether the user is new or returning, whether a step guide should be expanded or collapsed, whether a compare or report action is currently in flight, and which saved artifact lists need refreshing.

The component also has to bridge the mismatch between product-facing concepts and backend-facing concepts. The user selects model providers such as OpenAI or Gemini, but the backend runs concrete model IDs defined in `FALLBACK_CHAINS`. The user thinks in terms of "my current decision summary" or "the execution plan I just generated", but the backend thinks in terms of saved artifact IDs and source types. `pages/product.tsx` is where those translations are coordinated.

Another important detail is that the frontend deliberately performs follow-up work after primary actions. For example, generation does not end when `/api` returns. The frontend takes that response, updates the visible results state, updates usage state, marks workflow milestones, and then silently calls `POST /api/saved-results` so the new run becomes part of the artifact library. That means the visible user action of "Generate Ideas" is implemented as a multi-step client-side orchestration, not a single request.

The same pattern appears in the compare, decision, and execution-plan flows. The frontend is responsible for choosing the right endpoint, preparing the right request shape, deciding which saved artifact list to refresh, hydrating the resulting artifact into the main view, and showing the user a stable transition with loaders and notices rather than a jarring state swap. The architecture of the app therefore depends on the frontend being stateful and workflow-aware, not stateless and purely presentational.

## 4. Backend Architecture

### 4.1 FastAPI as control plane

[api/index.py](/home/repos/ideagen-saas-aws/api/index.py) is the central orchestrator.

It owns:

- FastAPI app creation
- startup DB connectivity verification
- host allowlisting
- Clerk bearer-token verification
- premium and quota checks
- provider client initialization
- request-scoped orchestration of all generation and report flows
- PDF rendering responses
- email dispatch entry points
- static frontend mounting

This is an orchestrator-worker style architecture:

- FastAPI routes are the orchestrator
- `api/agent/*.py` modules are specialized LLM workers
- `api/db.py` is the persistence boundary

### 4.2 Authentication and request guards

Auth is implemented with a custom Clerk bearer dependency in [api/index.py](/home/repos/ideagen-saas-aws/api/index.py):

- the frontend obtains a Clerk JWT
- the backend verifies it against Clerk JWKS
- the decoded token is attached to the request credentials
- `sub` is used as the application `user_id`
- `pla` is used as the current plan value

Request host validation is also enforced in middleware:

- `ALLOWED_HOSTS` controls allowed production hosts
- localhost and test hosts are always allowed
- wildcard host patterns like `*.awsapprunner.com` are supported
- `/health` bypasses the host allowlist

### 4.3 Public vs protected routes

Most app routes are protected by Clerk auth.

Current public routes:

- `GET /health`
- `POST /api/download-pdf`

Protected routes include:

- `GET /api/subscription`
- `POST /api`
- saved result routes
- compare routes
- rank report routes
- stakeholder report routes
- `POST /api/email`
- `POST /api/recommend-combination`

### 4.4 Current model and provider runtime

The backend initializes clients for:

- OpenAI
- DeepSeek
- Grok
- Gemini

Current primary generation model constants in [api/index.py](/home/repos/ideagen-saas-aws/api/index.py):

- Grok: `grok-4-1-fast-reasoning`
- Gemini: `gemini-2.5-flash`
- OpenAI: `gpt-5-nano`
- DeepSeek: `deepseek-chat`

Current fallback constants:

- `grok-4-fast-non-reasoning`
- `gemini-2.5-flash-lite`
- `gpt-5-mini`
- `deepseek-chat-v3.1`

`FALLBACK_CHAINS` maps each primary model to:

- a provider label
- an ordered fallback chain

### 4.5 Agent modules

The backend uses the following specialized agent modules:

- [api/agent/idea_generation_agent.py](/home/repos/ideagen-saas-aws/api/agent/idea_generation_agent.py)
- [api/agent/rank_result_agent.py](/home/repos/ideagen-saas-aws/api/agent/rank_result_agent.py)
- [api/agent/compare_results_agent.py](/home/repos/ideagen-saas-aws/api/agent/compare_results_agent.py)
- [api/agent/rank_report_agent.py](/home/repos/ideagen-saas-aws/api/agent/rank_report_agent.py)
- [api/agent/recommend_combination_agent.py](/home/repos/ideagen-saas-aws/api/agent/recommend_combination_agent.py)
- [api/agent/email_agent.py](/home/repos/ideagen-saas-aws/api/agent/email_agent.py)
- [api/agent/execution_plan_agent.py](/home/repos/ideagen-saas-aws/api/agent/execution_plan_agent.py)
- [api/agent/model_fallback.py](/home/repos/ideagen-saas-aws/api/agent/model_fallback.py)

The important architectural point is that these are request-scoped workers. There is no background agent graph, queue, or inter-agent message bus.

### 4.6 How `api/index.py` Coordinates Requests In Practice

`api/index.py` is the place where product rules become runtime behavior.

Every major request goes through the same broad phases:

1. identify the user
2. determine plan and quota status
3. validate request shape and feature-specific constraints
4. load or write artifacts through `api/db.py`
5. invoke the necessary agent modules
6. normalize the response into a product-facing payload

That sequencing is why FastAPI is best described as the control plane of the application. The agent modules do the reasoning-heavy work, but they do not decide who is allowed to use a feature, how artifacts are resolved, whether a comparison can be reused from cache, when a PDF should be rendered, or how report delivery should happen. Those responsibilities remain centralized in `api/index.py`.

The startup path is also important. On startup, FastAPI only verifies database connectivity through `db.init_db()`. It does not create schema. That design is intentional and depends on the container entrypoint running Alembic first. If someone skipped the startup wrapper and ran Uvicorn directly against an empty database, the process could start but fail later when routes touched missing tables. The architecture therefore assumes a deployment discipline: migrations first, then app startup.

Authentication is similarly explicit. Rather than delegating entirely to framework defaults, the app verifies Clerk JWTs manually against the JWKS URL, applies a leeway window, relaxes audience verification, and attaches the decoded claims to the request credentials object. That gives the rest of the code a predictable source for `sub` and `pla`, which then drive user scoping and plan gating. The architecture of authorization in this app is therefore claim-driven and centralized, not scattered across route-specific ad hoc checks.

The request handlers also make a clear distinction between orchestration and storage. Route functions do not embed large amounts of SQL. They call `db.*` helpers. That keeps product flow logic in one layer and persistence semantics in another. When a route needs to create, update, or look up an artifact, it asks the persistence layer to do that. When it needs model reasoning, it asks an agent module to do that. `api/index.py` itself remains the traffic director between those concerns.

### 4.7 Prompt And Validation Architecture

The app does not treat LLM output as trusted just because a provider returned it. Every major reasoning path is built around an output contract.

For idea generation, the contract is semantic HTML rather than markdown. For ranking, comparison, recommendation, and decision-summary generation, the contract is structured JSON with required keys and shape constraints. For execution-plan generation, the contract is an even stricter JSON dossier that must survive validation and normalization before it can be returned and saved.

The practical consequence is that LLM calls are embedded inside validator loops. A first response is treated as a candidate output, not as guaranteed truth. If it violates the expected contract, the app feeds the validation errors back into the next attempt. If that still fails after the configured number of tries, the code uses deterministic fallbacks in some cases or raises a controlled error in others. This validation-first design is one of the reasons the backend can safely persist artifacts and later render them into PDFs: it does not blindly store whatever text the model emitted.

### 4.8 Execution-Plan Generation Is Its Own Subsystem

The execution-plan feature is the most architecturally complex path in the app because it combines artifact resolution, deterministic modeling, LLM narrative generation, validation, and persistence.

The backend first resolves a source context from one of three supported origins: a decision report, a comparison, or a saved run. That source context is not just an ID. It includes the chosen run, any preferred model selection, and the evidence payload that should inform the resulting plan. The backend then determines which model output within the source run should be treated as the winning or selected concept.

From there, the app can follow one of two finance modes. The default `grounded_v2` path builds a deterministic baseline dossier from assumption packs and bounded transforms, then asks an LLM to supply only the narrative sections. The `llm_v1` path allows fuller LLM generation but still forces the resulting output back through validation and baseline grounding logic. In both cases the final dossier is normalized, checked for internal consistency, annotated with provenance, and only then saved as a stakeholder report.

This is why the execution-plan endpoint cannot be explained as "just another prompt". It is a hybrid subsystem with explicit financial rules, scenario handling, profitability checks, provenance tracking, and saved output formats. It is closer to a report engine than to a generic text-generation endpoint.

## 5. Core Runtime Flows

### 5.1 Generation flow

`POST /api` is the primary generation entry point.

Flow:

1. Validate auth and quota.
2. Build system and user prompts from industry, constraints, and persona.
3. Map requested provider labels to concrete primary model IDs.
4. Run one generation task per model concurrently with `asyncio.gather`.
5. For each model, apply:
   - provider-specific generation
   - validation
   - retry with correction feedback
   - ordered fallback across model chain
6. Aggregate usage.
7. If more than one result was generated, run ranking.
8. Return `results`, `usage`, and `rank_result`.

The backend does not save the run in this endpoint. The frontend follows up by calling `POST /api/saved-results`.

What actually makes this flow reliable is the combination of concurrency and local correction loops. The route fans out one task per selected model with `asyncio.gather`, so generation latency is dominated by the slowest selected model rather than the sum of all model latencies. Inside each task, however, the model call is not "fire once and trust the output". The generation agent validates the returned HTML, strips or rejects invalid wrapper patterns such as fenced markdown, retries with correction feedback when necessary, and can fall back to the next configured model in the provider chain when the failure mode is transient. The route then aggregates the surviving outputs, tracks usage, and only afterward decides whether ranking is appropriate.

That means the route is doing three different kinds of orchestration at once:

- concurrency across requested models
- sequential fallback inside each model chain
- post-processing across the combined result set

The ranking step is also important. The route only invokes the ranking agent when there is more than one successful output to compare. If only one model is involved, the response includes a structured "ranking skipped" payload so the frontend can still behave consistently. The architecture therefore treats ranking as a first-class but conditional stage in the generation pipeline rather than bolting it on later in the UI.

### 5.2 Saved run flow

Saved runs are stored in `saved_results`.

The save route:

- rejects empty result payloads
- estimates current saved-results storage usage
- applies a plan-based storage cap
- stores the run payload and optional ranking JSON

Saved runs are the base artifact for:

- compare results
- decision summaries
- execution plans

This route is also where the product’s storage economics show up most clearly. The backend does not blindly accept every save. It estimates the size of the user’s saved-result footprint and enforces a plan-specific storage cap before writing the row. That means saved runs are durable product state, but they are still governed by account limits. The save endpoint therefore sits at the intersection of product flow, persistence, and billing policy.

### 5.3 Compare flow

`POST /api/compare-results` compares two saved runs.

Important business rule:

- the two runs must match on normalized industry, persona, constraints, and model set

Operational flow:

1. Validate token limit and run IDs.
2. Load both saved runs.
3. Enforce configuration parity.
4. Reuse a cached comparison if one exists.
5. If rank data is missing for a run, generate and persist it.
6. Select the top output from each run.
7. Run the comparison agent.
8. Save the comparison artifact.

Saved comparisons are stored in `saved_comparisons`.

The compare path is one of the best examples of why the backend is an orchestrator instead of just a thin model proxy. Before any comparison agent is invoked, the route has to prove that the two runs are meaningfully comparable. It normalizes industry, persona, constraints, and model selection to avoid comparing artifacts that came from different experimental conditions. If that parity check fails, the route rejects the request because a comparison would be misleading. If a cached comparison already exists, the route can return it and only backfill missing fields such as top outputs when older stored payloads are incomplete. If no cache exists, the route may have to generate ranking metadata for one or both runs first so it can identify the top candidate from each run before the comparison agent even has valid inputs. The comparison feature therefore depends on orchestration of saved-run loading, config validation, cache reuse, ranking backfill, comparison inference, and persistence in one coherent flow.

### 5.4 Decision summary flow

The decision-summary feature is implemented by `POST /api/rank-report` plus the saved rank-report routes.

Key behavior:

- the user may select 1-5 runs directly
- `include_all_runs` is also supported
- reports are cached by a sorted `run_ids_key`
- a saved report stores both the generated report and a snapshot of the source runs

That snapshotting matters because it allows later PDF rendering even if source runs change or disappear.

Saved decision summaries are stored in `saved_rank_reports`.

Decision-summary generation is more than "run a report prompt on some runs". The route first resolves which runs are in scope, applies product limits such as a maximum of five directly selected runs, and converts that selection into a deterministic cache key. That key is what allows the app to treat the same run set as the same logical report request, even if the user triggers it from different UI states later. When a cached report is found, the backend can reuse it and still repair missing snapshot metadata if older rows are incomplete. When a report is not cached, the route performs the expensive reasoning step, persists the report together with a run snapshot, and then renders delivery output. The saved snapshot is what makes the report durable as an artifact instead of a transient response.

### 5.5 Execution plan flow

Execution plans are implemented through `POST /api/stakeholder-report` and the saved stakeholder-report routes.

Current source modes:

- `decision_report`
- `compare_result`
- `saved_run`

Current request constraints enforced in code:

- `output` must be `json`
- `currency` must be `USD`
- `region` must be `US`
- `scenario_profile` must be `conservative`, `base`, `aggressive`, or `all`
- `finance_mode` must be `grounded_v2` or `llm_v1`

One current implementation detail is easy to miss: `scenario_profile=all` is accepted by the route, but the execution-plan builders currently normalize it to `base` before constructing the dossier. In other words, `all` is part of the public request contract today, but it does not yet produce a true multi-scenario execution-plan artifact.

Current default behavior is effectively a hybrid model:

- finance baseline is deterministic and generated from assumption packs plus bounded transforms
- narrative sections are generated by an LLM
- the final dossier is validated before being returned and saved

Saved execution plans are stored in `saved_stakeholder_reports`.

The execution-plan flow is also constrained much more tightly than the generation and comparison flows because the output is intended to be operational, not exploratory. The route only accepts supported currencies, supported regions, bounded scenario profiles, and explicit source modes. It then resolves the exact artifact context from which the plan should be derived. In the `decision_report` path, for example, it may need to recover the winning run from the report or default to the top-ranked run in the snapshot. In the `compare_result` path, it may infer the selected output from the winning side of the comparison. Only once the source context is stable does the execution-plan subsystem build its deterministic financial baseline and narrative sections. This is a more constrained and more opinionated path than generation because the product is trying to turn analysis into an action plan with traceable provenance.

### 5.6 Export and email flow

The app supports several export and delivery paths:

- generated run PDF via `POST /api/download-pdf`
- compare PDF via `GET /api/compare-results/{id}/pdf`
- decision summary PDF via `GET /api/rank-reports/{id}/pdf`
- execution plan PDF via `GET /api/stakeholder-reports/{id}/pdf`
- execution-plan presentation PDF via `GET /api/stakeholder-reports/{id}/presentation`

Email delivery is implemented separately for:

- current idea payload
- saved comparison
- saved rank report

Execution-plan email delivery is not implemented in the current product UI or backend route surface. Execution plans can be downloaded as a standard PDF or as a presentation PDF, but not emailed from the app.

Email sending uses Resend through [api/agent/email_agent.py](/home/repos/ideagen-saas-aws/api/agent/email_agent.py).

PDF rendering uses WeasyPrint through [api/utils/pdf_utils.py](/home/repos/ideagen-saas-aws/api/utils/pdf_utils.py).

The delivery layer is intentionally split between unsaved current-context exports and saved-artifact exports. `POST /api/download-pdf` and `POST /api/email` operate on the current generation payload, even if it has not yet been reloaded from storage. By contrast, compare, decision-summary, and execution-plan exports are tied to saved artifact IDs. Email support is narrower than PDF support: compare and decision-summary artifacts can be emailed, but execution plans currently stop at downloadable exports. That distinction matters because some exports are intended to reflect immediate UI state while others are intended to reflect durable saved records, and not every artifact type has the same delivery contract yet.

## 6. Persistence Architecture

### 6.1 Storage stack

The application is PostgreSQL-first.

Persistence components:

- [api/config.py](/home/repos/ideagen-saas-aws/api/config.py): resolves the active DB URL
- [api/database/session.py](/home/repos/ideagen-saas-aws/api/database/session.py): engine and sessions
- [api/database/models.py](/home/repos/ideagen-saas-aws/api/database/models.py): ORM models
- [api/db.py](/home/repos/ideagen-saas-aws/api/db.py): app-facing persistence helpers
- [alembic](/home/repos/ideagen-saas-aws/alembic): schema migration ownership

The database schema is not created on app startup. Startup only verifies connectivity. Schema changes belong to Alembic.

### 6.2 Environment resolution

[api/config.py](/home/repos/ideagen-saas-aws/api/config.py) resolves exactly one effective database URL:

- `APP_ENV=local` -> `DATABASE_URL_LOCAL`
- `APP_ENV=prod` -> `DATABASE_URL_PROD`

If `APP_ENV` is omitted:

- AWS runtime markers default it to `prod`
- otherwise it defaults to `local`

### 6.3 Core tables

Current core tables:

- `user_usage`
- `saved_results`
- `saved_rank_reports`
- `saved_comparisons`
- `saved_stakeholder_reports`

Important schema traits:

- JSON-heavy artifacts are stored as `JSONB`
- timestamps are timezone-aware
- artifact lookup paths are indexed by `user_id` and `created_at`
- usage counters have non-negative check constraints

### 6.4 Artifact and cache strategy

The persistence layer is not just CRUD. It also supports application-level caching and reproducibility:

- comparisons are reused for the same run pair
- decision summaries are reused for the same run set
- rank reports store `runs_snapshot`
- stakeholder reports store the generated dossier and assumptions

This lets the UI reload earlier work without regenerating every artifact.

### 6.5 Usage metering

`user_usage` is the authoritative source for:

- monthly token totals
- per-minute API call counts
- daily email counts
- current plan string

Current limit behavior in [api/db.py](/home/repos/ideagen-saas-aws/api/db.py):

- free API call rate: 1/minute
- premium API call rate: 5/minute
- free email sending: not allowed
- premium email sending: 10/day
- monthly token caps differ by plan

Saved-result storage caps are also plan-based.

### 6.6 How The Persistence Layer Supports Product Behavior

The persistence layer exists to support specific product behaviors, not just to "store data somewhere".

`user_usage` exists so the app can enforce usage rules consistently on the server, even if a client tries to bypass UI restrictions. `saved_results` exists so the user can move from one generation session to comparison and reporting without losing context. `saved_comparisons` and `saved_rank_reports` exist so the app can avoid re-running expensive reasoning for the same artifact selections. `saved_stakeholder_reports` exists because execution plans are meant to be reviewed, exported, and revisited, not discarded after generation.

This is also why the database schema is JSON-heavy. The product is centered on structured AI artifacts whose exact shapes evolve faster than a fully normalized relational model would comfortably allow. Instead of decomposing every report into many child tables, the architecture stores coherent artifact payloads as JSONB and uses the database primarily for identity, ownership, ordering, caching, and reuse. That is a deliberate tradeoff: stronger flexibility for evolving product artifacts, at the cost of keeping some integrity rules in application logic instead of foreign keys.

### 6.7 Session And Transaction Boundaries

The code in `api/db.py` uses short-lived SQLAlchemy sessions and explicit transaction blocks. That choice fits the request-scoped design of the whole app.

For quota updates and writes, helpers typically open a session, begin a transaction, perform a small unit of work, and close the session immediately. That minimizes the time a DB connection stays checked out while the app is still waiting on external LLM latency. The architecture would be much less stable if it held database transactions open across long model calls. Instead, the DB is used in short bursts before or after inference, which is the correct pattern for a service dominated by external API latency.

## 7. API Surface

This is the current route inventory that matters to product operation.

| Route | Auth | Purpose |
| --- | --- | --- |
| `GET /api/subscription` | yes | Sync user record and return plan/usage |
| `POST /api` | yes | Generate idea outputs and optional ranking |
| `POST /api/saved-results` | yes | Save a generated run |
| `GET /api/saved-results` | yes | List saved runs |
| `GET /api/saved-results/{id}` | yes | Load one saved run |
| `DELETE /api/saved-results/{id}` | yes | Delete one saved run |
| `DELETE /api/saved-results` | yes | Delete all saved runs |
| `POST /api/compare-results` | yes | Generate or reuse a comparison |
| `GET /api/compare-results` | yes | List saved comparisons |
| `DELETE /api/compare-results/{id}` | yes | Delete one comparison |
| `DELETE /api/compare-results` | yes | Delete all comparisons |
| `GET /api/compare-results/{id}/pdf` | yes | Export compare PDF |
| `POST /api/compare-results/{id}/email` | yes | Email compare PDF |
| `POST /api/rank-report` | yes | Generate or reuse a decision summary |
| `GET /api/rank-reports` | yes | List saved decision summaries |
| `GET /api/rank-reports/{id}` | yes | Load one decision summary |
| `DELETE /api/rank-reports/{id}` | yes | Delete one decision summary |
| `DELETE /api/rank-reports` | yes | Delete all decision summaries |
| `GET /api/rank-reports/{id}/pdf` | yes | Export decision-summary PDF |
| `POST /api/rank-reports/{id}/email` | yes | Email decision-summary PDF |
| `POST /api/stakeholder-report` | yes | Generate and save an execution plan |
| `GET /api/stakeholder-reports` | yes | List saved execution plans |
| `GET /api/stakeholder-reports/{id}` | yes | Load one execution plan |
| `DELETE /api/stakeholder-reports/{id}` | yes | Delete one execution plan |
| `DELETE /api/stakeholder-reports` | yes | Delete all execution plans |
| `GET /api/stakeholder-reports/{id}/pdf` | yes | Export execution-plan PDF |
| `GET /api/stakeholder-reports/{id}/presentation` | yes | Export execution-plan presentation PDF |
| `POST /api/download-pdf` | no | Export current unsaved generated report |
| `POST /api/email` | yes | Email current unsaved generated report |
| `POST /api/recommend-combination` | yes, premium | Recommend persona + constraints |
| `GET /health` | no | Health probe |

One implementation detail worth keeping in mind: error response shapes are not fully standardized yet. Some handlers return `{"detail": ...}` and some quota handlers return `{"error": ...}` with HTTP 429.

The route list above is useful as an inventory, but operationally the API is better understood as four feature families plus two cross-cutting support families.

The four feature families are:

- generation and saved runs
- comparisons
- decision summaries
- execution plans

The cross-cutting support families are:

- subscription and quota introspection
- delivery actions such as PDF export and email

That grouping is how the frontend actually consumes the API. `pages/product.tsx` does not treat the route surface as a flat list of unrelated endpoints. It treats it as a workflow graph. A generation endpoint creates raw material, saved-result endpoints manage the base artifact, comparison endpoints derive a verdict from two base artifacts, decision-summary endpoints derive a stronger recommendation from one or more artifacts, and execution-plan endpoints derive an operational dossier from the output of earlier stages. Thinking about the API in those families makes the overall system design much easier to reason about than reading the route table alone.

## 8. Deployment and Runtime Packaging

### 8.1 Container shape

[Dockerfile](/home/repos/ideagen-saas-aws/Dockerfile) builds the app in two stages:

1. Node build stage
   - installs frontend dependencies
   - runs `npm run build`
   - emits the static export in `out/`
2. Python runtime stage
   - installs Python deps and WeasyPrint system packages
   - copies `api/`, Alembic files, and scripts
   - copies the frontend export into `static/`
   - starts the app through [scripts/start_server.sh](/home/repos/ideagen-saas-aws/scripts/start_server.sh)

### 8.2 Process model

The deployed service is a single container process:

- `uvicorn server:app`

That process serves:

- API routes
- `/health`
- the static frontend mounted at `/`

### 8.3 Startup behavior

[scripts/start_server.sh](/home/repos/ideagen-saas-aws/scripts/start_server.sh) does two things:

1. runs `alembic upgrade head` if a database URL is configured
2. starts Uvicorn

This is important because [api/index.py](/home/repos/ideagen-saas-aws/api/index.py) does not create schema on startup.

### 8.4 Local development

Local DB runtime is defined in [docker-compose.yml](/home/repos/ideagen-saas-aws/docker-compose.yml):

- PostgreSQL 16
- persistent local volume
- init scripts from `docker/postgres/init`

Normal local loop:

1. start local Postgres
2. set `APP_ENV=local` and `DATABASE_URL_LOCAL`
3. run `alembic upgrade head`
4. run backend and frontend

### 8.5 AWS deployment topology

Terraform models a small-SaaS AWS deployment in [terraform/main.tf](/home/repos/ideagen-saas-aws/terraform/main.tf) and related files.

Current major AWS components:

- VPC
- public and private subnets
- NAT gateway
- App Runner VPC connector
- security groups
- RDS PostgreSQL
- ECR repository
- Secrets Manager secrets
- optional Route 53 custom domain wiring

Runtime topology:

```text
Internet
  -> App Runner public HTTPS ingress
  -> app container
  -> VPC connector private egress
  -> RDS PostgreSQL in private DB subnets
```

Secrets Manager currently holds app secrets such as:

- `DATABASE_URL_PROD`
- provider API keys
- `RESEND_API_KEY`

The important architectural point here is that the application runtime only ever sees normal environment variables. It does not speak directly to Terraform state and it does not query Secrets Manager itself during request handling. Secret creation, secret population, and secret injection happen before the application starts serving traffic. That keeps the app runtime simple: by the time Uvicorn starts, configuration must already be complete.

### 8.6 Terraform architecture

Terraform is the infrastructure source of truth.

Current Terraform characteristics:

- a single root stack under [terraform](/home/repos/ideagen-saas-aws/terraform)
- remote state in S3, configured dynamically through [terraform/backend.tf](/home/repos/ideagen-saas-aws/terraform/backend.tf)
- one var-file per environment: `dev`, `test`, `prod`
- one Terraform workspace per environment

Current Terraform responsibilities include:

- networking and subnet layout
- App Runner service and VPC connector
- RDS PostgreSQL
- ECR repository and lifecycle policy
- Secrets Manager secret containers
- IAM attachments for runtime and GitHub Actions integration
- optional Route 53 custom-domain resources

Infrastructure environment selection is separate from app runtime mode:

- Terraform chooses `dev|test|prod` via var-files and workspaces
- the app chooses `local|prod` via `APP_ENV`

That distinction matters because GitHub Actions runs tests with `APP_ENV=local` even while deploying real AWS infrastructure for `dev`, `test`, or `prod`.

That separation between infrastructure environment and app runtime mode is subtle but important. The Terraform environment decides which cloud resources you are targeting. The application environment decides which database URL the Python process should resolve at startup. Those are related concerns, but not the same concern. The workflow design keeps them separate so that the deployment pipeline can test the application against a temporary local Postgres service while still provisioning or updating real AWS resources for a named environment.

### 8.7 Local deploy and destroy wrappers

Local infrastructure operations are wrapped by:

- [scripts/deploy.sh](/home/repos/ideagen-saas-aws/scripts/deploy.sh)
- [scripts/destroy.sh](/home/repos/ideagen-saas-aws/scripts/destroy.sh)

`deploy.sh` is a thin environment selector that delegates to `deploy_terraform_local.sh`.

`destroy.sh` is more opinionated. It:

- validates the selected environment and tfvars file
- bootstraps the Terraform backend
- selects the matching workspace
- disables RDS deletion protection if needed
- empties the ECR repository before destroy
- runs `terraform destroy`

This means destroy is not just a raw Terraform call. It includes cleanup steps required by the current AWS resource design.

The cleanup behavior in `destroy.sh` is especially important because some AWS resources have lifecycle constraints that plain `terraform destroy` does not smooth over by itself. ECR repositories with remaining images and RDS instances with deletion protection are the obvious examples in this stack. The wrapper script exists because the current infrastructure architecture requires those constraints to be cleared in the right order before destroy can succeed cleanly.

### 8.8 GitHub Actions delivery pipeline

Current GitHub workflows:

- [ci.yml](/home/repos/ideagen-saas-aws/.github/workflows/ci.yml)
- [deploy.yml](/home/repos/ideagen-saas-aws/.github/workflows/deploy.yml)
- [destroy.yml](/home/repos/ideagen-saas-aws/.github/workflows/destroy.yml)

CI currently covers:

- backend tests
- frontend lint
- Terraform format and validate
- Docker build

The deploy workflow is effectively the production delivery pipeline.

Current deploy flow in [deploy.yml](/home/repos/ideagen-saas-aws/.github/workflows/deploy.yml):

1. validate environment selection and tfvars metadata
2. assume AWS credentials through OIDC
3. bootstrap the Terraform backend
4. initialize Terraform and select the matching workspace
5. bootstrap prerequisite infrastructure on first deploy
6. read Terraform outputs such as ECR and RDS metadata
7. sync runtime secrets into Secrets Manager
8. if App Runner already exists, apply config first and wait for a stable state
9. build and push the Docker image to ECR
10. wait for App Runner rollout, or create App Runner on first deploy
11. verify `/health`

There are two notable design choices here:

- deployment includes backend tests before rollout
- existing App Runner services are updated in place rather than torn down and recreated

The destroy workflow is intentionally manual and gated by an explicit `DESTROY` confirmation string.

### 8.9 How Terraform, Secrets, App Runner, And The App Fit Together

The AWS side of the system is easiest to understand if you follow responsibility boundaries rather than resource names.

Terraform owns the infrastructure envelope. It creates the VPC, subnets, routing, security groups, RDS instance, ECR repository, App Runner service definition, VPC connector, and secret containers in Secrets Manager. That means Terraform decides what cloud resources exist and how they are wired together. It does not decide application behavior. The Python app still reads environment variables such as `DATABASE_URL_PROD`, `OPENAI_API_KEY`, and `RESEND_API_KEY` exactly as if it were running locally.

Secrets Manager sits between Terraform and the application runtime. Terraform creates the secret containers, and the deploy pipeline populates them with environment-specific values. App Runner then injects those values into the runtime environment. From the application's perspective, it simply sees environment variables at process startup. This separation is important because it keeps cloud secret storage concerns out of the application code while still letting the app use a normal configuration model.

App Runner is the runtime boundary. It pulls the image from ECR, runs the container, exposes public HTTPS ingress, and uses its VPC connector for private egress toward RDS. That means the container does not need to know anything about VPC routing or RDS networking. It only needs a valid database URL and working network reachability. Terraform and App Runner provide that environment; the app consumes it.

### 8.10 How GitHub Actions Actually Delivers A Change

The GitHub Actions pipeline is not just "run tests and deploy". It is the automated version of the operational contract this architecture depends on.

When code is pushed, CI first proves that the repo is internally coherent enough to ship: Python dependencies install, backend tests pass against PostgreSQL, the frontend lints cleanly, Terraform validates, and the Docker image still builds. That is the quality gate for the codebase itself.

The deploy workflow then performs the cloud-facing part of the contract. It validates that the selected tfvars file really matches the requested environment, assumes AWS credentials through OIDC, bootstraps the remote Terraform backend, selects the correct workspace, and ensures the underlying infrastructure exists. It then reads outputs such as the ECR repository URL and RDS connection metadata, syncs the actual runtime secrets into Secrets Manager, and only then builds and pushes the application image.

For an existing service, the workflow deliberately applies App Runner configuration before the image push and waits for the service to be in a safe state. After the image is pushed, it waits for App Runner to detect or apply the rollout and then verifies the `/health` endpoint. For a first deploy, it creates the App Runner service only after the prerequisites are in place. That sequencing is important because the app expects migrations, secrets, networking, and database connectivity to be correct at container startup.

In other words, GitHub Actions is part of the architecture, not external ceremony around it. The deployment pipeline enforces the order in which infrastructure, secrets, image publishing, and runtime health checks must happen for this application design to work reliably.

There is also a meaningful distinction between first deploy and subsequent deploys. On first deploy, the workflow has to bootstrap the infrastructure envelope before an App Runner service can exist at all: network, database, repository, roles, connector, and secret containers. On subsequent deploys, the problem changes. The workflow is no longer creating the whole system from scratch; it is reconciling configuration, updating secrets if necessary, publishing a new image, and rolling the existing App Runner service forward without breaking connectivity or health checks. That is why the workflow contains explicit logic for detecting an existing service and handling configuration and rollout differently in that case.

The deploy workflow also acts as the enforcement point for startup assumptions that the code itself does not verify deeply. For example, the application assumes a valid `DATABASE_URL_PROD` will exist by container startup, that the image can reach RDS through the VPC connector, and that the schema will be migrated before requests arrive. The workflow helps make those assumptions true by sequencing secret sync, Terraform application, image publication, service rollout, and health checks in the correct order. Without that operational discipline, the runtime architecture described in this document would be much more fragile in production.

## 9. Security and Reliability Boundaries

### 9.1 Security controls in the current app

Implemented controls include:

- Clerk JWT verification
- host allowlisting
- premium feature checks on the server
- usage and storage enforcement in the backend
- user-scoped artifact access in DB queries
- DB isolation through private AWS networking in production

### 9.2 Reliability patterns

The app uses several reliability patterns repeatedly:

- validation-first LLM outputs
- retry with correction feedback
- ordered model fallback
- deterministic fallback payloads for some agent failures
- saved-artifact caching to avoid repeated inference
- snapshot persistence for decision-summary reproducibility

### 9.3 Known architectural limitations

Current limitations visible in code:

- no background job queue for long-running work
- no standardized error envelope across all routes
- no first-class distributed tracing or metrics backend
- no frontend integration or end-to-end test suite in the repo
- no explicit relational foreign keys between artifact tables; relationships are application-managed

These are not theoretical gaps; they are current design choices.

### 9.4 Observability And Diagnostics

The current app does have some operational diagnostics, but they are lightweight and embedded in application behavior rather than backed by a separate observability platform.

On the backend, logging is configured centrally and noisy library logs are reduced. Route handlers and agent modules emit enough information to understand validation failures, model fallback behavior, and delivery failures during debugging. On the frontend, the user sees notices, spinners, skeleton hydration states, and lock states that correspond to long-running operations. Some report responses also include diagnostic headers such as cache and email outcome flags.

What the architecture does not yet have is a dedicated tracing or metrics system. There is no distributed trace spanning browser, API, provider calls, and PDF generation. There is no metrics backend aggregating fallback rates, queue times, or per-endpoint latency histograms. Operational visibility therefore exists, but it is still application-level rather than platform-level.

## 10. Testing Posture

The repo has backend-focused tests under [tests](/home/repos/ideagen-saas-aws/tests).

Current test coverage includes:

- config resolution
- Alembic migration behavior
- database contract behavior
- usage and concurrency behavior
- SQLite-to-Postgres import tool behavior

Current gaps:

- no automated frontend behavior tests
- no end-to-end product-flow tests
- no API contract test suite covering the full FastAPI route surface

### 10.1 Testing What Matters Versus What Is Missing

The existing tests are strongest around the parts of the system that were most sensitive during the Postgres migration: configuration resolution, Alembic correctness, DB contract behavior, concurrency safety around counters, and import tooling. That gives the backend storage layer a reasonable safety baseline.

What is still missing is broad system verification of the end-to-end product behavior. There is no automated test that signs in, generates a run, confirms auto-save, compares two runs, creates a decision summary, and then generates an execution plan. There is also no contract suite that locks down every response shape the frontend relies on. That means the architecture is documented and partially tested, but not yet fully exercised as a whole system in automation.

## 11. Supporting Documents

This file is the main system document. The other docs should be treated as drill-down references:

- [README.md](/home/repos/ideagen-saas-aws/README.md): setup and repo entry point
- [technical_backend.md](/home/repos/ideagen-saas-aws/technical_backend.md): backend-specific detail
- [api_reference.md](/home/repos/ideagen-saas-aws/api_reference.md): route-by-route request and response reference
- [data_model.md](/home/repos/ideagen-saas-aws/data_model.md): schema detail
- [agentic_architecture.md](/home/repos/ideagen-saas-aws/agentic_architecture.md): agent orchestration detail
- [ux_flow.md](/home/repos/ideagen-saas-aws/ux_flow.md): user workflow and step-guide behavior
- [deployment_runbook.md](/home/repos/ideagen-saas-aws/deployment_runbook.md): deployment and ops detail
- [billing_limits.md](/home/repos/ideagen-saas-aws/billing_limits.md): quota and plan detail
- [security_privacy.md](/home/repos/ideagen-saas-aws/security_privacy.md): security and privacy notes

Those docs should deepen this one, not compete with it.

## 12. Maintenance Rule

When the app changes, update this file if any of the following changed:

- primary user workflow
- route inventory
- auth or quota boundaries
- storage model
- deployment topology
- primary model or fallback strategy
- execution-plan generation rules

If a change is too detailed for this file, summarize it here and push the deeper explanation into the relevant specialist document.
