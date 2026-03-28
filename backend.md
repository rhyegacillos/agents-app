# Backend API Documentation: Agentic Healthcare SaaS

This document describes the current backend implementation of `healthcare-saas-aws`. It focuses on the runtime API, the major agents, and the storage model now in use after the AWS rollout.

It should be read together with:

- [README.md](/home/repos/healthcare-saas-aws/README.md) for the product and deployment overview
- [ARCHITECTURE.md](/home/repos/healthcare-saas-aws/ARCHITECTURE.md) for the full system architecture
- [terraform/README.md](/home/repos/healthcare-saas-aws/terraform/README.md) for infrastructure ownership

## 1. Backend composition

The backend is packaged into the same deployed application as the frontend, but logically it has three layers:

1. HTTP/API entrypoints in `api/index.py`
2. agent orchestration and domain logic in `api/agent/`
3. persistence and infrastructure adapters such as:
   - `api/memory/vector_store.py`
   - Upstash helpers in `api/agent/utils/`
   - provider routing in `api/agent/utils/provider_clients.py`

The deployed runtime is stateless with respect to local disk. Any data that must outlive the current container must be stored externally.

## 2. API surface and request classes

The exact endpoint list can continue to evolve, but the current backend behavior centers around these operational paths.

### 2.1 Summary pipeline endpoints

The consultation summary path is the most important backend flow.

It currently supports:

- starting a summary job
- streaming job progress
- reusing or regenerating prior visit outputs
- persisting visit memory and evidence

This flow is responsible for:

- parsing raw inputs
- calling the summary and research models
- critic review
- evidence generation
- persistence to DynamoDB
- SSE streaming back to the UI

### 2.2 Assistant chat endpoint

The chat path receives:

- prior conversation messages
- patient name
- current summary state

It then augments the prompt with patient history from the memory store before generating the response.

### 2.3 Patient-history endpoints

The patient-history UI depends on backend helpers that support:

- listing known patients
- paginated patient browsing
- loading visit history for a patient
- soft deletion and restore
- patient rename operations

These helpers are implemented through the memory layer rather than a separate relational database.

### 2.4 Email dispatch endpoint

The email path accepts a structured payload and decides whether it needs:

- direct send
- translation followed by send

before delivering via Resend.

## 3. Agent inventory

The backend uses a multi-agent architecture rather than a single monolithic summarization function.

### 3.1 Summary Agent

File:

- [summary_agent.py](/home/repos/healthcare-saas-aws/api/agent/summary_agent.py)

Primary responsibilities:

- orchestrate the full consultation pipeline
- start or reuse resumable jobs
- gather extracted context
- inject patient history
- coordinate research lookups
- run critic review and regeneration
- call evidence and coordinator agents
- persist memory after a successful run
- stream progress and final output

Operational significance:

- this is the core controller for the app
- if summary generation, evidence output, or patient-memory persistence is broken, the fix often starts here

### 3.2 Extraction Agent

File:

- [extraction_agent.py](/home/repos/healthcare-saas-aws/api/agent/extraction_agent.py)

Responsibilities:

- parse uploaded files
- transcribe audio
- OCR or interpret prescription images
- extract doctor and patient metadata from source text

This agent exists to normalize raw consultation inputs into a single internal context shape.

### 3.3 Research Agent

File:

- [research_agent.py](/home/repos/healthcare-saas-aws/api/agent/research_agent.py)

Responsibilities:

- drug interaction lookups
- guideline or supporting research retrieval
- concise research findings with source URLs

This agent allows the summary pipeline to remain focused on synthesis while delegating external retrieval.

### 3.4 Critic Agent

File:

- [critic_agent.py](/home/repos/healthcare-saas-aws/api/agent/critic_agent.py)

Responsibilities:

- score the draft summary
- detect hallucinations and omissions
- trigger regeneration when quality is insufficient

This agent is the main quality-control checkpoint before memory persistence.

### 3.5 Evidence Agent

File:

- [evidence_agent.py](/home/repos/healthcare-saas-aws/api/agent/evidence_agent.py)

Responsibilities:

- split the final summary into clinically meaningful statements
- match those statements to source chunks
- produce evidence snippets and source references

This is what lets the UI render “why the summary says this” instead of treating the summary as an opaque block of text.

### 3.6 Memory Agent

File:

- [memory_agent.py](/home/repos/healthcare-saas-aws/api/agent/memory_agent.py)

Responsibilities:

- persist visit memory via `remember_visit(...)`
- retrieve patient history via `recall_patient_history(...)`
- list patients and visits
- rename patients
- soft delete and restore historical documents

Important current detail:

- the deployed app now depends on DynamoDB-backed memory
- the old JSON-file fallback is no longer part of the active storage model

### 3.7 Coordinator Agent

File:

- [coordinator_agent.py](/home/repos/healthcare-saas-aws/api/agent/coordinator_agent.py)

Responsibilities:

- extract structured next actions from free-text summary output

### 3.8 Email Agent

File:

- [email_agent.py](/home/repos/healthcare-saas-aws/api/agent/email_agent.py)

Responsibilities:

- decide whether translation is needed
- translate email content when requested
- send through Resend

### 3.9 Chat Agent

File:

- [chat_agent.py](/home/repos/healthcare-saas-aws/api/agent/chat_agent.py)

Responsibilities:

- mediate assistant conversation
- merge current session context with long-term patient history
- generate contextual assistant responses

## 4. Current persistence implementation

This is the area most changed by the AWS rollout and the one most likely to be misunderstood if someone only remembers the older file-backed version.

### 4.1 DynamoDB-backed memory store

File:

- [vector_store.py](/home/repos/healthcare-saas-aws/api/memory/vector_store.py)

The memory store now initializes DynamoDB unconditionally. If `DYNAMODB_TABLE_NAME` is missing, the backend raises a runtime error instead of silently falling back to local disk.

Required environment variables:

- `DYNAMODB_TABLE_NAME`
- one of:
  - `AWS_REGION`
  - `AWS_DEFAULT_REGION`
  - `DEFAULT_AWS_REGION`

Optional local-only variable:

- `DYNAMODB_ENDPOINT_URL`

#### Item model

The store writes items with this logical shape:

- `pk`: patient partition key, for example `PATIENT#juan dela cruz`
- `sk`: document key, for example `DOC#<doc_id>`
- `item_type`: currently `document`
- `doc_id`
- `dedupe_key`
- `timestamp`
- `text`
- `embedding`
- `metadata`
- `payload`

#### Current metadata fields used by the app

The app actively depends on metadata fields such as:

- `patient_name`
- `date`
- `type`
- `doc_id`
- `encounter_id`
- `template_id`
- `time`
- `saved_at`
- `deleted`

#### Retrieval behavior

Search is currently implemented by:

1. embedding the query
2. loading candidate documents from DynamoDB
3. optionally filtering by metadata
4. scoring candidates in application code with cosine similarity
5. returning the top results

This means DynamoDB is the durable store, while semantic ranking still happens in Python.

#### Dedupe behavior

When a visit is stored, the code attempts to reuse an existing logical record if the tuple below matches:

- patient name
- date
- type
- template id
- encounter id

This is why a repeat summary for the same encounter updates the prior logical memory record instead of spraying duplicates into the patient timeline.

### 4.2 Upstash Redis-backed resumable jobs

The summary pipeline uses Upstash Redis for job and streaming state when configured.

Operationally, this provides:

- durable job IDs
- reconnect-safe SSE streaming
- status event persistence
- deduplication of repeated summary requests

This is distinct from long-term memory. Redis holds execution-state data. DynamoDB holds patient-history data.

### 4.3 Secrets Manager-backed runtime secrets

In the deployed environment, sensitive runtime values are expected to come from AWS Secrets Manager via App Runner secret references.

The backend consumes these secrets as ordinary environment variables at runtime, but the App Runner service is configured so those variables are resolved from Secrets Manager ARNs.

The important implication is:

- the backend code still reads `OPENAI_API_KEY`, `UPSTASH_REDIS_REST_TOKEN`, and similar names
- the infrastructure now decides that those values come from Secrets Manager instead of manual inline App Runner config

## 5. Summary pipeline detail

The current end-to-end summary lifecycle is:

1. request enters the consultation endpoint
2. summary job is started or reused
3. extraction agent builds visit context
4. memory agent recalls patient history
5. summary draft is generated
6. research agent runs when heuristics require it
7. critic reviews the draft
8. regeneration happens if needed
9. evidence agent maps citations
10. coordinator extracts actions
11. memory agent stores summary, notes, and evidence
12. final SSE output is streamed to the client

### 5.1 Why the memory write is late in the pipeline

The system stores memory only after the summary pipeline has succeeded far enough to produce a meaningful final artifact. This prevents partial or low-quality drafts from becoming the official long-term patient memory.

### 5.2 Why chat history can fail even when summary generation succeeds

Historically, one of the failure modes in this app was:

- summary generation reached the final stages
- memory persistence failed
- the user saw the summary but later could not retrieve patient history

That is why the memory write path is operationally important and why errors in `memory_agent.py` or `vector_store.py` affect patient-history behavior even when the rest of the app appears healthy.

## 6. Patient-history APIs and behaviors

The patient-history features are backed by the memory store rather than a dedicated relational schema.

### 6.1 Patient list

`list_known_patients()` and `list_patients_paginated(...)` derive:

- canonical patient names
- last-visit metadata
- note counts

from stored memory documents.

### 6.2 Visit timeline

`list_patient_visits(...)` derives a patient’s timeline from stored documents and metadata.

Important behaviors:

- deleted documents are hidden by default
- deleted documents can be restored
- evidence records are associated back to the encounter
- sorting is derived from metadata rather than a separate visit table

### 6.3 Rename and soft delete

Rename, delete, and restore operations are implemented as memory-store maintenance operations rather than independent database entities.

This is why the vector store includes helper methods for:

- rename
- soft delete by `doc_id`
- restore by `doc_id`

## 7. Runtime configuration contract

The backend expects a mix of public config, non-secret runtime config, and secret runtime config.

### 7.1 Non-secret config used by the app

Examples:

- `AWS_REGION`
- `DYNAMODB_TABLE_NAME`
- `GEMINI_API_URL`
- `DEEPSEEK_API_URL`
- `GROK_API_URL`
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
- `NEXT_PUBLIC_CLERK_JWT_TEMPLATE`
- `RESEND_FROM`

### 7.2 Secret config used by the app

Examples:

- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `DEEPSEEK_API_KEY`
- `GROK_API_KEY`
- `RESEND_API_KEY`
- `CLERK_SECRET_KEY`
- `CLERK_JWKS_URL`
- `BRAVE_API_KEY`
- `UPSTASH_REDIS_REST_URL`
- `UPSTASH_REDIS_REST_TOKEN`

The backend code does not care whether those arrive from:

- local `.env` files
- GitHub Actions environment secrets
- App Runner Secrets Manager references

but the deployed infrastructure does care, and the desired deployed source is now AWS Secrets Manager.

## 8. Local versus deployed behavior

### 8.1 Local development

Local runs may use:

- `.env`
- `.env.local`
- DynamoDB Local through `DYNAMODB_ENDPOINT_URL`

This is the local development path for testing memory persistence without using AWS DynamoDB.

### 8.2 Deployed AWS runtime

The production deployment path expects:

- real AWS DynamoDB
- no `DYNAMODB_ENDPOINT_URL`
- runtime secrets resolved from Secrets Manager
- App Runner runtime IAM permissions to access DynamoDB and Secrets Manager

This means the deployed application is no longer tied to container-local files for persistence.

## 9. Operational debugging guidance

When diagnosing a backend failure, it helps to separate problems by persistence boundary.

### 9.1 If summaries stream but patient history is empty

Check:

- whether DynamoDB has records
- whether memory writes failed late in the pipeline
- whether patient-name normalization caused lookup mismatches

### 9.2 If job streaming is broken but patient memory exists

Check:

- Upstash Redis configuration
- resumable job and SSE event storage

### 9.3 If deployed requests fail only in AWS

Check:

- Secrets Manager values
- App Runner secret references
- runtime IAM permissions
- environment-scoped GitHub secrets used during deploy

### 9.4 If local works but AWS does not

The first variables to compare are:

- `DYNAMODB_TABLE_NAME`
- `AWS_REGION`
- `DYNAMODB_ENDPOINT_URL`
- model provider URLs
- Upstash credentials
- Clerk secrets and JWKS URL
