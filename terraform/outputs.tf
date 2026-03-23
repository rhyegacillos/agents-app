output "ecr_repository_url" {
  description = "ECR repository for the app image."
  value       = aws_ecr_repository.app.repository_url
}

output "rds_endpoint" {
  description = "RDS endpoint hostname."
  value       = aws_db_instance.postgres.address
}

output "rds_port" {
  description = "RDS port."
  value       = aws_db_instance.postgres.port
}

output "rds_master_user_secret_arn" {
  description = "Secrets Manager ARN for the RDS-managed master credentials."
  value       = aws_db_instance.postgres.master_user_secret[0].secret_arn
}

output "app_runner_service_url" {
  description = "Public App Runner service URL."
  value       = var.app_runner_enabled ? aws_apprunner_service.app[0].service_url : ""
}

output "app_runner_service_arn" {
  description = "App Runner service ARN."
  value       = var.app_runner_enabled ? aws_apprunner_service.app[0].arn : ""
}

output "app_runner_ecr_access_role_arn" {
  description = "IAM role ARN App Runner uses to pull from ECR."
  value       = aws_iam_role.apprunner_ecr_access.arn
}

output "app_runner_instance_role_arn" {
  description = "IAM role ARN App Runner uses at runtime."
  value       = aws_iam_role.apprunner_instance.arn
}

output "app_runner_vpc_connector_arn" {
  description = "App Runner VPC connector ARN."
  value       = aws_apprunner_vpc_connector.main.arn
}

output "app_runner_autoscaling_configuration_arn" {
  description = "App Runner autoscaling configuration ARN."
  value       = aws_apprunner_auto_scaling_configuration_version.main.arn
}

output "app_runner_runtime_environment_variables" {
  description = "Non-secret runtime environment variables for App Runner."
  value = {
    APP_ENV                           = "prod"
    CLERK_JWKS_URL                    = var.clerk_jwks_url
    NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = var.next_public_clerk_publishable_key
    GEMINI_API_URL                    = var.gemini_api_url
    DEEPSEEK_API_URL                  = var.deepseek_api_url
    GROK_API_URL                      = var.grok_api_url
    EMAIL_FROM                        = var.email_from
    TOKEN_LIMIT_FREE                  = tostring(var.token_limit_free)
    TOKEN_LIMIT_PREMIUM               = tostring(var.token_limit_premium)
    SAVED_RESULTS_LIMIT_FREE_BYTES    = tostring(var.saved_results_limit_free_bytes)
    SAVED_RESULTS_LIMIT_PREMIUM_BYTES = tostring(var.saved_results_limit_premium_bytes)
    ALLOWED_HOSTS                     = var.allowed_hosts
  }
}

output "app_runtime_secret_arns" {
  description = "Secrets Manager ARNs used by App Runner."
  value = {
    DATABASE_URL_PROD = aws_secretsmanager_secret.database_url_prod.arn
    OPENAI_API_KEY    = aws_secretsmanager_secret.openai_api_key.arn
    GEMINI_API_KEY    = aws_secretsmanager_secret.gemini_api_key.arn
    DEEPSEEK_API_KEY  = aws_secretsmanager_secret.deepseek_api_key.arn
    GROK_API_KEY      = aws_secretsmanager_secret.grok_api_key.arn
    RESEND_API_KEY    = aws_secretsmanager_secret.resend_api_key.arn
  }
  sensitive = true
}

output "app_runner_custom_domain_dns_target" {
  description = "DNS target for the App Runner custom domain association."
  value       = length(aws_apprunner_custom_domain_association.app) > 0 ? aws_apprunner_custom_domain_association.app[0].dns_target : ""
}

output "app_runner_custom_domain_validation_records" {
  description = "Certificate validation records for the App Runner custom domain association."
  value       = length(aws_apprunner_custom_domain_association.app) > 0 ? aws_apprunner_custom_domain_association.app[0].certificate_validation_records : []
}

output "app_runner_custom_domain_status" {
  description = "Status of the App Runner custom domain association."
  value       = length(aws_apprunner_custom_domain_association.app) > 0 ? aws_apprunner_custom_domain_association.app[0].status : ""
}
