# MediNotes — One‑Page Capstone (AI/ML Engineer)

## Summary
MediNotes is an agentic clinical documentation platform that converts unstructured clinical inputs into structured, verifiable visit summaries with safety checks, evidence linking, and longitudinal memory. The project demonstrates real‑world agent orchestration, retrieval, evaluation loops, and explainability in a clinical domain.

## Core Contributions
- **Agentic orchestration**: Summary Agent coordinates Extraction, Research (MCP), Critic, Evidence, Memory, and Coordinator agents.
- **Grounded outputs**: Evidence Agent links summary statements to source chunks for auditability.
- **QA loop**: Critic Agent detects hallucinations/omissions and triggers tournament regeneration.
- **RAG memory**: Longitudinal patient history stored and retrieved via embeddings.
- **Streaming UX**: SSE for live status updates and resumable jobs.

## Architecture Snapshot
- **Inputs**: notes, PDFs/DOCX/TXT, audio (Whisper), prescription images (vision model).
- **Models**: DeepSeek (summary), Gemini (critic + chat), OpenAI (OCR + embeddings).
- **External tools**: MCP Brave Search for drug interactions/guidelines.
- **Persistence**: DynamoDB-backed vector store with deduped encounter IDs.

## Deployment
- Dockerized single container
- ECR + AWS App Runner
- Custom domain: `medinotes.agentairg.site`

## Why It Matters
This capstone demonstrates a production‑grade agentic pipeline with robust evaluation, explainable outputs, and real-world deployment in a safety‑critical domain.
