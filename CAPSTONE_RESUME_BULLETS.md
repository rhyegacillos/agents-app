# MediNotes — Resume Bullet Set (AI/ML Engineer)

- Built an agentic clinical documentation platform that orchestrates extraction, research, critic QA, evidence grounding, memory retrieval, and action extraction to generate structured visit summaries from multimodal consultation inputs.
- Designed a critic-driven regeneration loop that reviews drafts for hallucinations, omissions, contradictions, and safety gaps before allowing summaries to become persisted patient memory.
- Implemented evidence-linked clinical summaries that map summary statements back to source snippets and external references for auditability and explainability.
- Migrated long-term patient memory from ephemeral local storage to a DynamoDB-backed retrieval layer, enabling patient-history continuity across App Runner redeploys and container replacement.
- Integrated multimodal ingestion for notes, uploaded documents, audio transcription, and prescription-image OCR into a unified clinical context pipeline.
- Deployed the application on AWS using App Runner, ECR, DynamoDB, Secrets Manager, Route53, Terraform, and GitHub Actions with environment-scoped deployment identity and secret management.

