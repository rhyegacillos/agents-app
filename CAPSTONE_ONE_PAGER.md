# MediNotes — One-Page Capstone (AI/ML Engineer)

## What it is

MediNotes is an agentic clinical documentation system that turns multimodal consultation inputs into structured visit summaries, evidence-linked outputs, and reusable patient history. It is deployed on AWS and designed to persist patient memory across redeploys.

## Core technical contribution

The core contribution is a production-oriented multi-agent architecture rather than a single LLM call.

Specialized agents handle:

- extraction from notes, files, audio, and prescription images
- summary orchestration
- research-backed safety checks
- critic review and regeneration
- evidence grounding
- long-term patient memory
- assistant chat over current and historical context

## Why it matters

Clinical notes are high-stakes and messy. A useful system must do more than generate fluent text. It must:

- combine multiple input modalities
- preserve continuity across visits
- reduce hallucinations
- ground outputs in evidence
- survive production deploys without losing memory

## Current deployed stack

- Next.js + FastAPI single application
- AWS App Runner runtime
- ECR image delivery
- DynamoDB-backed patient memory
- Secrets Manager-backed runtime secrets
- Route53 custom domain: `medinotes.agentairg.site`
- GitHub Actions + Terraform for deployment

## AI/ML engineering highlights

- Agentic orchestration instead of monolithic prompting
- Retrieval-augmented clinical context with durable DynamoDB persistence
- Critic-driven regeneration loop for quality control
- Evidence-linked outputs for explainability
- Provider-routed model usage across summary, critic, chat, OCR, embeddings, and transcription
- Real deployment and operational infrastructure, not just prototype logic

## What makes it stronger than a normal demo

This project includes the hard parts that many AI demos skip:

- persistence outside the container
- secure secret handling
- infrastructure as code
- branch-isolated deployment identity
- production redeploy and destroy workflows

It demonstrates the ability to take an agentic system from application logic into a maintainable deployed platform.

