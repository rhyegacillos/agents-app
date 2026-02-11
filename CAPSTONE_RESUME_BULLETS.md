# MediNotes — Resume Bullet Set (AI/ML Engineer)

- Built an agentic clinical documentation system orchestrating multi‑agent workflows (extraction, research, critic QA, evidence grounding, memory/RAG) to generate structured, verifiable visit summaries.
- Implemented MCP‑based retrieval for drug interactions and clinical guidelines, isolating external tools from core reasoning for safety and portability.
- Designed a critic‑driven regeneration loop (tournament N=3) to reduce hallucinations and enforce clinical accuracy, with persistent guardrails for long‑term quality gains.
- Added evidence‑linked summaries that map each key statement to source chunks, enabling auditability and explainability in a clinical workflow.
- Integrated multimodal inputs (PDF/DOCX/TXT, audio via Whisper, prescriptions via vision OCR) into a unified context pipeline.
- Deployed the system as a Dockerized service on AWS App Runner with ECR and a custom domain (`medinotes.agentairg.site`).
