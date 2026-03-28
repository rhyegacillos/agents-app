# Bedrock-Only Provider Spec

## Goal
Run the assistant entirely on AWS Bedrock and remove the runtime dependency on Grok.

This change is driven by an operational constraint:
- Grok credits are exhausted.
- The system must continue to support tool calling, high-risk flows, and plain chat without requiring `GROK_API_KEY`.
- The migration should remain reversible so switching back to Grok later is operationally easy.

## Problem Statement
The repository already exposes a provider switch through `AI_PROVIDER=bedrock`, but the runtime is not actually Bedrock-only today.

Current implemented behavior:
- Low-risk/plain chat can use Bedrock when `AI_PROVIDER=bedrock`.
- High-risk and tool-calling requests are always routed to Grok.
- If Grok is unavailable or out of credits, tool-heavy requests fail even when Bedrock is selected as the provider.

This creates a configuration trap:
- Operators can set `AI_PROVIDER=bedrock`.
- The system still depends on Grok for a meaningful subset of user requests.

## Current State
### Routing
- `backend/server.py`
  - High-risk requests call `call_grok_with_mcp(...)`.
  - Low-risk requests use `AI_PROVIDER` to select Grok or Bedrock.

### Provider runtimes
- `backend/services/chat_runtime/grok_runner.py`
  - Grok runtime via `openai-agents` + MCP server integration.
- `backend/services/chat_runtime/bedrock_runner.py`
  - Bedrock runtime via `bedrock_client.converse(...)`.
- `backend/services/bedrock_tools.py`
  - Bedrock tool loop using MCP tool discovery and tool result handoff.

### Configuration
- `backend/config.py`
  - `AI_PROVIDER` defaults to `bedrock`.
  - Grok variables are still defined and used by high-risk flows.
- `terraform/terraform.tfvars`
  - `ai_provider = "bedrock"` already exists.
- `terraform/prod.tfvars`
  - `ai_provider = "bedrock"` already exists.

### Documentation mismatch
- The deployed configuration suggests Bedrock-first operation.
- The implemented code still hard-requires Grok for high-risk/tool paths.

## Target State
All chat flows run on Bedrock:
- Low-risk/plain chat.
- High-risk/tool-calling chat.
- Search/citation flows.
- PDF/email/file-related tool flows.
- Approved-memory enforcement and retry loops.

After this change:
- No user-facing chat route should require Grok.
- `GROK_API_KEY` should not be required for normal operation.
- Bedrock must be the single active LLM provider for the assistant runtime.
- Provider selection should remain structurally reversible even if Bedrock is the deployed default.

## Scope
### In scope
- Route all chat execution paths to Bedrock.
- Keep provider switching architecture reversible.
- Keep existing risk classification behavior unless it is strictly needed for routing cleanup.
- Preserve MCP tool usage for high-risk/tool-calling flows.
- Preserve truth-gated high-risk finalization behavior.
- Preserve approved-memory validation behavior.
- Update config, docs, and deploy defaults to reflect Bedrock-only operation.
- Add regression tests for Bedrock-only routing.

### Out of scope
- Replacing MCP with a different tool framework.
- Rewriting the truth gate architecture.
- Changing the product UX.
- Removing every Grok-related artifact in one pass if some are historical or backup-only.
- Multi-provider fallback.

## Functional Requirements
### 1) Provider contract
- Bedrock is the only supported runtime for the assistant chat path.
- `AI_PROVIDER=bedrock` must be sufficient for all supported request types.
- Missing `GROK_API_KEY` must not break chat execution.
- The code structure should still allow `AI_PROVIDER=grok` to be re-enabled later without a large refactor.

### 2) Routing contract
- High-risk requests must no longer hard-route to Grok.
- Tool-capable requests must execute through the Bedrock tool loop.
- Low-risk requests may still use a simpler Bedrock path if desired, but the path must remain Bedrock-based.

### 3) Tool-calling contract
- Bedrock must remain able to discover and invoke MCP tools.
- Tool outputs must continue to flow into truth-gated rendering and validation.
- Tool-calling behavior must not depend on the Grok runtime being present.

### 4) Error-handling contract
- Bedrock model candidate fallback stays enabled.
- Errors must clearly indicate Bedrock configuration or model-access issues.
- No error should instruct the operator to configure Grok for normal Bedrock-only usage.

### 5) Deploy/config contract
- Dev and prod defaults must remain Bedrock.
- Grok secrets must become optional for Bedrock-only deployments.
- Docs must stop implying that Bedrock mode still requires Grok for some requests.
- Re-enabling Grok later should primarily be a configuration and validation exercise, not a rewrite.

## Proposed Design
### A) Route all chat execution through Bedrock
Update `backend/server.py` so that:
- High-risk requests use `call_bedrock(...)` instead of `call_grok_with_mcp(...)`.
- Low-risk requests also use Bedrock when the deployment is Bedrock-only.

Implementation direction:
- Replace the hardcoded high-risk Grok branch in `_generate_response_for_risk(...)`.
- Keep `classify_risk(...)` for quota, truth-gate, and behavior controls, but not for provider switching to Grok.
- Preserve a provider-selection seam so future Bedrock ↔ Grok switching remains localized to routing and config.

### B) Preserve high-risk post-processing
Keep the existing high-risk output pipeline:
- Classification.
- Tool execution.
- Truth-gated finalization.
- Quota accounting.

If `finalize_high_risk_response(...)` currently assumes Grok result objects, adapt the interface so Bedrock-driven high-risk responses can pass through the same contract cleanly.

### C) Keep a distinct Bedrock low-risk mode if useful
Two valid implementation shapes are acceptable:

Option 1:
- Use the existing Bedrock tool loop for both low-risk and high-risk requests.

Option 2:
- Keep a lighter Bedrock prose path for low-risk chat.
- Use the Bedrock tool loop for high-risk/tool-calling chat.

Preferred option:
- Option 2, if it keeps behavior simple and avoids unnecessary tool setup on conversational turns.

### D) Make Grok optional or deprecated in config
Update `backend/config.py` and surrounding docs to make the contract explicit:
- Grok settings are optional and unused in Bedrock-only mode.
- Bedrock is the default and supported provider.
- Grok code remains present unless a later cleanup explicitly removes it.

If a future cleanup removes Grok entirely, that should happen as a follow-up change rather than being blocked on this migration.

### E) Prefer dormancy over deletion
For this migration:
- Do not delete Grok runtime modules.
- Do not remove `AI_PROVIDER`.
- Do not collapse the code into a Bedrock-only architecture that would make Grok restoration expensive.

Preferred posture:
- Bedrock is active by default.
- Grok is inactive and optional.
- Switching back later should require config changes plus regression validation.

## Required Code Changes
### Backend runtime
- `backend/server.py`
  - Remove the hardcoded high-risk Grok route.
  - Ensure all request tiers can execute with Bedrock only.
  - Keep provider-routing logic easy to reverse later.
- `backend/services/chat_runtime/bedrock_runner.py`
  - Confirm it supports high-risk and tool-heavy flows end-to-end.
  - Extend interfaces only if needed for truth-gate integration.
- `backend/services/bedrock_tools.py`
  - Keep as the canonical tool loop for Bedrock.

### Configuration
- `backend/config.py`
  - Clarify that `bedrock_client` is the primary runtime client, not merely a fallback.
- `.env.example`
  - Add or complete Bedrock-first environment examples.
  - Mark Grok settings optional or legacy.
- Terraform vars and deployment docs
  - Keep `ai_provider = "bedrock"`.
  - Document Grok secrets as optional for Bedrock-only deployments.

### Tests
- Add routing tests proving high-risk messages no longer call Grok.
- Add tests proving Bedrock-only mode works with no `GROK_API_KEY`.
- Add regression coverage for representative high-risk requests:
  - web/search/citation query
  - PDF/export request
  - email/send request
  - file-attached request

### Documentation
- Update architecture and operations docs to reflect Bedrock-only supported operation.
- Remove or qualify statements that imply tool-heavy requests route to Grok.

## Acceptance Criteria
- A deployment with `AI_PROVIDER=bedrock` and no `GROK_API_KEY` can complete:
  - plain Q&A
  - search/citation requests
  - PDF generation flows
  - email-related tool flows
  - file-assisted tool flows
- No high-risk chat path calls `call_grok_with_mcp(...)`.
- No normal user request fails solely because Grok credentials are missing.
- Bedrock model candidate retry behavior still works.
- Existing truth-gate and quota behavior remains intact.
- Dev and prod deploy docs explicitly support Bedrock-only operation.
- A future switch back to `AI_PROVIDER=grok` remains technically feasible without restoring deleted runtime modules.

## Rollout Plan
1. Patch routing so high-risk/tool paths use Bedrock.
2. Add regression tests for Bedrock-only execution.
3. Update docs and environment examples.
4. Deploy to dev with no Grok key configured.
5. Validate representative low-risk and high-risk prompts.
6. Promote to prod after parity check.

## Risks
- Bedrock tool behavior may differ from Grok on multi-step tool planning.
- High-risk finalization may currently be more coupled to Grok result shapes than expected.
- Bedrock latency may increase when tools are enabled broadly.
- Some old docs and backup files may continue to mention Grok until a later cleanup pass.

## Non-Negotiables
- Bedrock-only mode must be real, not partial.
- Configuration must match runtime behavior.
- Tool-heavy requests must not silently depend on Grok.
- Missing Grok credits must not block the core product.
- Reversibility must be preserved unless a later change explicitly chooses permanent Grok removal.

## Follow-Up Cleanup
After Bedrock-only mode is stable, consider a second pass to:
- Remove unused Grok runtime code.
- Remove Grok-only environment variables from default deploy paths.
- Delete or archive outdated docs that still describe Grok as an active dependency.
- Revisit whether `AI_PROVIDER` is still needed if Bedrock becomes the only supported provider.
