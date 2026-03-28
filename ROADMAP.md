# Agentic Roadmap

This roadmap now reflects the system after the AWS deployment, DynamoDB persistence rollout, and GitHub/Terraform operationalization. It is not the original pre-deployment wishlist anymore.

## 1. Completed foundation

These are no longer roadmap ideas. They are implemented and part of the current system.

### 1.1 Agentic backend structure

Completed:

- modular agent layout under `api/agent/`
- separate orchestration, retrieval, critique, evidence, and communication responsibilities
- provider-routed model usage
- shared fallback and logging utilities

### 1.2 Intelligent email routing

Completed:

- email agent decides whether translation is required before send
- Resend-backed delivery path

### 1.3 Multimodal extraction pipeline

Completed:

- uploaded document parsing
- audio transcription
- image-based prescription extraction

### 1.4 Research-backed clinical assistance

Completed:

- drug interaction checks
- guideline search
- research findings injected into the summary pipeline

### 1.5 Critic and regeneration loop

Completed:

- review for hallucinations, omissions, contradictions, and safety concerns
- regeneration path when the critic rejects a draft

### 1.6 Patient history and long-term memory

Completed:

- long-term patient memory
- patient-history browsing
- visit retrieval
- soft delete and restore
- assistant recall from prior visits

### 1.7 Production deployment model

Completed:

- Terraform stack
- GitHub Actions deployment workflows
- App Runner runtime
- ECR image delivery
- DynamoDB-backed memory persistence
- Secrets Manager-backed runtime secrets
- Route53-managed custom domain

## 2. Current platform state

The app is now beyond prototype stage. The current platform supports:

- deployed production runtime
- persistent patient memory outside the container
- secure runtime secret flow
- reproducible deploys
- destroy/recreate support

That means the next roadmap items are no longer “how do we get this running at all.” They are feature and quality improvements on top of a working platform.

## 3. In-progress and near-term work

### 3.1 Patient history workspace hardening

Status: In progress

Current state already includes:

- patient list
- visit timeline
- filters and pagination
- soft delete and restore
- reuse-versus-regenerate behavior

Likely next improvements:

- evidence backfill for older visits
- better historical comparison views
- stronger visit-level summary reuse controls

### 3.2 Retrieval quality and scale

Status: In progress

Current state:

- DynamoDB stores memory documents durably
- semantic ranking is still done in application code

Possible next steps:

- better query-time filtering
- more efficient retrieval paths for rename/delete/restore
- alternative vector-search architecture if scale requires it

### 3.3 Evaluation and monitoring

Status: Needed

Next useful work:

- regression suite for summary quality
- explicit hallucination and omission tracking
- evaluation datasets for critic effectiveness
- operational dashboards for deploy and runtime issues

## 4. Planned product evolution

### 4.1 Task engine and longitudinal care workflows

Status: Not started

Potential additions:

- scheduled follow-up tasks
- unresolved action carry-forward
- care-plan persistence across visits

### 4.2 Stronger human-in-the-loop controls

Status: Not started

Potential additions:

- explicit approval gates for high-risk actions
- configurable tool permissions
- stronger separation between drafting and executing actions

### 4.3 Expanded clinician workflow outputs

Status: Partially complete

Possible additions:

- referral-letter generation
- patient-instruction document generation
- structured care-plan views
- richer export/report outputs

## 5. Long-term architecture opportunities

These are not immediate blockers, but they are reasonable future directions.

### 5.1 More specialized verification layers

Potential future agents:

- verifier agent distinct from critic
- drug-safety or medication-specific specialist checks
- structured consistency checker between summary, evidence, and actions

### 5.2 More advanced memory infrastructure

Potential future changes:

- more efficient vector retrieval backend
- additional indexes for visit-history workloads
- archival strategy for older patient documents

### 5.3 External system integration

Potential future scope:

- EHR/FHIR integration
- external scheduling integrations
- downstream handoff into clinical operations systems

## 6. Roadmap summary

The biggest milestone is already complete:

- the app is now a deployed agentic system with durable memory, secrets management, and infrastructure as code

The roadmap should therefore be read as:

- refinement of quality and retrieval
- expansion of workflow capabilities
- gradual movement from documentation assistant toward broader clinical workflow assistant

