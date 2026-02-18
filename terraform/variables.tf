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
  default     = "amazon.nova-lite-v1:0"
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
  sensitive   = true
}

variable "brave_api_key" {
  description = "Brave Search API Key"
  type        = string
  sensitive   = true
}

variable "resend_api_key" {
  description = "Resend API Key"
  type        = string
  sensitive   = true
}

variable "ai_provider" {
  description = "AI Provider"
  type        = string
  default     = "grok"
}

variable "default_aws_region" {
  description = "Default AWS region for runtime clients"
  type        = string
  default     = "ap-southeast-1"
}

variable "enable_mcp_search" {
  description = "Enable MCP web search tools"
  type        = bool
  default     = true
}

variable "uploads_dir" {
  description = "Uploads directory in Lambda"
  type        = string
  default     = "/tmp/uploads"
}

variable "max_upload_mb" {
  description = "Max upload size in MB"
  type        = number
  default     = 50
}

variable "upload_allowed_exts" {
  description = "Allowed upload extensions (comma-separated)"
  type        = string
  default     = "pdf,docx,txt,md"
}

variable "lambda_timeout" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 60
}

variable "lambda_memory_mb" {
  description = "Memory size for API Lambda (MB)"
  type        = number
  default     = 512
}

variable "worker_lambda_timeout" {
  description = "Async worker Lambda timeout in seconds"
  type        = number
  default     = 300
}

variable "worker_lambda_memory_mb" {
  description = "Memory size for worker Lambda (MB)"
  type        = number
  default     = 2048
}

variable "worker_max_seconds" {
  description = "Max seconds the worker will spend on a job before marking it failed"
  type        = number
  default     = 240
}

variable "worker_llm_timeout_seconds" {
  description = "Timeout for LLM requests in worker (seconds)"
  type        = number
  default     = 120
}

variable "worker_mcp_startup_timeout_seconds" {
  description = "Timeout for MCP server startup in worker (seconds)"
  type        = number
  default     = 120
}

variable "worker_runner_timeout_seconds" {
  description = "Timeout for overall agent run in worker (seconds)"
  type        = number
  default     = 220
}


variable "lambda_image_tag" {
  description = "Container image tag for the Lambda function"
  type        = string
  default     = "latest"
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

variable "api_integration_timeout_ms" {
  description = "API Gateway REST API integration timeout in milliseconds (subject to quota)"
  type        = number
  default     = 29000
}

variable "async_chat_enabled" {
  description = "Enable async chat workflow (queue + worker)"
  type        = bool
  default     = false
}

variable "async_job_ttl_seconds" {
  description = "TTL for async job status in Redis"
  type        = number
  default     = 3600
}

variable "daily_token_limit" {
  description = "Daily token quota limit per user"
  type        = number
  default     = 100000
}

variable "app_timezone" {
  description = "Default application timezone (IANA, for example Asia/Manila)"
  type        = string
  default     = "Asia/Manila"
}

variable "otel_enabled" {
  description = "Enable OpenTelemetry tracing"
  type        = bool
  default     = false
}

variable "otel_exporter_otlp_endpoint" {
  description = "OTLP HTTP traces endpoint (for example: https://.../v1/traces)"
  type        = string
  default     = ""
}

variable "otel_exporter_otlp_headers" {
  description = "OTLP HTTP headers as comma-separated key=value pairs"
  type        = string
  default     = ""
  sensitive   = true
}

variable "otel_traces_sample_rate" {
  description = "OpenTelemetry traces sample rate (0.0-1.0)"
  type        = number
  default     = 0.1
}

variable "otel_logs_enabled" {
  description = "Enable OpenTelemetry logs export"
  type        = bool
  default     = false
}

variable "otel_exporter_otlp_logs_endpoint" {
  description = "OTLP HTTP logs endpoint (optional; derived from traces endpoint when empty)"
  type        = string
  default     = ""
}

variable "otel_exporter_otlp_logs_headers" {
  description = "OTLP HTTP logs headers as comma-separated key=value pairs (optional)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "otel_logs_min_level" {
  description = "Minimum stdlib log level exported to OTLP (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
  type        = string
  default     = "INFO"
}

variable "upstash_redis_rest_url" {
  description = "Upstash Redis REST URL"
  type        = string
  default     = ""
}

variable "upstash_redis_rest_token" {
  description = "Upstash Redis REST token"
  type        = string
  default     = ""
  sensitive   = true
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

variable "manage_github_actions_role_policies" {
  description = "If true, Terraform will attach required AWS managed policies to an existing GitHub Actions role."
  type        = bool
  default     = false
}

variable "github_actions_role_name" {
  description = "Name of the GitHub Actions IAM role to attach policies to (e.g. github-actions-digital-assistant-deploy)."
  type        = string
  default     = ""
}
