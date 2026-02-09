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

output "custom_domain_url" {
  description = "Root URL of the production site"
  value       = var.use_custom_domain ? "https://${var.project_name}.${var.root_domain}" : ""
}

output "ecr_repository_url" {
  description = "ECR repository URL for the Lambda image"
  value       = aws_ecr_repository.lambda.repository_url
}
