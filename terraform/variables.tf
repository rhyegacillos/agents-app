variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "ap-southeast-1"
}

variable "project_name" {
  description = "Name prefix for resources."
  type        = string
  default     = "autonomous-trader"
}

variable "instance_type" {
  description = "EC2 instance type."
  type        = string
  default     = "t3.small"
}

variable "key_name" {
  description = "EC2 key pair name for SSH."
  type        = string
}

variable "existing_instance_id" {
  description = "Optional: existing EC2 instance ID to import and manage."
  type        = string
  default     = ""
}

variable "existing_instance_tag_name" {
  description = "Optional: tag:Name to auto-detect an existing instance."
  type        = string
  default     = "autonomous-trader-app"
}

variable "manage_existing" {
  description = "If true and an existing instance is detected, Terraform will expect import and manage it."
  type        = bool
  default     = false
}

variable "manage_existing_sg_rules" {
  description = "If true, Terraform manages HTTP/HTTPS/SSH rules on the existing instance security group."
  type        = bool
  default     = false
}

variable "existing_security_group_id" {
  description = "Optional: explicit security group ID to manage when using an existing instance."
  type        = string
  default     = ""
}

variable "allowed_ssh_cidr" {
  description = "CIDR allowed to SSH to the instance."
  type        = string
  default     = "0.0.0.0/0"
}

variable "ecr_repo" {
  description = "ECR repository name."
  type        = string
  default     = "autonomous-trader"
}

variable "image_tag" {
  description = "Image tag to deploy."
  type        = string
  default     = "latest"
}

variable "env_vars" {
  description = "Environment variables written into /home/ec2-user/autonomous-trader.env"
  type        = map(string)
  default     = {}
}

variable "enable_https" {
  description = "Enable Nginx reverse proxy + HTTPS (Certbot) on the instance."
  type        = bool
  default     = false
}

variable "domain_name" {
  description = "Domain name to secure with HTTPS (e.g., autonomous-trader.agentairg.site)."
  type        = string
  default     = ""
}

variable "certbot_email" {
  description = "Email for Let's Encrypt registration."
  type        = string
  default     = ""
}

variable "enable_route53_dns" {
  description = "Create/maintain Route53 DNS record for the app domain."
  type        = bool
  default     = false
}

variable "route53_zone_name" {
  description = "Route53 hosted zone name (e.g., agentairg.site)."
  type        = string
  default     = ""
}

variable "route53_zone_id" {
  description = "Optional: Route53 hosted zone ID (takes precedence over zone name)."
  type        = string
  default     = ""
}

variable "deploy_ssh_key" {
  description = "Optional: local path to SSH private key for deploy script automation."
  type        = string
  default     = ""
}

variable "deploy_ssh_user" {
  description = "Optional: SSH username for deploy script automation."
  type        = string
  default     = "ec2-user"
}
