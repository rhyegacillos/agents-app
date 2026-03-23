# Security + Privacy Overview

This document summarizes the current security and data-handling posture after the PostgreSQL migration.

## 1. Data Handling

Stored application data includes:

- industry, tone, constraints, persona-related selections
- generated model outputs
- per-run rankings
- compare results
- decision summary reports
- execution plans / stakeholder dossiers
- usage counters for tokens, API calls, and email sends

Email addresses are used only when a user requests report delivery.

## 2. Current Storage Model

Persistent application data is stored in PostgreSQL.

Current intended deployment shape:

- local development -> local PostgreSQL
- AWS deployment -> Amazon RDS for PostgreSQL

Security implications of the migration:

- sensitive/runtime data is no longer tied to a local SQLite file inside the container
- production durability comes from managed database infrastructure
- schema changes are versioned and reviewable via Alembic

## 3. Data Retention

Artifact retention remains product-driven:

- saved runs and reports remain until deleted by the user
- no automated purge policy is currently implemented in the app

From a storage standpoint, those records now live in Postgres tables rather than SQLite text rows.

## 4. Auth and Request Protection

Authentication stack:

- Clerk for identity
- JWT verification against JWKS in [api/index.py](/home/repos/ideagen-saas-aws/api/index.py)

Request access controls:

- protected routes require a valid Clerk bearer token
- host allowlist middleware rejects unexpected hosts
- `/health` bypasses host allowlist checks so App Runner health probes can succeed

## 5. Secrets Handling

Application/provider secrets are environment-driven.

Current intended production path:

- runtime secret values are stored in AWS Secrets Manager
- App Runner receives secret references, not hardcoded values in source
- RDS master password is AWS-managed in Secrets Manager

This is a material improvement over mixing operational config into ad hoc local runtime state.

## 6. Storage Security Considerations

Current production assumptions:

- RDS is deployed in private subnets
- App Runner reaches RDS through a VPC connector
- public traffic reaches only the App Runner service ingress

Important consequence:

- database access is not expected directly from the public internet

## 7. Third-Party Services

- Clerk: authentication and identity
- OpenAI: model provider
- Google Gemini: model provider
- DeepSeek: model provider
- Grok / xAI: model provider
- Resend: transactional email
- AWS:
  - App Runner
  - RDS PostgreSQL
  - ECR
  - Secrets Manager
  - Route 53
  - CloudWatch

## 8. Email Policy

- emails are transactional
- delivery happens only on explicit user action
- reports are attached as PDFs when supported by the route
- sender defaults to a no-reply address unless overridden by `EMAIL_FROM`

## 9. Recommendations

- keep `ALLOWED_HOSTS` restricted to intended domains
- rotate provider and email API keys periodically
- prefer Secrets Manager or equivalent secret injection in production
- treat Alembic revisions as part of the security/change-control process for database evolution
- use HTTPS-only public access in production
