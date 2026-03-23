variable "project_name" {
  description = "Base name for resources."
  type        = string
  default     = "ideagen"
}

variable "environment" {
  description = "Deployment environment."
  type        = string
  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "Environment must be one of dev, test, prod."
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
  description = "Attach ECR/App Runner permissions to an existing GitHub Actions role."
  type        = bool
  default     = false
}

variable "github_actions_role_name" {
  description = "Existing GitHub Actions IAM role name."
  type        = string
  default     = ""
}

variable "vpc_cidr" {
  description = "VPC CIDR."
  type        = string
  default     = "10.60.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "Two public subnet CIDRs."
  type        = list(string)
  default     = ["10.60.0.0/24", "10.60.1.0/24"]
}

variable "private_app_subnet_cidrs" {
  description = "Two private app subnet CIDRs."
  type        = list(string)
  default     = ["10.60.10.0/24", "10.60.11.0/24"]
}

variable "private_db_subnet_cidrs" {
  description = "Two private DB subnet CIDRs."
  type        = list(string)
  default     = ["10.60.20.0/24", "10.60.21.0/24"]
}

variable "db_name" {
  description = "PostgreSQL database name."
  type        = string
  default     = "ideagen"
}

variable "db_username" {
  description = "PostgreSQL username."
  type        = string
  default     = "ideagen"
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "Allocated storage in GB."
  type        = number
  default     = 20
}

variable "db_backup_retention_period" {
  description = "Backup retention in days."
  type        = number
  default     = 7
}

variable "db_multi_az" {
  description = "Enable Multi-AZ."
  type        = bool
  default     = false
}

variable "db_skip_final_snapshot" {
  description = "Skip final snapshot on destroy."
  type        = bool
  default     = true
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
  description = "App Runner service name. Set this to reuse an existing service name."
  type        = string
  default     = ""
}

variable "existing_app_runner_service_arn" {
  description = "Existing App Runner service ARN to import and reuse instead of creating a new service."
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

variable "app_runner_custom_domain" {
  description = "Custom domain to associate with App Runner."
  type        = string
  default     = ""
}

variable "app_runner_enable_www_subdomain" {
  description = "Whether to enable the www subdomain for the App Runner custom domain."
  type        = bool
  default     = false
}

variable "allowed_hosts" {
  description = "Allowed hosts CSV for the backend."
  type        = string
  default     = ""
}

variable "next_public_clerk_publishable_key" {
  description = "Clerk publishable key for frontend/runtime."
  type        = string
}

variable "clerk_jwks_url" {
  description = "Clerk JWKS URL."
  type        = string
}

variable "gemini_api_url" {
  description = "Gemini API URL."
  type        = string
}

variable "deepseek_api_url" {
  description = "DeepSeek API URL."
  type        = string
}

variable "grok_api_url" {
  description = "Grok API URL."
  type        = string
}

variable "email_from" {
  description = "Default email sender."
  type        = string
  default     = "IdeaGen Reports <no-reply@example.com>"
}

variable "token_limit_free" {
  description = "Free plan monthly token limit."
  type        = number
  default     = 50000
}

variable "token_limit_premium" {
  description = "Premium plan monthly token limit."
  type        = number
  default     = 500000
}

variable "saved_results_limit_free_bytes" {
  description = "Free plan storage limit."
  type        = number
  default     = 104857600
}

variable "saved_results_limit_premium_bytes" {
  description = "Premium plan storage limit."
  type        = number
  default     = 1073741824
}
