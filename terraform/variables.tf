variable "project_name" {
  description = "Base name for resources."
  type        = string
  default     = "medinotes"
}

variable "environment" {
  description = "Deployment environment."
  type        = string
  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "Environment must be one of dev or prod."
  }
}

variable "aws_region" {
  description = "AWS region."
  type        = string
  default     = "ap-southeast-1"
}

variable "github_repository" {
  description = "GitHub repository in owner/name format."
  type        = string
  default     = ""
}

variable "manage_github_actions_role_policies" {
  description = "Attach deploy policies to an existing GitHub Actions role."
  type        = bool
  default     = false
}

variable "github_actions_role_name" {
  description = "Existing GitHub Actions IAM role name."
  type        = string
  default     = ""
}

variable "dynamodb_table_name" {
  description = "DynamoDB table name. Defaults to <project>-<environment>-memory."
  type        = string
  default     = ""
}

variable "dynamodb_point_in_time_recovery_enabled" {
  description = "Enable DynamoDB point-in-time recovery."
  type        = bool
  default     = true
}

variable "dynamodb_doc_id_gsi_enabled" {
  description = "Whether to create the doc_id-index GSI."
  type        = bool
  default     = true
}

variable "ecr_repository_name" {
  description = "ECR repository name. Defaults to <project>-<environment>-app."
  type        = string
  default     = ""
}

variable "ecr_image_tag" {
  description = "Docker image tag used by App Runner."
  type        = string
  default     = "latest"
}

variable "app_runner_enabled" {
  description = "Create the App Runner service."
  type        = bool
  default     = true
}

variable "app_runner_service_name" {
  description = "App Runner service name. Defaults to <project>-<environment>-service."
  type        = string
  default     = ""
}

variable "app_port" {
  description = "Container port."
  type        = number
  default     = 8000
}

variable "app_runner_cpu" {
  description = "App Runner CPU."
  type        = string
  default     = "1 vCPU"
}

variable "app_runner_memory" {
  description = "App Runner memory."
  type        = string
  default     = "2 GB"
}

variable "app_runner_min_size" {
  description = "App Runner min size."
  type        = number
  default     = 1
}

variable "app_runner_max_size" {
  description = "App Runner max size."
  type        = number
  default     = 3
}

variable "app_runner_max_concurrency" {
  description = "App Runner max concurrency per instance."
  type        = number
  default     = 10
}

variable "app_runner_custom_domain" {
  description = "Custom domain to associate with App Runner."
  type        = string
  default     = ""
}

variable "app_runner_custom_domain_dns_target_override" {
  description = "Optional DNS target override for adopting an existing App Runner custom domain association."
  type        = string
  default     = ""
}

variable "app_runner_enable_www_subdomain" {
  description = "Whether to enable the www subdomain for the App Runner custom domain."
  type        = bool
  default     = false
}

variable "route53_hosted_zone_name" {
  description = "Public Route53 hosted zone name used for the App Runner custom domain."
  type        = string
  default     = ""
}

variable "next_public_clerk_publishable_key" {
  description = "Clerk publishable key for frontend/runtime."
  type        = string
  default     = ""
}

variable "next_public_clerk_jwt_template" {
  description = "Clerk JWT template used by the frontend."
  type        = string
  default     = ""
}

variable "gemini_api_url" {
  description = "Gemini API URL."
  type        = string
  default     = "https://generativelanguage.googleapis.com/v1beta/openai/"
}

variable "deepseek_api_url" {
  description = "DeepSeek API URL."
  type        = string
  default     = "https://api.deepseek.com/v1"
}

variable "grok_api_url" {
  description = "Grok API URL."
  type        = string
  default     = "https://api.x.ai/v1"
}

variable "resend_from" {
  description = "Default email sender."
  type        = string
  default     = "MediNotes <no-reply@agentairg.site>"
}

variable "health_check_path" {
  description = "App Runner health check path."
  type        = string
  default     = "/health"
}

variable "health_check_interval" {
  description = "App Runner health check interval in seconds."
  type        = number
  default     = 10
}

variable "health_check_timeout" {
  description = "App Runner health check timeout in seconds."
  type        = number
  default     = 5
}

variable "health_check_healthy_threshold" {
  description = "App Runner healthy threshold."
  type        = number
  default     = 1
}

variable "health_check_unhealthy_threshold" {
  description = "App Runner unhealthy threshold."
  type        = number
  default     = 5
}
