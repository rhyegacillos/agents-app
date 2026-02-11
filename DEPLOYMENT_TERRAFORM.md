# Terraform Deployment Guide (Deep Dive, Local + Scripts)

This guide is a detailed, self-contained runbook for deploying this app with
Terraform locally. It matches the repo layout and the scripts in `scripts/`.
It is intentionally verbose so you can follow it step by step without
cross references.

-------------------------------------------------------------------------------

## 0) Quick start (if you already know the basics)

```bash
# 1) Confirm AWS identity
aws sts get-caller-identity

# 2) Deploy dev (uses scripts/deploy.sh)
./scripts/deploy.sh dev

# 3) Destroy dev (uses scripts/destroy.sh)
./scripts/destroy.sh dev
```

If you are unsure about any of those steps, read the full guide below.

-------------------------------------------------------------------------------

### 0.1 Conventions (balanced default)

- Commands are bash unless labeled PowerShell.
- Replace placeholders like `<env>`, `<bucket>`, `<ACM_CERT_ARN>`.
- Sections are ordered from high-level to low-level detail.
- Use Quick Reference when you just need the minimal commands.

-------------------------------------------------------------------------------

## 1) What this does (scope)

Terraform provisions all AWS infrastructure required for the app:
- Lambda (backend API + async worker)
- ECR (container image repository)
- API Gateway (REST API)
- S3 (frontend hosting + memory storage)
- CloudFront (global CDN for frontend)
- IAM roles and policies
- ACM certificate (for custom domain in us-east-1)
- Route53 records (if custom domain is enabled)
- Terraform state backend (S3 + DynamoDB locking)

The scripts:
- `scripts/deploy.sh` builds, applies Terraform, uploads frontend, invalidates CF.
- `scripts/destroy.sh` refreshes state, empties buckets, and destroys infra.

-------------------------------------------------------------------------------

## 1.1 What is Terraform (detailed)

Terraform is an Infrastructure as Code (IaC) tool. You describe the desired
state of your infrastructure in configuration files, and Terraform makes the
real infrastructure match that desired state.

Key concepts:

- **Configuration (HCL)**:
  `.tf` files describe resources (S3, Lambda, CloudFront, etc) and how they
  connect. The configuration is declarative: you say *what* you want, not how
  to build it step by step.

- **Providers**:
  Providers are plugins that let Terraform talk to external APIs. This repo
  uses the AWS provider, configured in `terraform/versions.tf`.

- **State**:
  Terraform stores a state file to track what it created. This repo uses an
  S3 backend with DynamoDB locking so the state is shared and safe.

- **Plan**:
  `terraform plan` shows what Terraform *would* change.

- **Apply**:
  `terraform apply` actually creates/updates/deletes resources to match the
  configuration.

- **Drift**:
  If someone changes resources manually in AWS, Terraform detects a mismatch.
  Running `terraform apply` or `terraform apply -refresh-only` re-syncs state.

- **Workspaces**:
  Workspaces isolate state. This repo uses dev/test/prod workspaces so each
  environment gets its own state and its own resources.

Why it matters in this repo:
Terraform is the single source of truth for AWS resources. Without it, you
would need to manually create and keep multiple AWS services in sync, which is
error‑prone and hard to reproduce.

-------------------------------------------------------------------------------

## 1.2 Terraform concepts you will actually use here (deeper)

This section goes deeper than 1.1 and focuses on the concepts that show up in
this repo and in day‑to‑day usage.

### 1.2.1 Resources
Resources are the core building blocks (e.g. `aws_s3_bucket`, `aws_lambda_function`).
Each resource block maps to a real AWS object and has:
- a **type** (`aws_lambda_function`)
- a **name** (`api`)
- a **body** (settings like runtime, tags, timeout)

Example:
```hcl
resource "aws_lambda_function" "api" {
  function_name = "digital-assistant-dev-api"
}
```

### 1.2.2 Data sources
Data sources read existing AWS data that Terraform does not create.
Example: account id or hosted zone lookup.

Example:
```hcl
data "aws_caller_identity" "current" {}
```

### 1.2.3 Variables
Variables make the configuration reusable across environments.
You declare them in `variables.tf` and set them in `.tfvars` or env vars.

Example:
```hcl
variable "environment" {
  type = string
}
```

### 1.2.4 Locals
Locals are computed values derived from variables or resource outputs.
They reduce duplication and keep names consistent.

Example:
```hcl
locals {
  name_prefix = "${var.project_name}-${var.environment}"
}
```

### 1.2.5 Outputs
Outputs expose values after apply so scripts and humans can use them.

Example:
```hcl
output "api_gateway_url" {
  value = "https://${aws_api_gateway_rest_api.main.id}.execute-api.${data.aws_region.current.id}.amazonaws.com/${aws_api_gateway_stage.main.stage_name}"
}
```

### 1.2.6 Dependencies
Terraform builds a dependency graph automatically based on references.
You can force a dependency using `depends_on` when required.

Example:
```hcl
resource "aws_lambda_function" "api" {
  depends_on = [aws_cloudfront_distribution.main]
}
```

### 1.2.7 Providers and regions
Providers define *where* Terraform creates resources.
This repo uses:
- default provider for most resources
- `aws.us_east_1` alias for ACM (required by CloudFront)

Example:
```hcl
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}
```

### 1.2.8 State and locking
Terraform state tracks everything it created.
This repo stores state in S3 and uses DynamoDB for locking:
- prevents two deploys from running at the same time
- avoids state corruption

### 1.2.9 Plan vs apply
- `terraform plan`: preview only, no changes
- `terraform apply`: actually changes AWS resources

In scripts, apply is used directly to keep deploys fast.

### 1.2.10 Refresh and drift
If resources are changed outside Terraform, use:
```bash
terraform apply -refresh-only
```
This syncs state without changing real infrastructure.

### 1.2.11 Workspaces (env isolation)
Workspaces keep separate state files per environment:
- dev, test, prod
- same code, separate infrastructure

### 1.2.12 Lifecycle rules
Terraform supports lifecycle settings like:
- `create_before_destroy` for ACM certificates
- `prevent_destroy` (not used here)

These prevent downtime or accidental deletion.

-------------------------------------------------------------------------------

## 1.3 Advanced Terraform topics (optional, but practical)

These are not required for basic deploys, but they are useful when the project
grows or when you need to refactor infrastructure.

### 1.3.1 Modules (when to split)
Use modules when your `main.tf` becomes too large or when you repeat patterns.

Typical split:
- `modules/network` for VPC, subnets
- `modules/compute` for Lambda/ECS
- `modules/storage` for S3 and DynamoDB

When to *not* split:
- small projects where a single file is clearer
- when you still iterate quickly on the base architecture

### 1.3.2 State file anatomy (safe inspection)
The state file is JSON that Terraform reads and writes. It contains:
- resource instances
- IDs and ARNs
- dependency relationships

Safe ways to inspect:
```bash
terraform state list
terraform state show aws_lambda_function.api
```

Do NOT edit the state file manually unless you are recovering from corruption.

### 1.3.3 Import existing resources
If something exists in AWS but not in Terraform state, import it.

Example:
```bash
terraform import aws_s3_bucket.frontend digital-assistant-dev-frontend-123456789012
```

After import:
- run `terraform plan` to confirm no drift
- update configuration if Terraform wants to recreate or delete it

### 1.3.4 Moving or renaming resources
If you rename a resource block, Terraform thinks it's a new resource unless
you map it.

Use `moved` blocks (Terraform 1.1+):
```hcl
moved {
  from = aws_s3_bucket.frontend
  to   = aws_s3_bucket.frontend_assets
}
```

### 1.3.5 State locking details
The DynamoDB lock prevents concurrent `apply` or `destroy`.
If a lock is stuck:
```bash
terraform force-unlock <LOCK_ID>
```
Use only when you are sure no other Terraform is running.

### 1.3.6 Backends and migration
If you change backend settings, you must reinitialize:
```bash
terraform init -reconfigure
```
If you are moving state between backends, use:
```bash
terraform init -migrate-state
```

### 1.3.7 Workspace hygiene
Delete unused workspaces to avoid confusion:
```bash
terraform workspace select default
terraform workspace delete <env>
```

### 1.3.8 State security
State may contain secrets (like API keys). Protect it by:
- using S3 bucket encryption
- restricting bucket access to admins only
- never copying the state file into public repos

-------------------------------------------------------------------------------

## 2) Why use Terraform here

- Reproducible infrastructure: no click ops drift.
- Multi environment support: dev/test/prod are isolated.
- Safer teardown: everything is tracked and can be destroyed.
- Clear dependency graph: CloudFront -> S3 -> ACM -> Route53, etc.

-------------------------------------------------------------------------------

## 3) When to use local Terraform

Use local Terraform when:
- you need full infra control
- you are debugging a deploy issue
- you need to create or destroy dev/test/prod
- you need to bootstrap or repair state

If you only want to test UI and API locally, run the app without Terraform.

-------------------------------------------------------------------------------

## 4) High level architecture and request flow

Browser -> CloudFront -> S3 (frontend assets)
Browser -> API Gateway -> Lambda (backend)
Lambda -> Grok or Bedrock (AI provider)
Lambda -> S3 (chat history storage)

Terraform manages all of these resources.

-------------------------------------------------------------------------------

## 5) Repo map (what is where) and what you actually edit

This section is explicit about what each file is for and what you are expected
to change. You are not supposed to create random files. You only edit the ones
listed below, and only in the ways described.

### 5.1 Terraform files (you will edit these)

- `terraform/terraform.tfvars`
  - Purpose: default values used for all environments.
  - You edit this for values that apply to dev/test/prod.
  - Example (typical):
    ```hcl
    project_name      = "digital-assistant"
    environment       = "dev"
    ai_provider       = "grok"
    grok_api_url      = "https://api.x.ai/v1"
    grok_model_id     = "grok-4-1-fast"
    use_custom_domain = false
    ```

- `terraform/prod.tfvars`
  - Purpose: overrides for production only.
  - You edit this when prod needs different values.
  - Example:
    ```hcl
    environment       = "prod"
    use_custom_domain = true
    root_domain       = "agentairg.site"
    custom_subdomain  = "digital-assistant"
    ```

- `terraform/terraform.tfvars.local`
  - Purpose: local secrets. This file is untracked and must be created by you.
  - You must create it once on each machine that deploys locally.
  - Example:
    ```hcl
    grok_api_key             = "YOUR_REAL_GROK_KEY"
    brave_api_key            = "YOUR_BRAVE_API_KEY"
    resend_api_key           = "YOUR_RESEND_API_KEY"
    upstash_redis_rest_url   = "https://YOUR_UPSTASH_REDIS.upstash.io"
    upstash_redis_rest_token = "YOUR_UPSTASH_TOKEN"
    ```
  - Do not commit this file. It is intentionally ignored.

### 5.2 Terraform files (create these from scratch if starting a new infra)

If you were building this from zero, these are the exact files you would
create and what goes inside each. Treat these as templates you can copy.

#### 5.2.1 `terraform/main.tf` (core resources)
Purpose: defines all AWS resources (Lambda, API Gateway, S3, CloudFront,
IAM, ACM, Route53).

Create the file and start with this skeleton:
```hcl
terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Example resource placeholders (replace with real resources)
# resource "aws_s3_bucket" "frontend" { ... }
# resource "aws_lambda_function" "api" { ... }
```

Then add your actual resources. Below is a concrete, detailed blueprint that
matches how this repo is structured.

##### S3 (memory bucket)
Purpose: store conversation history objects.

Key points:
- bucket name includes project, environment, and account id
- block all public access
- enforce bucket ownership
- configure CORS for **direct-to-S3 browser uploads** (presigned `PUT`) when using `POST /uploads/presign`

Example pattern:
```hcl
resource "aws_s3_bucket" "memory" {
  bucket = "${local.name_prefix}-memory-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "memory" {
  bucket = aws_s3_bucket.memory.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Required for direct-to-S3 uploads from the frontend (browser PUT to presigned URL).
# allowed_origins should match your CloudFront URL (and custom domain if used).
resource "aws_s3_bucket_cors_configuration" "memory" {
  bucket = aws_s3_bucket.memory.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT", "POST", "HEAD"]
    allowed_origins = [
      "https://${aws_cloudfront_distribution.main.domain_name}",
    ]
    expose_headers  = ["ETag", "x-amz-request-id", "x-amz-id-2"]
    max_age_seconds = 3000
  }
}
```

##### S3 (frontend bucket)
Purpose: host the static frontend.

Key points:
- bucket name includes project, environment, and account id
- website configuration required for CloudFront origin
- public read policy for static assets

Example pattern:
```hcl
resource "aws_s3_bucket" "frontend" {
  bucket = "${local.name_prefix}-frontend-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_website_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  index_document { suffix = "index.html" }
  error_document { key = "404.html" }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = "*"
      Action = "s3:GetObject"
      Resource = "${aws_s3_bucket.frontend.arn}/*"
    }]
  })
}
```

##### IAM role and policies (Lambda execution)
Purpose: allow Lambda to run and access S3 / Bedrock.

Key points:
- trust policy allows `lambda.amazonaws.com`
- attach AWSLambdaBasicExecutionRole
- attach S3 access
- attach Bedrock access (if using Bedrock)

Example pattern:
```hcl
resource "aws_iam_role" "lambda_role" {
  name = "${local.name_prefix}-lambda-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}
```

##### Lambda function (backend API)
Purpose: run the FastAPI handler in Lambda.

Key points:
- uses a container image from ECR
- API + worker share the same image
- environment variables include AI provider and S3 bucket
- `depends_on` CloudFront so CORS origins resolve

Example pattern:
```hcl
resource "aws_lambda_function" "api" {
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.lambda.repository_url}:${var.lambda_image_tag}"
  function_name = "${local.name_prefix}-api"
  role          = aws_iam_role.lambda_role.arn
  architectures = ["x86_64"]

  environment {
    variables = {
      S3_BUCKET     = aws_s3_bucket.memory.id
      AI_PROVIDER   = var.ai_provider
      GROK_API_KEY  = var.grok_api_key
      GROK_API_URL  = var.grok_api_url
      GROK_MODEL_ID = var.grok_model_id
    }
  }
}
```

Worker pattern (same image, different handler):
```hcl
resource "aws_lambda_function" "worker" {
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.lambda.repository_url}:${var.lambda_image_tag}"
  function_name = "${local.name_prefix}-worker"
  role          = aws_iam_role.lambda_role.arn
  architectures = ["x86_64"]
  timeout       = var.worker_lambda_timeout
  memory_size   = var.worker_lambda_memory_mb

  image_config {
    command = ["worker_handler.handler"]
  }
}
```

##### API Gateway (REST API)
Purpose: expose `/`, `/chat`, `/health`, `/jobs/{job_id}`, `/memory/*`, `/uploads`, `/downloads/*`.

Key points:
- REST API (v1)
- CORS configured
- integration type AWS_PROXY
- routes map to Lambda
- Lambda permission required for API Gateway

Example pattern (simplified):
```hcl
resource "aws_api_gateway_rest_api" "main" {
  name = "${local.name_prefix}-api-gateway"
}

resource "aws_api_gateway_resource" "proxy" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "{proxy+}"
}

resource "aws_api_gateway_method" "proxy_any" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.proxy.id
  http_method   = "ANY"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "proxy_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.proxy.id
  http_method             = aws_api_gateway_method.proxy_any.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.api.invoke_arn
}
```

##### CloudFront distribution (frontend CDN)
Purpose: serve the frontend globally with HTTPS and SPA routing.

Key points:
- origin is S3 website endpoint
- default cache behavior redirects to HTTPS
- SPA fallback 404 -> 200 index.html
- viewer certificate uses ACM if custom domain

Example pattern:
```hcl
resource "aws_cloudfront_distribution" "main" {
  origin {
    domain_name = aws_s3_bucket_website_configuration.frontend.website_endpoint
    origin_id   = "S3-${aws_s3_bucket.frontend.id}"
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = "S3-${aws_s3_bucket.frontend.id}"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
  }

  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  viewer_certificate {
    acm_certificate_arn            = var.use_custom_domain ? aws_acm_certificate.site[0].arn : null
    cloudfront_default_certificate = var.use_custom_domain ? false : true
    ssl_support_method             = var.use_custom_domain ? "sni-only" : null
  }
}
```

##### ACM certificate (custom domain)
Purpose: enable HTTPS on your custom domain.

Key points:
- CloudFront requires ACM certs in us-east-1
- requires provider alias `aws.us_east_1`
- DNS validation via Route53

Example pattern:
```hcl
resource "aws_acm_certificate" "site" {
  provider          = aws.us_east_1
  domain_name       = "${var.project_name}.${var.root_domain}"
  validation_method = "DNS"
}
```

##### Route53 records (custom domain)
Purpose: prove domain ownership and point DNS to CloudFront.

Key points:
- create validation CNAME records from ACM
- create alias A/AAAA records to CloudFront distribution

Example pattern:
```hcl
resource "aws_route53_record" "site_validation" {
  for_each = { for dvo in aws_acm_certificate.site[0].domain_validation_options : dvo.domain_name => dvo }
  zone_id = data.aws_route53_zone.root[0].zone_id
  name    = each.value.resource_record_name
  type    = each.value.resource_record_type
  records = [each.value.resource_record_value]
  ttl     = 300
}

resource "aws_route53_record" "alias_root" {
  zone_id = data.aws_route53_zone.root[0].zone_id
  name    = "${var.project_name}.${var.root_domain}"
  type    = "A"
  alias {
    name                   = aws_cloudfront_distribution.main.domain_name
    zone_id                = aws_cloudfront_distribution.main.hosted_zone_id
    evaluate_target_health = false
  }
}
```

Note: the actual repo already implements these resources in `terraform/main.tf`.
If you are creating from scratch, follow these patterns and keep naming
consistent with `project_name` and `environment`.

##### End to end wiring (how values flow)
This is the full data flow from inputs to outputs:

1) Inputs (`terraform.tfvars` + `prod.tfvars` + `terraform.tfvars.local`)
   - project_name, environment, ai_provider, grok_api_key, etc.

2) Locals in `main.tf` compute derived names:
   - `name_prefix = "${var.project_name}-${var.environment}"`
   - `custom_domain_fqdn = "${var.project_name}.${var.root_domain}"`

3) Resources use locals + vars:
   - S3 buckets use `name_prefix` + account id
   - Lambda uses `name_prefix` for function_name
   - API Gateway uses `name_prefix` for API name
   - CloudFront uses S3 website endpoint as origin
   - ACM uses custom_domain_fqdn (if enabled)
   - Route53 uses ACM validation records and CloudFront alias

4) Outputs expose what scripts need:
   - `api_gateway_url`
   - `cloudfront_url`
   - `s3_frontend_bucket`
   - `s3_memory_bucket`

##### Dependency graph (creation order)
This shows the dependency chain in plain English:

1) S3 buckets (frontend + memory)
2) IAM role and policies
3) Lambda (depends on IAM role)
4) API Gateway (integrates Lambda)
5) (Optional) Route53 zone lookup
6) (Optional) ACM certificate request (us-east-1)
7) (Optional) Route53 validation records
8) (Optional) ACM validation completion
9) CloudFront distribution (depends on ACM validation if custom domain)
10) (Optional) Route53 alias records to CloudFront

##### Full copy paste `terraform/main.tf` (minimal but working)
This is a complete example that matches this repo's architecture. You can copy
this into a new project and adjust names and variables.

```hcl
data "aws_caller_identity" "current" {}

locals {
  aliases = var.use_custom_domain && var.root_domain != "" ? [
    "${var.project_name}.${var.root_domain}"
  ] : []

  name_prefix = "${var.project_name}-${var.environment}"
  custom_domain_fqdn = "${var.project_name}.${var.root_domain}"
  create_www_alias   = false

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# S3 bucket for conversation memory
resource "aws_s3_bucket" "memory" {
  bucket = "${local.name_prefix}-memory-${data.aws_caller_identity.current.account_id}"
  tags   = local.common_tags
}

resource "aws_s3_bucket_public_access_block" "memory" {
  bucket = aws_s3_bucket.memory.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "memory" {
  bucket = aws_s3_bucket.memory.id
  rule { object_ownership = "BucketOwnerEnforced" }
}

# S3 bucket for frontend static website
resource "aws_s3_bucket" "frontend" {
  bucket = "${local.name_prefix}-frontend-${data.aws_caller_identity.current.account_id}"
  tags   = local.common_tags
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_website_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  index_document { suffix = "index.html" }
  error_document { key = "404.html" }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "PublicReadGetObject"
      Effect    = "Allow"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.frontend.arn}/*"
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.frontend]
}

# IAM role for Lambda
resource "aws_iam_role" "lambda_role" {
  name = "${local.name_prefix}-lambda-role"
  tags = local.common_tags
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
  role       = aws_iam_role.lambda_role.name
}

resource "aws_iam_role_policy_attachment" "lambda_bedrock" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonBedrockFullAccess"
  role       = aws_iam_role.lambda_role.name
}

resource "aws_iam_role_policy_attachment" "lambda_s3" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
  role       = aws_iam_role.lambda_role.name
}

# ECR repository for Lambda container image
resource "aws_ecr_repository" "lambda" {
  name                 = "${local.name_prefix}-lambda"
  image_tag_mutability = "MUTABLE"
  tags                 = local.common_tags

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository_policy" "lambda" {
  repository = aws_ecr_repository.lambda.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "LambdaECRImageRetrievalPolicy"
        Effect = "Allow"
        Principal = { Service = "lambda.amazonaws.com" }
        Action = [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchCheckLayerAvailability"
        ]
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }
    ]
  })
}

resource "aws_ecr_lifecycle_policy" "lambda" {
  repository = aws_ecr_repository.lambda.name
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 1 day"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = { type = "expire" }
      }
    ]
  })
}

# Lambda function
resource "aws_lambda_function" "api" {
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.lambda.repository_url}:${var.lambda_image_tag}"
  function_name = "${local.name_prefix}-api"
  role          = aws_iam_role.lambda_role.arn
  architectures = ["x86_64"]
  memory_size   = var.lambda_memory_mb
  timeout       = var.lambda_timeout
  tags          = local.common_tags

  environment {
    variables = {
      CORS_ORIGINS              = var.use_custom_domain ? "https://${local.custom_domain_fqdn}" : "https://${aws_cloudfront_distribution.main.domain_name}"
      S3_BUCKET                 = aws_s3_bucket.memory.id
      USE_S3                    = "true"
      DEFAULT_AWS_REGION        = var.default_aws_region
      ENABLE_MCP_SEARCH         = var.enable_mcp_search ? "true" : "false"
      BEDROCK_MODEL_ID          = var.bedrock_model_id
      AI_PROVIDER               = var.ai_provider
      GROK_MODEL_ID             = var.grok_model_id
      GROK_API_URL              = var.grok_api_url
      GROK_API_KEY              = var.grok_api_key
      BRAVE_API_KEY             = var.brave_api_key
      RESEND_API_KEY            = var.resend_api_key
      UPSTASH_REDIS_REST_URL    = var.upstash_redis_rest_url
      UPSTASH_REDIS_REST_TOKEN  = var.upstash_redis_rest_token
      ASYNC_CHAT_ENABLED        = var.async_chat_enabled ? "true" : "false"
      ASYNC_JOB_TTL_SECONDS     = tostring(var.async_job_ttl_seconds)
      ASYNC_WORKER_FUNCTION_NAME = aws_lambda_function.worker.function_name
      MEMORY_EXTRACT_SYNC        = "false"
      UPLOADS_DIR               = var.uploads_dir
      MAX_UPLOAD_MB             = tostring(var.max_upload_mb)
      UPLOAD_ALLOWED_EXTS       = var.upload_allowed_exts
    }
  }

  depends_on = [aws_cloudfront_distribution.main]
}

resource "aws_lambda_function" "worker" {
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.lambda.repository_url}:${var.lambda_image_tag}"
  function_name = "${local.name_prefix}-worker"
  role          = aws_iam_role.lambda_role.arn
  architectures = ["x86_64"]
  memory_size   = var.worker_lambda_memory_mb
  timeout       = var.worker_lambda_timeout
  tags          = local.common_tags

  image_config {
    command = ["worker_handler.handler"]
  }

  environment {
    variables = {
      CORS_ORIGINS              = var.use_custom_domain ? "https://${local.custom_domain_fqdn}" : "https://${aws_cloudfront_distribution.main.domain_name}"
      S3_BUCKET                 = aws_s3_bucket.memory.id
      USE_S3                    = "true"
      DEFAULT_AWS_REGION        = var.default_aws_region
      ENABLE_MCP_SEARCH         = var.enable_mcp_search ? "true" : "false"
      BEDROCK_MODEL_ID          = var.bedrock_model_id
      AI_PROVIDER               = var.ai_provider
      GROK_MODEL_ID             = var.grok_model_id
      GROK_API_URL              = var.grok_api_url
      GROK_API_KEY              = var.grok_api_key
      BRAVE_API_KEY             = var.brave_api_key
      RESEND_API_KEY            = var.resend_api_key
      UPSTASH_REDIS_REST_URL    = var.upstash_redis_rest_url
      UPSTASH_REDIS_REST_TOKEN  = var.upstash_redis_rest_token
      ASYNC_CHAT_ENABLED        = "false"
      ASYNC_JOB_TTL_SECONDS     = tostring(var.async_job_ttl_seconds)
      WORKER_MAX_SECONDS        = tostring(var.worker_max_seconds)
      LLM_TIMEOUT_SECONDS       = tostring(var.worker_llm_timeout_seconds)
      MCP_STARTUP_TIMEOUT_SECONDS = tostring(var.worker_mcp_startup_timeout_seconds)
      RUNNER_TIMEOUT_SECONDS      = tostring(var.worker_runner_timeout_seconds)
      MEMORY_EXTRACT_SYNC         = "true"
      UPLOADS_DIR               = var.uploads_dir
      MAX_UPLOAD_MB             = tostring(var.max_upload_mb)
      UPLOAD_ALLOWED_EXTS       = var.upload_allowed_exts
    }
  }

  depends_on = [aws_cloudfront_distribution.main]
}

# API Gateway REST API
resource "aws_api_gateway_rest_api" "main" {
  name = "${local.name_prefix}-api-gateway"
  tags = local.common_tags
}

resource "aws_api_gateway_resource" "proxy" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "{proxy+}"
}

resource "aws_api_gateway_method" "proxy_any" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.proxy.id
  http_method   = "ANY"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "proxy_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.proxy.id
  http_method             = aws_api_gateway_method.proxy_any.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.api.invoke_arn
}

resource "aws_lambda_permission" "api_gw" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

# CloudFront distribution
resource "aws_cloudfront_distribution" "main" {
  aliases = local.aliases
  depends_on = [aws_acm_certificate_validation.site]

  viewer_certificate {
    acm_certificate_arn            = var.use_custom_domain ? aws_acm_certificate.site[0].arn : null
    cloudfront_default_certificate = var.use_custom_domain ? false : true
    ssl_support_method             = var.use_custom_domain ? "sni-only" : null
    minimum_protocol_version       = "TLSv1.2_2021"
  }

  origin {
    domain_name = aws_s3_bucket_website_configuration.frontend.website_endpoint
    origin_id   = "S3-${aws_s3_bucket.frontend.id}"
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  tags                = local.common_tags

  default_cache_behavior {
    allowed_methods  = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${aws_s3_bucket.frontend.id}"
    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }
    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 3600
    max_ttl                = 86400
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }
}

# Optional: Custom domain configuration (only created when use_custom_domain = true)
data "aws_route53_zone" "root" {
  count        = var.use_custom_domain ? 1 : 0
  name         = var.root_domain
  private_zone = false
}

resource "aws_acm_certificate" "site" {
  count                     = var.use_custom_domain ? 1 : 0
  provider                  = aws.us_east_1
  domain_name               = local.custom_domain_fqdn
  subject_alternative_names = []
  validation_method         = "DNS"
  lifecycle { create_before_destroy = true }
  tags = local.common_tags
}

resource "aws_route53_record" "site_validation" {
  for_each = {
    for dvo in aws_acm_certificate.site[0].domain_validation_options : dvo.domain_name => dvo
  }
  zone_id = data.aws_route53_zone.root[0].zone_id
  name    = each.value.resource_record_name
  type    = each.value.resource_record_type
  ttl     = 300
  records = [each.value.resource_record_value]
}

resource "aws_acm_certificate_validation" "site" {
  count           = var.use_custom_domain ? 1 : 0
  provider        = aws.us_east_1
  certificate_arn = aws_acm_certificate.site[0].arn
  validation_record_fqdns = [
    for r in aws_route53_record.site_validation : r.fqdn
  ]
}

resource "aws_route53_record" "alias_root" {
  count   = var.use_custom_domain ? 1 : 0
  zone_id = data.aws_route53_zone.root[0].zone_id
  name    = local.custom_domain_fqdn
  type    = "A"
  alias {
    name                   = aws_cloudfront_distribution.main.domain_name
    zone_id                = aws_cloudfront_distribution.main.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "alias_root_ipv6" {
  count   = var.use_custom_domain ? 1 : 0
  zone_id = data.aws_route53_zone.root[0].zone_id
  name    = local.custom_domain_fqdn
  type    = "AAAA"
  alias {
    name                   = aws_cloudfront_distribution.main.domain_name
    zone_id                = aws_cloudfront_distribution.main.hosted_zone_id
    evaluate_target_health = false
  }
}
```

##### Full production `main.tf` (exact structure used in this repo)
This is the fully expanded version that mirrors the current repo structure,
including optional www aliases and ACM validation options handling.

Note: this file assumes provider aliases are defined in `terraform/versions.tf`
for `aws.us_east_1` and `aws.ap_southeast_1`.

```hcl
data "aws_caller_identity" "current" {}

locals {
  aliases = var.use_custom_domain && var.root_domain != "" ? [
    "${var.project_name}.${var.root_domain}"
  ] : []

  name_prefix = "${var.project_name}-${var.environment}"

  custom_domain_fqdn = "${var.project_name}.${var.root_domain}"
  create_www_alias   = false
  acm_validation_options = var.use_custom_domain && length(aws_acm_certificate.site) > 0 ? aws_acm_certificate.site[0].domain_validation_options : []

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# S3 bucket for conversation memory
resource "aws_s3_bucket" "memory" {
  bucket = "${local.name_prefix}-memory-${data.aws_caller_identity.current.account_id}"
  tags   = local.common_tags
}

resource "aws_s3_bucket_public_access_block" "memory" {
  bucket = aws_s3_bucket.memory.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "memory" {
  bucket = aws_s3_bucket.memory.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# S3 bucket for frontend static website
resource "aws_s3_bucket" "frontend" {
  bucket = "${local.name_prefix}-frontend-${data.aws_caller_identity.current.account_id}"
  tags   = local.common_tags
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_website_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  index_document {
    suffix = "index.html"
  }

  error_document {
    key = "404.html"
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicReadGetObject"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.frontend.arn}/*"
      },
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.frontend]
}

# IAM role for Lambda
resource "aws_iam_role" "lambda_role" {
  name = "${local.name_prefix}-lambda-role"
  tags = local.common_tags

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
  role       = aws_iam_role.lambda_role.name
}

resource "aws_iam_role_policy_attachment" "lambda_bedrock" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonBedrockFullAccess"
  role       = aws_iam_role.lambda_role.name
}

resource "aws_iam_role_policy_attachment" "lambda_s3" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
  role       = aws_iam_role.lambda_role.name
}

# ECR repository for Lambda container image
resource "aws_ecr_repository" "lambda" {
  name                 = "${local.name_prefix}-lambda"
  image_tag_mutability = "MUTABLE"
  tags                 = local.common_tags

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository_policy" "lambda" {
  repository = aws_ecr_repository.lambda.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "LambdaECRImageRetrievalPolicy"
        Effect = "Allow"
        Principal = { Service = "lambda.amazonaws.com" }
        Action = [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchCheckLayerAvailability"
        ]
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }
    ]
  })
}

resource "aws_ecr_lifecycle_policy" "lambda" {
  repository = aws_ecr_repository.lambda.name
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 1 day"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = { type = "expire" }
      }
    ]
  })
}

# Lambda function
resource "aws_lambda_function" "api" {
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.lambda.repository_url}:${var.lambda_image_tag}"
  function_name = "${local.name_prefix}-api"
  role          = aws_iam_role.lambda_role.arn
  architectures = ["x86_64"]
  memory_size   = var.lambda_memory_mb
  timeout       = var.lambda_timeout
  tags          = local.common_tags

  environment {
    variables = {
      CORS_ORIGINS              = var.use_custom_domain ? "https://${local.custom_domain_fqdn}" : "https://${aws_cloudfront_distribution.main.domain_name}"
      S3_BUCKET                 = aws_s3_bucket.memory.id
      USE_S3                    = "true"
      DEFAULT_AWS_REGION        = var.default_aws_region
      ENABLE_MCP_SEARCH         = var.enable_mcp_search ? "true" : "false"
      BEDROCK_MODEL_ID          = var.bedrock_model_id
      AI_PROVIDER               = var.ai_provider
      GROK_MODEL_ID             = var.grok_model_id
      GROK_API_URL              = var.grok_api_url
      GROK_API_KEY              = var.grok_api_key
      BRAVE_API_KEY             = var.brave_api_key
      RESEND_API_KEY            = var.resend_api_key
      UPSTASH_REDIS_REST_URL    = var.upstash_redis_rest_url
      UPSTASH_REDIS_REST_TOKEN  = var.upstash_redis_rest_token
      ASYNC_CHAT_ENABLED        = var.async_chat_enabled ? "true" : "false"
      ASYNC_JOB_TTL_SECONDS     = tostring(var.async_job_ttl_seconds)
      ASYNC_WORKER_FUNCTION_NAME = aws_lambda_function.worker.function_name
      MEMORY_EXTRACT_SYNC        = "false"
      UPLOADS_DIR               = var.uploads_dir
      MAX_UPLOAD_MB             = tostring(var.max_upload_mb)
      UPLOAD_ALLOWED_EXTS       = var.upload_allowed_exts
    }
  }

  # Ensure Lambda waits for the distribution to exist
  depends_on = [aws_cloudfront_distribution.main]
}

resource "aws_lambda_function" "worker" {
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.lambda.repository_url}:${var.lambda_image_tag}"
  function_name = "${local.name_prefix}-worker"
  role          = aws_iam_role.lambda_role.arn
  architectures = ["x86_64"]
  memory_size   = var.worker_lambda_memory_mb
  timeout       = var.worker_lambda_timeout
  tags          = local.common_tags

  image_config {
    command = ["worker_handler.handler"]
  }

  environment {
    variables = {
      CORS_ORIGINS              = var.use_custom_domain ? "https://${local.custom_domain_fqdn}" : "https://${aws_cloudfront_distribution.main.domain_name}"
      S3_BUCKET                 = aws_s3_bucket.memory.id
      USE_S3                    = "true"
      DEFAULT_AWS_REGION        = var.default_aws_region
      ENABLE_MCP_SEARCH         = var.enable_mcp_search ? "true" : "false"
      BEDROCK_MODEL_ID          = var.bedrock_model_id
      AI_PROVIDER               = var.ai_provider
      GROK_MODEL_ID             = var.grok_model_id
      GROK_API_URL              = var.grok_api_url
      GROK_API_KEY              = var.grok_api_key
      BRAVE_API_KEY             = var.brave_api_key
      RESEND_API_KEY            = var.resend_api_key
      UPSTASH_REDIS_REST_URL    = var.upstash_redis_rest_url
      UPSTASH_REDIS_REST_TOKEN  = var.upstash_redis_rest_token
      ASYNC_CHAT_ENABLED        = "false"
      ASYNC_JOB_TTL_SECONDS     = tostring(var.async_job_ttl_seconds)
      WORKER_MAX_SECONDS        = tostring(var.worker_max_seconds)
      LLM_TIMEOUT_SECONDS       = tostring(var.worker_llm_timeout_seconds)
      MCP_STARTUP_TIMEOUT_SECONDS = tostring(var.worker_mcp_startup_timeout_seconds)
      RUNNER_TIMEOUT_SECONDS      = tostring(var.worker_runner_timeout_seconds)
      MEMORY_EXTRACT_SYNC         = "true"
      UPLOADS_DIR               = var.uploads_dir
      MAX_UPLOAD_MB             = tostring(var.max_upload_mb)
      UPLOAD_ALLOWED_EXTS       = var.upload_allowed_exts
    }
  }

  # Ensure Lambda waits for the distribution to exist
  depends_on = [aws_cloudfront_distribution.main]
}

# API Gateway REST API
resource "aws_api_gateway_rest_api" "main" {
  name = "${local.name_prefix}-api-gateway"
  tags = local.common_tags
}

resource "aws_api_gateway_resource" "proxy" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "{proxy+}"
}

resource "aws_api_gateway_method" "proxy_any" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.proxy.id
  http_method   = "ANY"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "proxy_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.proxy.id
  http_method             = aws_api_gateway_method.proxy_any.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.api.invoke_arn
}

# Lambda permission for API Gateway
resource "aws_lambda_permission" "api_gw" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

# CloudFront distribution
resource "aws_cloudfront_distribution" "main" {
  aliases = local.aliases
  depends_on = [aws_acm_certificate_validation.site]

  viewer_certificate {
    acm_certificate_arn            = var.use_custom_domain ? aws_acm_certificate.site[0].arn : null
    cloudfront_default_certificate = var.use_custom_domain ? false : true
    ssl_support_method             = var.use_custom_domain ? "sni-only" : null
    minimum_protocol_version       = "TLSv1.2_2021"
  }

  origin {
    domain_name = aws_s3_bucket_website_configuration.frontend.website_endpoint
    origin_id   = "S3-${aws_s3_bucket.frontend.id}"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  tags                = local.common_tags

  default_cache_behavior {
    allowed_methods  = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${aws_s3_bucket.frontend.id}"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 3600
    max_ttl                = 86400
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }
}

# Optional: Custom domain configuration (only created when use_custom_domain = true)
data "aws_route53_zone" "root" {
  count        = var.use_custom_domain ? 1 : 0
  name         = var.root_domain
  private_zone = false
}

resource "aws_acm_certificate" "site" {
  count                     = var.use_custom_domain ? 1 : 0
  provider                  = aws.us_east_1
  domain_name               = local.custom_domain_fqdn
  subject_alternative_names = local.create_www_alias ? ["www.${local.custom_domain_fqdn}"] : []
  validation_method         = "DNS"
  lifecycle { create_before_destroy = true }
  tags = local.common_tags
}

resource "aws_route53_record" "site_validation" {
  for_each = {
    for dvo in local.acm_validation_options : dvo.domain_name => dvo
  }

  zone_id = data.aws_route53_zone.root[0].zone_id
  name    = each.value.resource_record_name
  type    = each.value.resource_record_type
  ttl     = 300
  records = [each.value.resource_record_value]
}

resource "aws_acm_certificate_validation" "site" {
  count           = var.use_custom_domain ? 1 : 0
  provider        = aws.us_east_1
  certificate_arn = aws_acm_certificate.site[0].arn
  validation_record_fqdns = [
    for r in aws_route53_record.site_validation : r.fqdn
  ]
}

resource "aws_route53_record" "alias_root" {
  count   = var.use_custom_domain ? 1 : 0
  zone_id = data.aws_route53_zone.root[0].zone_id
  name    = local.custom_domain_fqdn
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.main.domain_name
    zone_id                = aws_cloudfront_distribution.main.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "alias_root_ipv6" {
  count   = var.use_custom_domain ? 1 : 0
  zone_id = data.aws_route53_zone.root[0].zone_id
  name    = local.custom_domain_fqdn
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.main.domain_name
    zone_id                = aws_cloudfront_distribution.main.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "alias_www" {
  count   = var.use_custom_domain && local.create_www_alias ? 1 : 0
  zone_id = data.aws_route53_zone.root[0].zone_id
  name    = "www.${local.custom_domain_fqdn}"
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.main.domain_name
    zone_id                = aws_cloudfront_distribution.main.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "alias_www_ipv6" {
  count   = var.use_custom_domain && local.create_www_alias ? 1 : 0
  zone_id = data.aws_route53_zone.root[0].zone_id
  name    = "www.${local.custom_domain_fqdn}"
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.main.domain_name
    zone_id                = aws_cloudfront_distribution.main.hosted_zone_id
    evaluate_target_health = false
  }
}
```

#### 5.2.2 `terraform/variables.tf` (inputs)
Purpose: declares all input variables used by Terraform.

Create the file with at least these variables:
```hcl
variable "project_name" {
  type        = string
  description = "Base name for all resources"
}

variable "environment" {
  type        = string
  description = "Environment name (dev, test, prod)"
}

variable "aws_region" {
  type        = string
  description = "AWS region for primary resources"
  default     = "ap-southeast-1"
}

variable "ai_provider" {
  type        = string
  description = "AI provider (grok or bedrock)"
  default     = "grok"
}

variable "grok_api_key" {
  type        = string
  description = "Grok API key"
  sensitive   = true
}
```

Add more variables only when you need them. Keep names snake_case.

##### Full production `variables.tf` (exact structure used in this repo)
```hcl
variable "project_name" {
  description = "Name prefix for all resources"
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.project_name))
    error_message = "Project name must contain only lowercase letters, numbers, and hyphens."
  }
}

variable "environment" {
  description = "Environment name (dev, test, prod)"
  type        = string
  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "Environment must be one of: dev, test, prod."
  }
}

variable "bedrock_model_id" {
  description = "Bedrock model ID"
  type        = string
  default     = "amazon.nova-micro-v1:0"
}

variable "grok_model_id" {
  description = "Grok model ID"
  type        = string
  default     = "grok-4-1-fast"
}

variable "grok_api_url" {
  description = "Grok API Url"
  type        = string
  default     = "https://api.x.ai/v1"
}

variable "grok_api_key" {
  description = "Grok API Key"
  type        = string
  sensitive = true
}

variable "ai_provider" {
  description = "AI Provider"
  type        = string
  default     = "bedrock"
}

variable "lambda_timeout" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 60
}

variable "api_throttle_burst_limit" {
  description = "API Gateway throttle burst limit"
  type        = number
  default     = 10
}

variable "api_throttle_rate_limit" {
  description = "API Gateway throttle rate limit"
  type        = number
  default     = 5
}

variable "use_custom_domain" {
  description = "Attach a custom domain to CloudFront"
  type        = bool
  default     = false
}

variable "root_domain" {
  description = "Apex domain name, e.g. mydomain.com"
  type        = string
  default     = ""
}
```

#### 5.2.3 `terraform/outputs.tf` (outputs)
Purpose: exposes Terraform values for scripts and for humans.

Create the file and output the values your scripts need:
```hcl
output "api_gateway_url" {
  value = "https://${aws_api_gateway_rest_api.main.id}.execute-api.${data.aws_region.current.id}.amazonaws.com/${aws_api_gateway_stage.main.stage_name}"
}

output "cloudfront_url" {
  value = "https://${aws_cloudfront_distribution.main.domain_name}"
}

output "s3_frontend_bucket" {
  value = aws_s3_bucket.frontend.bucket
}

output "s3_memory_bucket" {
  value = aws_s3_bucket.memory.id
}

output "lambda_function_name" {
  value = aws_lambda_function.api.function_name
}

output "worker_function_name" {
  value = aws_lambda_function.worker.function_name
}

output "ecr_repository_url" {
  value = aws_ecr_repository.lambda.repository_url
}
```

##### Full production `outputs.tf` (exact structure used in this repo)
```hcl
output "api_gateway_url" {
  description = "URL of the API Gateway"
  value       = "https://${aws_api_gateway_rest_api.main.id}.execute-api.${data.aws_region.current.id}.amazonaws.com/${aws_api_gateway_stage.main.stage_name}"
}

output "cloudfront_url" {
  description = "URL of the CloudFront distribution"
  value       = "https://${aws_cloudfront_distribution.main.domain_name}"
}

output "s3_frontend_bucket" {
  description = "Name of the S3 bucket for frontend"
  value       = aws_s3_bucket.frontend.id
}

output "s3_memory_bucket" {
  description = "Name of the S3 bucket for memory storage"
  value       = aws_s3_bucket.memory.id
}

output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.api.function_name
}

output "worker_function_name" {
  description = "Name of the async worker Lambda function"
  value       = aws_lambda_function.worker.function_name
}

output "ecr_repository_url" {
  description = "ECR repository URL for the Lambda image"
  value       = aws_ecr_repository.lambda.repository_url
}

output "custom_domain_url" {
  description = "Root URL of the production site"
  value       = var.use_custom_domain ? "https://${var.project_name}.${var.root_domain}" : ""
}
```
#### 5.2.4 `terraform/backend.tf` (backend placeholder)
Purpose: placeholder for backend config (S3 backend).

Create a minimal backend block and let scripts pass real values:
```hcl
terraform {
  backend "s3" {}
}
```

Do not hardcode bucket/region here unless you want to force everyone to use
the same backend. The scripts already pass backend configs at runtime.

##### Full production `versions.tf` (provider aliases)
This file pins Terraform and configures multiple AWS provider aliases used by
`main.tf`. CloudFront/ACM must use us-east-1, so we keep a separate provider.

Create `terraform/versions.tf`:
```hcl
terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  # Uses AWS CLI configuration (aws configure)
}

provider "aws" {
  alias  = "ap_southeast_1"
  region = "ap-southeast-1"
}

# CloudFront/ACM certificates must be in us-east-1
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}
```

##### Full production `backend.tf`
This is the exact backend placeholder file used in the repo.
Create `terraform/backend.tf`:
```hcl
terraform {
  backend "s3" {
    # These values will be set by deployment scripts
    # For local development, they can be passed via -backend-config
  }
}
```

### 5.3 Scripts (you do NOT edit unless changing deploy behavior)

- `scripts/deploy.sh`
  - Purpose: builds Lambda, applies Terraform, uploads frontend, invalidates CF.
  - Use: `./scripts/deploy.sh <env> [project_name]`

- `scripts/destroy.sh`
  - Purpose: refreshes state, empties buckets, destroys resources.
  - Use: `./scripts/destroy.sh <env> [project_name]`

### 5.4 Backend files (for app behavior, not Terraform)

- `backend/server.py`
  - Purpose: FastAPI app, memory storage, chat endpoints.
  - You edit this if you change the API or memory logic.

- `backend/Dockerfile`
  - Purpose: builds the Lambda container image.
  - You edit this only when dependencies or system packages change.

### 5.5 Frontend (for UI only)

- `frontend/`
  - Next.js static build. You edit this for UI changes.
  - Deployment uses `npm run build` and uploads `frontend/out`.

### 5.6 Full example configs (dev/test/prod)

These are complete examples you can copy. Adjust domains and keys.

#### terraform/terraform.tfvars (base defaults)
```hcl
project_name      = "digital-assistant"
environment       = "dev"
ai_provider       = "grok"
grok_api_url      = "https://api.x.ai/v1"
grok_model_id     = "grok-4-1-fast"
use_custom_domain = false
async_chat_enabled = false
```

Line by line (what each value does):
- `project_name`: prefix used in all resource names (S3, Lambda, API Gateway).
- `environment`: sets the workspace name and suffix in resource names.
- `ai_provider`: selects Grok vs Bedrock in the backend.
- `grok_api_url`: base URL used by the backend when Grok is selected.
- `grok_model_id`: model id passed to Grok API.
- `use_custom_domain`: enables/disables ACM + Route53 + CloudFront alias.

#### terraform/dev.tfvars (optional override for dev)
```hcl
environment = "dev"
```

Line by line:
- `environment`: keeps dev isolated. This value also controls name prefixes.

#### terraform/test.tfvars (optional override for test)
```hcl
environment = "test"
```

Line by line:
- `environment`: keeps test isolated with separate resources.

#### terraform/prod.tfvars (production overrides)
```hcl
environment       = "prod"
use_custom_domain = true
root_domain       = "agentairg.site"
custom_subdomain  = "digital-assistant"
```

Line by line:
- `environment`: ensures prod uses the prod workspace and prod resource names.
- `use_custom_domain`: must be true for ACM + Route53 + CloudFront alias.
- `root_domain`: the apex domain managed in Route53.
- `custom_subdomain`: subdomain that points to CloudFront (full FQDN is
  `custom_subdomain.root_domain`).

#### terraform/terraform.tfvars.local (local secrets, untracked)
```hcl
grok_api_key = "YOUR_REAL_GROK_KEY"
upstash_redis_rest_url   = "https://YOUR_UPSTASH_REDIS.upstash.io"
upstash_redis_rest_token = "YOUR_UPSTASH_TOKEN"
brave_api_key            = "YOUR_BRAVE_API_KEY"
resend_api_key           = "YOUR_RESEND_API_KEY"
```

Line by line:
- `grok_api_key`: secret API key. Required when `ai_provider = "grok"`.

### 5.6.1 Full production tfvars (complete set)
This shows a complete, explicit config that covers all variables.
Use it as a reference and remove the ones you do not need.

```hcl
project_name      = "digital-assistant"
environment       = "prod"
ai_provider       = "grok"

grok_api_url      = "https://api.x.ai/v1"
grok_model_id     = "grok-4-1-fast"

bedrock_model_id  = "amazon.nova-micro-v1:0"

lambda_timeout            = 60
lambda_memory_mb          = 512
worker_lambda_timeout     = 300
worker_lambda_memory_mb   = 2048
api_throttle_burst_limit  = 10
api_throttle_rate_limit   = 5
async_chat_enabled        = false
async_chat_enabled         = true
upstash_redis_rest_url     = "https://YOUR_UPSTASH_REDIS.upstash.io"
upstash_redis_rest_token   = "YOUR_UPSTASH_TOKEN"

use_custom_domain = true
root_domain       = "agentairg.site"
custom_subdomain  = "digital-assistant"
```

### 5.6.2 How to choose Grok vs Bedrock

- If `ai_provider = "grok"`:
  - Required: `grok_api_key`, `grok_api_url`, `grok_model_id`
  - Bedrock fields are ignored

- If `ai_provider = "bedrock"`:
  - Required: `bedrock_model_id`
  - Grok fields are ignored

### 5.6.3 Full per-environment examples (dev/test/prod)

These are explicit, complete examples for each environment. They include all
commonly used fields so you can copy-paste with minimal guessing.

#### Dev example
`terraform/dev.tfvars`
```hcl
project_name      = "digital-assistant"
environment       = "dev"
ai_provider       = "grok"

grok_api_url      = "https://api.x.ai/v1"
grok_model_id     = "grok-4-1-fast"

lambda_timeout            = 60
lambda_memory_mb          = 512
worker_lambda_timeout     = 300
worker_lambda_memory_mb   = 2048
api_throttle_burst_limit  = 10
api_throttle_rate_limit   = 5
async_chat_enabled        = false

use_custom_domain = false
root_domain       = ""
custom_subdomain  = ""
```

`terraform/terraform.tfvars.local`
```hcl
grok_api_key            = "YOUR_REAL_GROK_KEY"
brave_api_key           = "YOUR_BRAVE_API_KEY"
resend_api_key          = "YOUR_RESEND_API_KEY"
upstash_redis_rest_url  = "https://YOUR_UPSTASH_REDIS.upstash.io"
upstash_redis_rest_token = "YOUR_UPSTASH_TOKEN"
```

#### Test example
`terraform/test.tfvars`
```hcl
project_name      = "digital-assistant"
environment       = "test"
ai_provider       = "grok"

grok_api_url      = "https://api.x.ai/v1"
grok_model_id     = "grok-4-1-fast"

lambda_timeout            = 60
lambda_memory_mb          = 512
worker_lambda_timeout     = 300
worker_lambda_memory_mb   = 2048
api_throttle_burst_limit  = 10
api_throttle_rate_limit   = 5
async_chat_enabled         = true
upstash_redis_rest_url     = "https://YOUR_UPSTASH_REDIS.upstash.io"
upstash_redis_rest_token   = "YOUR_UPSTASH_TOKEN"

use_custom_domain = false
root_domain       = ""
custom_subdomain  = ""
```

`terraform/terraform.tfvars.local`
```hcl
grok_api_key             = "YOUR_REAL_GROK_KEY"
brave_api_key            = "YOUR_BRAVE_API_KEY"
resend_api_key           = "YOUR_RESEND_API_KEY"
upstash_redis_rest_url   = "https://YOUR_UPSTASH_REDIS.upstash.io"
upstash_redis_rest_token = "YOUR_UPSTASH_TOKEN"
```

#### Prod example
`terraform/prod.tfvars`
```hcl
project_name      = "digital-assistant"
environment       = "prod"
ai_provider       = "grok"

grok_api_url      = "https://api.x.ai/v1"
grok_model_id     = "grok-4-1-fast"

lambda_timeout            = 60
lambda_memory_mb          = 512
worker_lambda_timeout     = 300
worker_lambda_memory_mb   = 2048
api_throttle_burst_limit  = 10
api_throttle_rate_limit   = 5
async_chat_enabled         = true
upstash_redis_rest_url     = "https://YOUR_UPSTASH_REDIS.upstash.io"
upstash_redis_rest_token   = "YOUR_UPSTASH_TOKEN"

use_custom_domain = true
root_domain       = "agentairg.site"
custom_subdomain  = "digital-assistant"
```

`terraform/terraform.tfvars.local`
```hcl
grok_api_key             = "YOUR_REAL_GROK_KEY"
brave_api_key            = "YOUR_BRAVE_API_KEY"
resend_api_key           = "YOUR_RESEND_API_KEY"
upstash_redis_rest_url   = "https://YOUR_UPSTASH_REDIS.upstash.io"
upstash_redis_rest_token = "YOUR_UPSTASH_TOKEN"
```

### 5.6.4 Validation checklist (variable -> usage)

Use this table to verify every variable is connected to the right resource.

| Variable | Used in | Purpose |
|---|---|---|
| project_name | locals.name_prefix, Route53/ACM, outputs | Resource naming |
| environment | locals.name_prefix, tags | Environment isolation |
| ai_provider | Lambda env vars | Select Grok vs Bedrock |
| grok_api_url | Lambda env vars | Grok API base |
| grok_model_id | Lambda env vars | Grok model selection |
| grok_api_key | Lambda env vars | Grok auth |
| bedrock_model_id | Lambda env vars | Bedrock model selection |
| default_aws_region | Lambda env vars | Region for runtime AWS clients |
| enable_mcp_search | Lambda env vars | Toggle MCP web search |
| brave_api_key | Lambda env vars | Brave Search auth |
| resend_api_key | Lambda env vars | Resend email auth |
| lambda_timeout | aws_lambda_function.api | Lambda timeout |
| lambda_memory_mb | aws_lambda_function.api | Lambda memory (API) |
| worker_lambda_timeout | aws_lambda_function.worker | Worker timeout |
| worker_lambda_memory_mb | aws_lambda_function.worker | Worker memory |
| worker_max_seconds | worker env vars | Max worker job duration |
| worker_llm_timeout_seconds | worker env vars | LLM timeout (worker) |
| worker_mcp_startup_timeout_seconds | worker env vars | MCP startup timeout |
| worker_runner_timeout_seconds | worker env vars | Overall worker run timeout |
| async_chat_enabled | Lambda env vars | Enable async job flow |
| async_job_ttl_seconds | Lambda env vars | Async job TTL in Redis |
| upstash_redis_rest_url | Lambda env vars | Upstash Redis endpoint |
| upstash_redis_rest_token | Lambda env vars | Upstash Redis auth |
| lambda_image_tag | deploy.sh + ECR | Image tag deployed to Lambda |
| api_throttle_burst_limit | aws_api_gateway_method_settings.main | API Gateway throttling |
| api_throttle_rate_limit | aws_api_gateway_method_settings.main | API Gateway throttling |
| use_custom_domain | CloudFront + ACM + Route53 | Enable custom domain |
| root_domain | ACM + Route53 | Domain zone lookup |
| custom_subdomain | Route53 alias / ACM | Full domain name |

### 5.6.5 Dev vs Prod diff (what changes and why)

This section shows exactly what changes between dev and prod and how that
impacts resource names and DNS.

#### Variable diff (conceptual)
```
dev:
  environment = "dev"
  use_custom_domain = false
  root_domain = ""
  custom_subdomain = ""

prod:
  environment = "prod"
  use_custom_domain = true
  root_domain = "agentairg.site"
  custom_subdomain = "digital-assistant"
```

#### Resource name diff (examples)
```
dev:
  s3_frontend_bucket = digital-assistant-dev-frontend-<ACCOUNT_ID>
  s3_memory_bucket   = digital-assistant-dev-memory-<ACCOUNT_ID>
  lambda_function    = digital-assistant-dev-api
  api_gateway        = digital-assistant-dev-api-gateway

prod:
  s3_frontend_bucket = digital-assistant-prod-frontend-<ACCOUNT_ID>
  s3_memory_bucket   = digital-assistant-prod-memory-<ACCOUNT_ID>
  lambda_function    = digital-assistant-prod-api
  api_gateway        = digital-assistant-prod-api-gateway
```

#### DNS diff (only prod with custom domain)
```
dev:
  No Route53 records created
  CloudFront URL used directly

prod:
  ACM certificate in us-east-1
  Route53 validation CNAME
  Route53 A/AAAA alias to CloudFront
  Custom domain: https://digital-assistant.agentairg.site
```

### 5.6.6 Impact of `use_custom_domain` (what changes)

When `use_custom_domain = false`:
- No ACM certificate is requested.
- No Route53 records are created.
- CloudFront uses the default certificate.
- The frontend URL is the CloudFront domain.

When `use_custom_domain = true`:
- ACM certificate is requested in us-east-1.
- DNS validation CNAME is created in Route53.
- CloudFront uses the ACM certificate (custom SSL).
- Route53 A/AAAA alias records are created.
- The frontend URL becomes `https://<custom_subdomain>.<root_domain>`.

### 5.6.7 Propagation timeline (what to wait for)

These steps are normal and can take time:

1) ACM certificate request (us-east-1)
   - Usually 1 to 10 minutes, but can take longer.
2) DNS validation propagation
   - Route53 updates are quick, public DNS can take 5 to 30 minutes.
3) CloudFront deployment
   - 5 to 20 minutes, sometimes longer.

If CloudFront fails with `InvalidViewerCertificate`, the cert is not issued
yet. Wait and re-apply.

### 5.6.8 Ready checks (commands to verify each stage)

Use these commands to confirm every step is complete.

#### Check Route53 records (A/AAAA and validation)
```bash
dig A digital-assistant.agentairg.site +short
dig AAAA digital-assistant.agentairg.site +short
```

Windows PowerShell equivalent:
```powershell
nslookup -type=A digital-assistant.agentairg.site
nslookup -type=AAAA digital-assistant.agentairg.site
```

#### Check ACM certificate status
```bash
aws acm describe-certificate \
  --certificate-arn <ACM_CERT_ARN> \
  --region us-east-1 \
  --query "Certificate.Status"
```

Expected status: `ISSUED`.

Windows PowerShell equivalent:
```powershell
aws acm describe-certificate `
  --certificate-arn <ACM_CERT_ARN> `
  --region us-east-1 `
  --query "Certificate.Status"
```

#### Check CloudFront distribution status
```bash
aws cloudfront get-distribution \
  --id <DISTRIBUTION_ID> \
  --query "Distribution.Status"
```

Expected status: `Deployed`.

Windows PowerShell equivalent:
```powershell
aws cloudfront get-distribution `
  --id <DISTRIBUTION_ID> `
  --query "Distribution.Status"
```

#### Check HTTP response through custom domain
```bash
curl -I https://digital-assistant.agentairg.site
```

You should see `HTTP/2 200` and `x-cache: Hit from cloudfront`.

Windows PowerShell equivalent:
```powershell
Invoke-WebRequest -Method Head -Uri https://digital-assistant.agentairg.site
```
### 5.7 Decision table: which file do I edit?

| Change you want | File to edit | Why |
|---|---|---|
| Change the base project name | `terraform/terraform.tfvars` | Used in all envs |
| Change AI provider or model | `terraform/terraform.tfvars` | Shared across envs unless overridden |
| Add a custom domain for prod | `terraform/prod.tfvars` | Prod only behavior |
| Add/rotate Grok API key | `terraform/terraform.tfvars.local` | Secrets must not be committed |
| Add a new variable | `terraform/variables.tf` + `terraform/terraform.tfvars` | Declare then set |
| Change infra layout | `terraform/main.tf` | Actual resources live here |

### 5.8 Troubleshooting by file (what to fix and where)

- Error: `Missing required argument` for a variable
  - Fix: ensure the variable is set in `terraform.tfvars` or `prod.tfvars`.

- Error: `terraform.tfvars.local does not exist`
  - Fix: create it and add `grok_api_key`, or remove it from the command.

- Error: `BucketAlreadyOwnedByYou`
  - Fix: backend state mismatch. Reinit backend in `terraform/backend.tf` via
    `terraform init -reconfigure` and make sure you selected the correct
    workspace.

- Error: `AccessDenied` for ACM/Route53/DynamoDB/etc
  - Fix: IAM permissions. This is not a file issue; update your AWS identity.

- Error: `InvalidViewerCertificate` in CloudFront
  - Fix: ACM cert in us-east-1 not issued. Check `use_custom_domain` and
    `root_domain` in `prod.tfvars`, ensure Route53 validation exists.

-------------------------------------------------------------------------------

## 6) Prerequisites (tools and access)

### 6.1 Tools required
- Terraform (CLI)
- AWS CLI
- Node.js + npm (frontend build)
- Python 3.12 + uv (backend packaging)

Verify versions:
```bash
terraform --version
aws --version
node --version
npm --version
uv --version
python --version
```

### 6.2 AWS access required
Your AWS identity must be allowed to manage:
- Lambda
- API Gateway
- S3
- CloudFront
- IAM
- ACM (us-east-1)
- Route53 (if custom domain)
- DynamoDB (for Terraform locks)

If you see AccessDenied errors, your IAM user or role is missing permissions.

-------------------------------------------------------------------------------

## 7) Configuration inputs (variables)

Terraform variables are defined in `terraform/variables.tf`.
You typically set them via `.tfvars` files or TF_VAR_ env vars.

### 7.1 Required and commonly used variables

| Variable | Purpose | Example |
|---------|---------|---------|
| project_name | base name used in resource naming | "digital-assistant" |
| environment | dev/test/prod | "dev" |
| ai_provider | which model backend to use | "grok" |
| grok_api_key | API key for Grok | "<secret>" |
| grok_api_url | Grok endpoint base URL | "https://api.x.ai/v1" |
| grok_model_id | Grok model id | "grok-4-1-fast" |
| use_custom_domain | whether to use Route53 + ACM | true/false |
| root_domain | root domain for custom domain | "agentairg.site" |
| custom_subdomain | subdomain for app | "digital-assistant" |

Note:
- `grok_api_key` must be in `terraform.tfvars.local` or TF_VAR_ env var.
- `use_custom_domain` controls ACM + Route53 + CloudFront alias.

### 7.2 Local secrets file (do not commit)
Create `terraform/terraform.tfvars.local` with secrets:
```hcl
grok_api_key = "YOUR_GROK_KEY"
```

This file is intentionally untracked.

-------------------------------------------------------------------------------

## 8) Terraform backend (state + locking)

Terraform state is stored remotely to prevent drift and allow safe locking.
The backend is:
- S3 bucket: `${PROJECT_NAME}-terraform-state-${AWS_ACCOUNT_ID}`
- DynamoDB table: `${PROJECT_NAME}-terraform-locks`
- key: `terraform.tfstate` (workspaces prefix under `env:/`)

### 8.1 Why this matters
If the backend is wrong, Terraform may:
- try to recreate existing resources
- fail with AlreadyExists errors
- lose track of what it manages

### 8.2 Create backend (one time)
```bash
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
PROJECT_NAME=digital-assistant
REGION=ap-southeast-1

aws s3 mb "s3://${PROJECT_NAME}-terraform-state-${AWS_ACCOUNT_ID}" --region "$REGION"

aws dynamodb create-table \
  --table-name "${PROJECT_NAME}-terraform-locks" \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region "$REGION"
```

Windows PowerShell equivalent:
```powershell
$AWS_ACCOUNT_ID = (aws sts get-caller-identity --query Account --output text)
$PROJECT_NAME = "digital-assistant"
$REGION = "ap-southeast-1"

aws s3 mb "s3://$PROJECT_NAME-terraform-state-$AWS_ACCOUNT_ID" --region $REGION

aws dynamodb create-table `
  --table-name "$PROJECT_NAME-terraform-locks" `
  --attribute-definitions AttributeName=LockID,AttributeType=S `
  --key-schema AttributeName=LockID,KeyType=HASH `
  --billing-mode PAY_PER_REQUEST `
  --region $REGION
```

Verify:
```bash
aws s3 ls | grep "${PROJECT_NAME}-terraform-state"
aws dynamodb describe-table --table-name "${PROJECT_NAME}-terraform-locks" --region "$REGION"
```

### 8.3 Reconfigure backend (if you change names)
If you changed `PROJECT_NAME` or region, reinit:
```bash
terraform init -reconfigure \
  -backend-config="bucket=<bucket>" \
  -backend-config="key=terraform.tfstate" \
  -backend-config="region=<region>" \
  -backend-config="dynamodb_table=<table>" \
  -backend-config="encrypt=true"
```

-------------------------------------------------------------------------------

## 9) Environments and workspaces

This repo maps environments to Terraform workspaces:
- dev -> workspace "dev"
- test -> workspace "test"
- prod -> workspace "prod"

Each workspace has isolated state. You can deploy dev/test/prod in the same
AWS account without overwriting each other.

Check current workspace:
```bash
terraform workspace show
```

List all workspaces:
```bash
terraform workspace list
```

-------------------------------------------------------------------------------

## 10) Deployment using scripts (recommended)

The script handles:
- Lambda packaging
- Terraform init + workspace selection
- Terraform apply
- Frontend build + S3 upload
- CloudFront invalidation

### 10.1 Deploy dev
```bash
./scripts/deploy.sh dev
```

Windows PowerShell (requires Git Bash or WSL):
```powershell
bash ./scripts/deploy.sh dev
```

### 10.2 Deploy prod
```bash
./scripts/deploy.sh prod
```

Windows PowerShell (requires Git Bash or WSL):
```powershell
bash ./scripts/deploy.sh prod
```

### 10.3 Override project name
```bash
./scripts/deploy.sh dev my-project-name
```

Windows PowerShell (requires Git Bash or WSL):
```powershell
bash ./scripts/deploy.sh dev my-project-name
```

### 10.4 Environment variables used by the script
You can set these in your shell if you want explicit control:
- `APP_NAME` (maps to project_name)
- `DEFAULT_AWS_REGION`
- `TF_BACKEND_BUCKET`
- `TF_BACKEND_DDB_TABLE`

Examples:
```bash
export APP_NAME=digital-assistant
export DEFAULT_AWS_REGION=ap-southeast-1
export TF_BACKEND_BUCKET=digital-assistant-terraform-state-123456789012
export TF_BACKEND_DDB_TABLE=digital-assistant-terraform-locks
```

Windows PowerShell equivalents:
```powershell
$env:APP_NAME = "digital-assistant"
$env:DEFAULT_AWS_REGION = "ap-southeast-1"
$env:TF_BACKEND_BUCKET = "digital-assistant-terraform-state-123456789012"
$env:TF_BACKEND_DDB_TABLE = "digital-assistant-terraform-locks"
```

-------------------------------------------------------------------------------

## 11) Manual Terraform steps (if you want full control)

If you prefer manual steps instead of the script:

### 11.1 Init backend
```bash
cd terraform
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=ap-southeast-1
PROJECT_NAME=digital-assistant

terraform init -reconfigure \
  -backend-config="bucket=${PROJECT_NAME}-terraform-state-${AWS_ACCOUNT_ID}" \
  -backend-config="key=terraform.tfstate" \
  -backend-config="region=${REGION}" \
  -backend-config="dynamodb_table=${PROJECT_NAME}-terraform-locks" \
  -backend-config="encrypt=true"
```

Windows PowerShell equivalent:
```powershell
cd terraform
$AWS_ACCOUNT_ID = (aws sts get-caller-identity --query Account --output text)
$REGION = "ap-southeast-1"
$PROJECT_NAME = "digital-assistant"

terraform init -reconfigure `
  -backend-config="bucket=$PROJECT_NAME-terraform-state-$AWS_ACCOUNT_ID" `
  -backend-config="key=terraform.tfstate" `
  -backend-config="region=$REGION" `
  -backend-config="dynamodb_table=$PROJECT_NAME-terraform-locks" `
  -backend-config="encrypt=true"
```

### 11.2 Select workspace
```bash
terraform workspace select dev || terraform workspace new dev
```

Windows PowerShell equivalent:
```powershell
terraform workspace select dev
if ($LASTEXITCODE -ne 0) { terraform workspace new dev }
```

### 11.3 Apply with tfvars
```bash
terraform apply \
  -var-file=terraform.tfvars \
  -var-file=terraform.tfvars.local \
  -var="project_name=digital-assistant" \
  -var="environment=dev"
```

Windows PowerShell equivalent:
```powershell
terraform apply `
  -var-file=terraform.tfvars `
  -var-file=terraform.tfvars.local `
  -var="project_name=digital-assistant" `
  -var="environment=dev"
```

### 11.4 Build + upload frontend manually
```bash
cd ../frontend
npm install
npm run build
aws s3 sync ./out s3://<frontend-bucket> --delete
```

Windows PowerShell equivalent:
```powershell
cd ../frontend
npm install
npm run build
aws s3 sync ./out s3://<frontend-bucket> --delete
```

### 11.5 Invalidate CloudFront
```bash
aws cloudfront create-invalidation --distribution-id <ID> --paths "/*"
```

Windows PowerShell equivalent:
```powershell
aws cloudfront create-invalidation --distribution-id <ID> --paths "/*"
```

-------------------------------------------------------------------------------

## 12) Custom domain (optional but common)

CloudFront requires ACM certificates in us-east-1.
If you enable `use_custom_domain = true`, Terraform:
- requests an ACM certificate in us-east-1
- creates validation CNAME in Route53
- creates CloudFront distribution with your domain
- creates Route53 A/AAAA alias records

### 12.1 Requirements
- Your domain is in Route53 (hosted zone)
- You can manage DNS for that domain

### 12.2 Example config
```hcl
use_custom_domain = true
root_domain = "agentairg.site"
custom_subdomain = "digital-assistant"
```

### 12.3 DNS propagation
After apply, it can take minutes for ACM validation and DNS propagation.
CloudFront will fail if the certificate is not issued.

-------------------------------------------------------------------------------

### 12.4 UI walkthroughs (no screenshots, exact clicks and expected screens)

This section is a text substitute for screenshots. It gives exact UI paths and
what you should see at each step.

#### 12.4.1 Route53 hosted zone creation

Path:
1) AWS Console -> **Route 53**.
2) Left sidebar: **Hosted zones**.
3) Click **Create hosted zone**.

Expected screen:
- Fields: **Domain name**, **Type**.
- Type should be **Public hosted zone**.

What to enter:
- Domain name: `agentairg.site` (your root domain)
- Type: Public hosted zone

Expected result:
- A hosted zone with NS and SOA records appears.
- You will see a list of 4 NS nameservers. You must copy them to your registrar.

#### 12.4.2 Namecheap DNS update (point to Route53)

Path (Namecheap):
1) Login -> **Domain List**.
2) Find your domain -> **Manage**.
3) Go to **Nameservers**.
4) Choose **Custom DNS**.
5) Paste the 4 Route53 nameservers.

Expected result:
- Namecheap shows those 4 NS values.
- DNS propagation can take minutes to hours.

#### 12.4.3 ACM certificate request (us-east-1)

Path:
1) AWS Console -> **ACM**.
2) Top right region selector -> choose **us-east-1**.
3) Click **Request a certificate**.
4) Choose **Public certificate**.

What to enter:
- Domain name: `digital-assistant.agentairg.site`
- Validation method: **DNS**

Expected result:
- Certificate status: **Pending validation** until DNS records exist.
- A CNAME record is shown. Terraform creates it when `use_custom_domain=true`.

#### 12.4.4 CloudFront distribution check

Path:
1) AWS Console -> **CloudFront**.
2) Select your distribution.

Expected screen:
- Status: **Deployed**
- Domain name: `dxxxx.cloudfront.net`
- Alternate domain names (CNAMEs): `digital-assistant.agentairg.site`

#### 12.4.5 Route53 records (validation + alias)

Path:
1) AWS Console -> **Route 53** -> **Hosted zones**.
2) Select your zone (agentairg.site).

Expected records:
- One CNAME record for ACM validation.
- One A and one AAAA alias record for the custom domain.


## 13) Destroy (clean teardown)

The destroy script is safe and designed for real environments.
It:
- refreshes state
- skips destroy if nothing remains
- empties S3 buckets (including versioned objects)
- runs terraform destroy

### 13.1 Destroy dev
```bash
./scripts/destroy.sh dev
```

Windows PowerShell (requires Git Bash or WSL):
```powershell
bash ./scripts/destroy.sh dev
```

### 13.2 Destroy prod
```bash
./scripts/destroy.sh prod
```

Windows PowerShell (requires Git Bash or WSL):
```powershell
bash ./scripts/destroy.sh prod
```

### 13.3 Remove workspace
Only after destroy completes:
```bash
terraform workspace select default
terraform workspace delete dev
```

-------------------------------------------------------------------------------

## 14) Verification (after deploy)

### 14.1 Terraform outputs
```bash
cd terraform
terraform output
```

Expected outputs:
- api_gateway_url
- cloudfront_url
- custom_domain_url (if enabled)
- s3_frontend_bucket
- s3_memory_bucket

### 14.2 Test API
```bash
curl -s <api_gateway_url>/health
```

### 14.3 Test frontend
Open the CloudFront URL in browser.

-------------------------------------------------------------------------------

## 15) Troubleshooting (common errors and fixes)

### 15.1 AccessDenied (IAM)
Symptom:
- AccessDenied for Route53/ACM/Lambda/S3/etc
Fix:
- Attach the missing permissions to your IAM user or role.

### 15.2 BucketAlreadyOwnedByYou
Symptom:
- Terraform tries to create an S3 bucket that already exists.
Fix:
- Your state is missing or wrong. Reinit with correct backend and workspace.
- Do NOT manually create duplicate buckets with same name.

### 15.3 BucketNotEmpty on destroy
Symptom:
- Terraform cannot delete S3 bucket.
Fix:
- Use scripts/destroy.sh which empties buckets first.

### 15.4 Signature expired
Symptom:
- API calls fail with Signature expired.
Fix:
- Check system clock and NTP sync.

### 15.5 ACM certificate stuck in PENDING
Symptom:
- CloudFront fails with InvalidViewerCertificate.
Fix:
- Ensure validation CNAME exists in Route53.
- Wait for DNS propagation and rerun apply.

### 15.6 Backend configuration changed
Symptom:
- Terraform init complains about backend change.
Fix:
- Run `terraform init -reconfigure` with correct backend configs.

### 15.7 Missing variables file
Symptom:
- "terraform.tfvars.local does not exist".
Fix:
- Create it or remove it from the command.
- The scripts already handle this if the file is missing.

-------------------------------------------------------------------------------

### 15.8 Common errors by symptom (fast lookup)

| Symptom (error text) | Likely cause | Exact fix |
|---|---|---|
| `BucketAlreadyOwnedByYou` | Wrong or empty backend state | Run `terraform init -reconfigure`, select correct workspace, re-apply |
| `AccessDenied` for Route53 | Missing Route53 permissions | Attach Route53 permissions or update IAM policy |
| `AccessDenied` for ACM | Missing ACM permissions | Attach AWSCertificateManagerFullAccess |
| `InvalidViewerCertificate` | ACM cert not issued or wrong region | Ensure cert is in us-east-1 and issued; wait for DNS validation |
| `BucketNotEmpty` | S3 bucket has objects | Use `./scripts/destroy.sh <env>` to empty before destroy |
| `Signature expired` | System clock drift | Sync system time (NTP) and retry |
| `Failed to read variables file` | Missing tfvars.local | Create file or remove from apply args |
| `Provider configuration not present` | Removed provider while resources still exist | Re-add provider alias to destroy or import resources |

-------------------------------------------------------------------------------

### 15.9 Rollback / safe re-deploy

Use this if a deploy failed midway or you need a clean retry.

### 15.9.1 Safe retry (no destroy)
Use when you want Terraform to converge to desired state again.
```bash
cd terraform
terraform workspace select <env>
terraform apply -var-file=<env>.tfvars -var-file=terraform.tfvars.local
```

### 15.9.2 Refresh state only
Use when resources were manually deleted or partially removed.
```bash
cd terraform
terraform workspace select <env>
terraform apply -refresh-only -var-file=<env>.tfvars -var-file=terraform.tfvars.local
```

### 15.9.3 Full rollback (destroy + redeploy)
Use when state is inconsistent or you want a clean rebuild.
```bash
./scripts/destroy.sh <env>
./scripts/deploy.sh <env>
```

### 15.9.4 When to use each option
- Safe retry: apply failed due to timeout or transient AWS error.
- Refresh-only: resources were deleted manually or drifted.
- Full rollback: corrupted state or repeated apply failures.

-------------------------------------------------------------------------------

### 15.10 Decision tree (text-only)

Use this quick guide to choose the safest action:

1) Did the apply fail due to a timeout or temporary AWS error?
   - Yes -> Re-run `terraform apply` (safe retry).
   - No -> Continue.

2) Did you manually delete or change AWS resources outside Terraform?
   - Yes -> Run `terraform apply -refresh-only`.
   - No -> Continue.

3) Are repeated applies failing with the same error?
   - Yes -> `./scripts/destroy.sh <env>` then `./scripts/deploy.sh <env>`.
   - No -> Re-run `terraform apply`.

## 16) FAQ

Q: Can I deploy dev and prod at the same time?
A: Yes. Workspaces isolate state. Use different env names.

Q: Does Terraform overwrite my existing resources?
A: It only manages what is in state. If state is correct, it is safe.

Q: Can I run Terraform without the scripts?
A: Yes, but scripts are the recommended and tested path.

Q: Is the custom domain required?
A: No. You can use the CloudFront URL directly.

-------------------------------------------------------------------------------

## 17) Summary checklist

- [ ] AWS CLI configured
- [ ] Terraform installed
- [ ] Backend bucket and lock table created
- [ ] terraform.tfvars.local created with Grok key
- [ ] Deploy via scripts/deploy.sh <env>
- [ ] Verify outputs and endpoints
- [ ] Destroy via scripts/destroy.sh <env> when needed

-------------------------------------------------------------------------------

## 18) Deployment checklists (appendix)

### 18.1 Pre-deploy checklist
- [ ] AWS identity verified (`aws sts get-caller-identity`)
- [ ] Backend bucket and lock table exist
- [ ] Correct workspace selected (dev/test/prod)
- [ ] `terraform.tfvars.local` contains Grok key
- [ ] `use_custom_domain` and domain inputs are correct

### 18.2 Deploy checklist
- [ ] Run `./scripts/deploy.sh <env>`
- [ ] Confirm Terraform apply completes without errors
- [ ] CloudFront invalidation completes

### 18.3 Post-deploy checklist
- [ ] `terraform output` shows URLs
- [ ] API health endpoint responds 200
- [ ] Frontend loads via CloudFront or custom domain

### 18.4 Destroy checklist
- [ ] Run `./scripts/destroy.sh <env>`
- [ ] S3 buckets are emptied and deleted
- [ ] Workspace is deleted if you no longer need it

-------------------------------------------------------------------------------

## 19) PowerShell command index (all major commands)

This appendix provides PowerShell equivalents for every important command in
this guide. Use it if you prefer Windows native shells.

### 19.1 Version checks
```powershell
terraform --version
aws --version
node --version
npm --version
uv --version
python --version
```

### 19.2 Confirm AWS identity
```powershell
aws sts get-caller-identity
```

### 19.3 Backend creation (S3 + DynamoDB)
```powershell
$AWS_ACCOUNT_ID = (aws sts get-caller-identity --query Account --output text)
$PROJECT_NAME = "digital-assistant"
$REGION = "ap-southeast-1"

aws s3 mb "s3://$PROJECT_NAME-terraform-state-$AWS_ACCOUNT_ID" --region $REGION

aws dynamodb create-table `
  --table-name "$PROJECT_NAME-terraform-locks" `
  --attribute-definitions AttributeName=LockID,AttributeType=S `
  --key-schema AttributeName=LockID,KeyType=HASH `
  --billing-mode PAY_PER_REQUEST `
  --region $REGION
```

### 19.4 Backend verification
```powershell
aws s3 ls | findstr "$PROJECT_NAME-terraform-state"
aws dynamodb describe-table --table-name "$PROJECT_NAME-terraform-locks" --region $REGION
```

### 19.5 Backend reconfigure
```powershell
terraform init -reconfigure `
  -backend-config="bucket=<bucket>" `
  -backend-config="key=terraform.tfstate" `
  -backend-config="region=<region>" `
  -backend-config="dynamodb_table=<table>" `
  -backend-config="encrypt=true"
```

### 19.6 Workspace operations
```powershell
terraform workspace show
terraform workspace list

terraform workspace select dev
if ($LASTEXITCODE -ne 0) { terraform workspace new dev }
```

### 19.7 Deploy using scripts
```powershell
bash ./scripts/deploy.sh dev
bash ./scripts/deploy.sh prod
bash ./scripts/deploy.sh dev my-project-name
```

### 19.8 Environment variables for scripts
```powershell
$env:APP_NAME = "digital-assistant"
$env:DEFAULT_AWS_REGION = "ap-southeast-1"
$env:TF_BACKEND_BUCKET = "digital-assistant-terraform-state-123456789012"
$env:TF_BACKEND_DDB_TABLE = "digital-assistant-terraform-locks"
```

### 19.9 Manual Terraform apply (no script)
```powershell
cd terraform
$AWS_ACCOUNT_ID = (aws sts get-caller-identity --query Account --output text)
$REGION = "ap-southeast-1"
$PROJECT_NAME = "digital-assistant"

terraform init -reconfigure `
  -backend-config="bucket=$PROJECT_NAME-terraform-state-$AWS_ACCOUNT_ID" `
  -backend-config="key=terraform.tfstate" `
  -backend-config="region=$REGION" `
  -backend-config="dynamodb_table=$PROJECT_NAME-terraform-locks" `
  -backend-config="encrypt=true"

terraform apply `
  -var-file=terraform.tfvars `
  -var-file=terraform.tfvars.local `
  -var="project_name=digital-assistant" `
  -var="environment=dev"
```

### 19.10 Build + upload frontend manually
```powershell
cd ../frontend
npm install
npm run build
aws s3 sync ./out s3://<frontend-bucket> --delete
```

### 19.11 Invalidate CloudFront
```powershell
aws cloudfront create-invalidation --distribution-id <ID> --paths "/*"
```

### 19.12 Destroy using scripts
```powershell
bash ./scripts/destroy.sh dev
bash ./scripts/destroy.sh prod
```

### 19.13 Remove workspace
```powershell
terraform workspace select default
terraform workspace delete dev
```

### 19.14 Verify outputs
```powershell
cd terraform
terraform output
```

### 19.15 Test API
```powershell
curl -s <api_gateway_url>/health
```

### 19.16 Ready checks (DNS, ACM, CloudFront, HTTP)
```powershell
nslookup -type=A digital-assistant.agentairg.site
nslookup -type=AAAA digital-assistant.agentairg.site

aws acm describe-certificate `
  --certificate-arn <ACM_CERT_ARN> `
  --region us-east-1 `
  --query "Certificate.Status"

aws cloudfront get-distribution `
  --id <DISTRIBUTION_ID> `
  --query "Distribution.Status"

Invoke-WebRequest -Method Head -Uri https://digital-assistant.agentairg.site
```

-------------------------------------------------------------------------------

## 20) Quick reference (most common paths)

Use this if you already understand the details and just need the shortest path.

### 20.1 Deploy dev (local)
```bash
./scripts/deploy.sh dev
```

### 20.2 Deploy prod (local)
```bash
./scripts/deploy.sh prod
```

### 20.3 Destroy dev (local)
```bash
./scripts/destroy.sh dev
```

### 20.4 Destroy prod (local)
```bash
./scripts/destroy.sh prod
```

### 20.5 Refresh only (sync state)
```bash
cd terraform
terraform workspace select <env>
terraform apply -refresh-only -var-file=<env>.tfvars -var-file=terraform.tfvars.local
```

### 20.6 Reconfigure backend (if state errors)
```bash
terraform init -reconfigure \
  -backend-config="bucket=<bucket>" \
  -backend-config="key=terraform.tfstate" \
  -backend-config="region=<region>" \
  -backend-config="dynamodb_table=<table>" \
  -backend-config="encrypt=true"
```

-------------------------------------------------------------------------------

## 21) Glossary (Terraform + AWS terms used here)

**ACM**: AWS Certificate Manager, used to issue TLS certificates.  
**API Gateway**: AWS service that exposes HTTPS endpoints to Lambda.  
**Apply**: Terraform command that creates/updates/destroys resources.  
**Backend**: Where Terraform state is stored (S3 in this repo).  
**CloudFront**: AWS CDN that serves the frontend globally.  
**CNAME/A/AAAA**: DNS record types used for validation and aliases.  
**Data source**: Terraform block that reads existing AWS data.  
**DynamoDB lock**: Prevents concurrent Terraform applies.  
**HCL**: HashiCorp Configuration Language used in `.tf` files.  
**IAM**: Identity and Access Management (roles/policies).  
**Lambda**: Serverless compute for backend API.  
**Plan**: Terraform preview of changes.  
**Provider**: Plugin that lets Terraform talk to AWS.  
**Route53**: AWS DNS service, hosts your domain zone.  
**S3**: Object storage used for frontend hosting and memory.  
**State**: Terraform record of managed resources.  
**Workspace**: Separate Terraform state per environment.  

-------------------------------------------------------------------------------

## 22) Command cheat sheet (one-page)

This is a minimal list of commands for the entire flow.

### Setup
```bash
aws sts get-caller-identity
terraform --version
```

### Backend create (one time)
```bash
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
PROJECT_NAME=digital-assistant
REGION=ap-southeast-1
aws s3 mb "s3://${PROJECT_NAME}-terraform-state-${AWS_ACCOUNT_ID}" --region "$REGION"
aws dynamodb create-table \
  --table-name "${PROJECT_NAME}-terraform-locks" \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region "$REGION"
```

### Deploy dev
```bash
./scripts/deploy.sh dev
```

### Deploy prod
```bash
./scripts/deploy.sh prod
```

### Destroy dev
```bash
./scripts/destroy.sh dev
```

### Destroy prod
```bash
./scripts/destroy.sh prod
```

### Refresh-only
```bash
cd terraform
terraform workspace select <env>
terraform apply -refresh-only -var-file=<env>.tfvars -var-file=terraform.tfvars.local
```

### Windows PowerShell cheat sheet

```powershell
# Setup
aws sts get-caller-identity
terraform --version

# Backend create (one time)
$AWS_ACCOUNT_ID = (aws sts get-caller-identity --query Account --output text)
$PROJECT_NAME = "digital-assistant"
$REGION = "ap-southeast-1"
aws s3 mb "s3://$PROJECT_NAME-terraform-state-$AWS_ACCOUNT_ID" --region $REGION
aws dynamodb create-table `
  --table-name "$PROJECT_NAME-terraform-locks" `
  --attribute-definitions AttributeName=LockID,AttributeType=S `
  --key-schema AttributeName=LockID,KeyType=HASH `
  --billing-mode PAY_PER_REQUEST `
  --region $REGION

# Deploy dev
bash ./scripts/deploy.sh dev

# Deploy prod
bash ./scripts/deploy.sh prod

# Destroy dev
bash ./scripts/destroy.sh dev

# Destroy prod
bash ./scripts/destroy.sh prod

# Refresh-only
cd terraform
terraform workspace select <env>
terraform apply -refresh-only -var-file=<env>.tfvars -var-file=terraform.tfvars.local
```
