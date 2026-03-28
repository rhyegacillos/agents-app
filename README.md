# Agentic Healthcare SaaS (AWS)

`healthcare-saas-aws` is a clinician-facing summarization and patient-history product built as a single Next.js + FastAPI application and deployed on AWS App Runner. The current production stack is no longer a purely manual App Runner deployment. It now has a Terraform-managed AWS foundation, GitHub Actions deployment workflow, DynamoDB-backed patient memory, Secrets Manager-backed runtime secrets, and Route53-managed custom-domain routing.

This document is the product and platform overview. It explains what the app does, how data persists, and how the deployed system is structured today.

For deeper operational detail, also see:

- [Architecture](/home/repos/healthcare-saas-aws/ARCHITECTURE_medinotes.md)
- [Backend API and agent details](/home/repos/healthcare-saas-aws/backend.md)
- [Deployment + ops runbook](/home/repos/healthcare-saas-aws/deployment_runbook.md)
- [GitHub Actions runbook](/home/repos/healthcare-saas-aws/github_actions_runbook.md)
- [Terraform infrastructure guide](/home/repos/healthcare-saas-aws/terraform/README.md)
- [GitHub environment runbook](/home/repos/healthcare-saas-aws/healthcare_github_environment_setup.md)
- [Infrastructure design and status](/home/repos/healthcare-saas-aws/TERRAFORM_AWS_SPEC.md)

## 1. What the application does

The app is designed for doctors who want to capture consultation inputs, generate structured clinical summaries, recall longitudinal patient context, and send patient-friendly follow-up communication without manually stitching together documents, notes, and past visits.

At a high level, the product provides:

- multi-source consultation capture
- agentic summary generation with research and quality review
- patient-memory retrieval across prior visits
- evidence-linked summaries
- patient-history browsing and visit restore/delete workflows
- assistant chat grounded in current context plus historical patient memory
- patient email drafting and dispatch

## 2. Main user workflows

### 2.1 Consultation capture

Clinicians can provide one or more of the following:

- typed notes
- uploaded PDFs, DOCX, TXT, or Markdown files
- audio recordings for transcription
- images of prescriptions or handwritten notes

The backend normalizes those inputs into a single visit context that downstream agents can reason over.

### 2.2 Summary generation

When the user clicks **Generate Summary**, the backend starts a resumable summary job. The pipeline:

1. extracts text from all available inputs
2. recalls prior patient memory
3. optionally performs research and medication/guideline checks
4. drafts the summary
5. runs a critic review
6. regenerates if the critic rejects the draft
7. maps evidence to the final summary
8. stores visit memory for future retrieval

The response streams back to the UI as Server-Sent Events so the user sees progress and intermediate status in real time.

### 2.3 Patient history workspace

The app includes a patient-history workspace rather than treating memory as an invisible backend-only feature.

Current supported behavior:

- paginated patient list
- patient timeline browsing
- date filtering and keyword filtering
- soft delete and restore
- reuse-versus-regenerate behavior for repeated encounters

The important operational change is that this history is no longer ephemeral. It now persists in DynamoDB and survives redeploys and App Runner instance replacement.

### 2.4 MediNotes Assistant

The assistant is not a generic chatbot. It has access to:

- the current in-progress consultation state
- the persisted patient history from DynamoDB-backed memory
- the current summary draft when one exists

This lets it answer questions like:

- “What happened at the patient’s last visit?”
- “Summarize what I just uploaded.”
- “What medications were previously prescribed?”

### 2.5 Patient email dispatch

After a summary is reviewed, the app can draft and send a patient-facing email. The email path uses Resend and can translate content before dispatch when the requested language is not English.

## 3. Agentic backend model

The backend is intentionally split into cooperating agents rather than one large summary function.

The core agents are:

- `extraction_agent.py`: parses uploads, audio, and prescription images
- `summary_agent.py`: orchestrates the full clinical synthesis flow
- `research_agent.py`: performs external clinical retrieval
- `critic_agent.py`: reviews output quality and correctness
- `evidence_agent.py`: grounds summary statements in source evidence
- `memory_agent.py`: persists and retrieves patient visit memory
- `coordinator_agent.py`: extracts next actions
- `email_agent.py`: handles translation and final send
- `chat_agent.py`: powers the MediNotes Assistant

This architecture matters operationally because persistence now crosses multiple layers:

- Upstash Redis persists resumable summary job state and event streams
- DynamoDB persists long-term patient memory
- Secrets Manager supplies runtime secrets to the deployed application

## 4. Current persistence model

This section is the most important change from earlier versions of the app.

### 4.1 Long-term patient memory now uses DynamoDB

The old local file-backed memory model is gone. There is no JSON fallback path in production code anymore. The application now requires a DynamoDB table for patient memory.

The store implementation lives in:

- [vector_store.py](/home/repos/healthcare-saas-aws/api/memory/vector_store.py)
- [memory_agent.py](/home/repos/healthcare-saas-aws/api/agent/memory_agent.py)

The app writes documents such as:

- `visit_summary`
- `visit_notes`
- `visit_evidence`

Each stored document includes:

- patient key
- document id
- visit date
- document type
- embedding
- source text
- metadata
- optional payload

The current DynamoDB table schema is:

- partition key: `pk`
- sort key: `sk`
- GSI: `doc_id-index`

The application stores patient documents under a patient partition, for example:

- `pk = PATIENT#juan dela cruz`
- `sk = DOC#<doc_id>`

The store also keeps a dedupe key derived from:

- patient name
- visit date
- document type
- template id
- encounter id

That dedupe behavior is why repeated saves of the same encounter update the existing logical visit memory rather than growing unbounded duplicate rows.

### 4.2 Upstash Redis is still used, but for jobs and streaming

Upstash Redis did not disappear. It simply serves a different persistence boundary.

It is used for:

- resumable summary jobs
- SSE event persistence
- reconnect-safe streaming
- job deduplication

It is not the patient-history database.

### 4.3 Secrets Manager is now part of the runtime design

The deployed app no longer depends on manually typed secret values living directly inside the App Runner configuration as the desired long-term model.

Terraform creates secret containers in AWS Secrets Manager and the deploy process writes their values at deploy time. App Runner then reads those secrets by ARN at runtime.

Current managed runtime secrets include:

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

This design keeps secret values out of Terraform state while still making the deployed service fully reproducible.

## 5. Current AWS deployment topology

The deployed production stack is intentionally simpler than the `ideagen` stack because this application does not need private RDS networking.

Current AWS components:

- App Runner for the web application
- ECR for the container image
- DynamoDB for long-term patient memory
- Secrets Manager for runtime secret values
- Route53 for the custom domain
- S3 + DynamoDB for Terraform remote state and locking

Not part of the current healthcare stack:

- VPC
- private subnets
- NAT gateway
- RDS
- security groups for database connectivity

### 5.1 Production names currently in use

The production environment was adopted from an existing manual deployment, so its names are intentionally aligned to live resources rather than freshly generated defaults.

Current production values:

- App Runner service: `consultation-app-service`
- App Runner service URL: `ymwpjvxcjn.ap-southeast-1.awsapprunner.com`
- custom domain: `medinotes.agentairg.site`
- ECR repository: `consultation-app`
- DynamoDB table: `medinotes-prod-memory`
- secret prefix: `medinotes-prod/app/*`

This is important because the repo now supports:

- redeploying the adopted existing service
- destroying the Terraform-managed stack
- recreating the stack from scratch later

### 5.2 DNS ownership

The custom domain is now Terraform-managed. That means a destroy/recreate cycle no longer leaves Route53 pointing at an old App Runner target.

Production DNS currently resolves through:

- hosted zone: `agentairg.site`
- record: `medinotes.agentairg.site`

## 6. GitHub Actions and deployment model

The repo now has a real CI/CD workflow rather than manual AWS console updates only.

Current workflows:

- [ci.yml](/home/repos/healthcare-saas-aws/.github/workflows/ci.yml)
- [deploy.yml](/home/repos/healthcare-saas-aws/.github/workflows/deploy.yml)
- [destroy.yml](/home/repos/healthcare-saas-aws/.github/workflows/destroy.yml)

### 6.1 Current branch behavior

Current behavior is intentionally **prod-only on push**:

- push to `healthcare-saas-aws` runs test, docker build, and `Deploy / prod`

`dev` still exists as a Terraform environment and a GitHub environment, but it is no longer auto-deployed on push. It is for manual workflow execution when needed.

### 6.2 GitHub environment model

The repo uses:

- `healthcare-dev`
- `healthcare-prod`

These are not the same as Terraform `dev` and `prod`. GitHub environments exist to scope deployment secrets and the AWS OIDC role.

Both healthcare GitHub environments intentionally use the same dedicated AWS role today:

- `arn:aws:iam::348375262167:role/github-actions-healthcare-deploy`

That role is restricted by GitHub environment in its trust policy, which is what gives you branch/environment isolation even though the ARN is the same in both healthcare environments.

### 6.3 Deploy order

The deploy flow is designed to avoid the App Runner race conditions that came up in other repos:

1. initialize remote Terraform backend
2. select the Terraform workspace
3. apply Terraform prerequisites and configuration
4. sync runtime secrets into Secrets Manager
5. build and push the Docker image to ECR
6. let App Runner auto-deploy the new image
7. wait for the service to return to `RUNNING`
8. verify the health endpoint

This order matters because it ensures the service already has the correct runtime configuration and secret references before the new image is rolled out.

## 7. Local development model

Local development is intentionally different from AWS production where it should be different.

### 7.1 Local app runtime

The application can still run locally with:

- `npm run dev`

and the Python backend in the same repository.

### 7.2 Local DynamoDB

Local testing of patient-memory behavior now uses DynamoDB Local rather than a JSON file.

Start DynamoDB Local:

```bash
docker compose -f docker-compose.local.yml up -d
```

Required local environment variables:

```bash
export DYNAMODB_TABLE_NAME=medinotes-memory
export DYNAMODB_ENDPOINT_URL=http://localhost:8001
export AWS_REGION=ap-southeast-1
export AWS_ACCESS_KEY_ID=dummy
export AWS_SECRET_ACCESS_KEY=dummy
```

Create the local table:

```bash
bash tools/create_memory_table.sh medinotes-memory
```

### 7.3 Deployed AWS runtime

When deployed to AWS:

- `DYNAMODB_ENDPOINT_URL` must be unset
- App Runner uses the runtime role to reach DynamoDB and Secrets Manager directly
- the deployed service reads its non-secret config from environment variables and its secret config from Secrets Manager

## 8. Operational expectations

### 8.1 What survives redeploys

These survive a normal image redeploy:

- DynamoDB patient memory
- Secrets Manager secret values
- Route53 custom-domain records
- ECR repository and image history

### 8.2 What does not survive a destroy

If the Terraform stack is destroyed, infrastructure resources are removed. However, the destroy path has been hardened so that:

- ECR images are emptied before repository deletion
- Secrets Manager secret names are immediately reusable
- Route53 records are removed with the stack

### 8.3 What the application now guarantees better than before

Compared with the earlier manual deployment model, the current app now has:

- persistent patient memory outside the container filesystem
- deploy-time secret synchronization into AWS Secrets Manager
- reproducible AWS infrastructure
- Route53 ownership under Terraform
- GitHub Actions deployment using environment-scoped credentials

## 9. Where to look next

If you are trying to understand a specific layer:

- app behavior and system topology: [Architecture](/home/repos/healthcare-saas-aws/ARCHITECTURE_medinotes.md)
- API, agents, and request lifecycle: [backend.md](/home/repos/healthcare-saas-aws/backend.md)
- infrastructure resources and deploy/destroy semantics: [terraform/README.md](/home/repos/healthcare-saas-aws/terraform/README.md)
- GitHub environments, IAM role, and branch policies: [healthcare_github_environment_setup.md](/home/repos/healthcare-saas-aws/healthcare_github_environment_setup.md)
