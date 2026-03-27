output "ecr_repository_url" {
  description = "ECR repository for the app image."
  value       = aws_ecr_repository.app.repository_url
}

output "dynamodb_table_name" {
  description = "DynamoDB table name."
  value       = aws_dynamodb_table.memory.name
}

output "dynamodb_table_arn" {
  description = "DynamoDB table ARN."
  value       = aws_dynamodb_table.memory.arn
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

output "app_runner_runtime_environment_variables" {
  description = "Non-secret runtime environment variables for App Runner."
  value = {
    NODE_ENV                          = "production"
    AWS_REGION                        = var.aws_region
    DYNAMODB_TABLE_NAME               = aws_dynamodb_table.memory.name
    GEMINI_API_URL                    = var.gemini_api_url
    DEEPSEEK_API_URL                  = var.deepseek_api_url
    GROK_API_URL                      = var.grok_api_url
    NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = var.next_public_clerk_publishable_key
    NEXT_PUBLIC_CLERK_JWT_TEMPLATE    = var.next_public_clerk_jwt_template
    RESEND_FROM                       = var.resend_from
  }
}

output "app_runtime_secret_arns" {
  description = "Secrets Manager ARNs used by App Runner."
  value = {
    OPENAI_API_KEY           = aws_secretsmanager_secret.openai_api_key.arn
    GEMINI_API_KEY           = aws_secretsmanager_secret.gemini_api_key.arn
    DEEPSEEK_API_KEY         = aws_secretsmanager_secret.deepseek_api_key.arn
    GROK_API_KEY             = aws_secretsmanager_secret.grok_api_key.arn
    RESEND_API_KEY           = aws_secretsmanager_secret.resend_api_key.arn
    CLERK_SECRET_KEY         = aws_secretsmanager_secret.clerk_secret_key.arn
    CLERK_JWKS_URL           = aws_secretsmanager_secret.clerk_jwks_url.arn
    BRAVE_API_KEY            = aws_secretsmanager_secret.brave_api_key.arn
    UPSTASH_REDIS_REST_URL   = aws_secretsmanager_secret.upstash_redis_rest_url.arn
    UPSTASH_REDIS_REST_TOKEN = aws_secretsmanager_secret.upstash_redis_rest_token.arn
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
