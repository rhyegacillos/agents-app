# Data source to get current AWS account ID
data "aws_caller_identity" "current" {}

locals {
  aliases = var.use_custom_domain && var.root_domain != "" ? [
    "${var.project_name}.${var.root_domain}"
  ] : []

  name_prefix = "${var.project_name}-${var.environment}"

  custom_domain_fqdn     = "${var.project_name}.${var.root_domain}"
  api_cors_origin        = var.use_custom_domain && var.root_domain != "" ? "https://${local.custom_domain_fqdn}" : "https://${aws_cloudfront_distribution.main.domain_name}"
  create_www_alias       = false
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

locals {
  memory_cors_allowed_origins = distinct(compact([
    "https://${aws_cloudfront_distribution.main.domain_name}",
    var.use_custom_domain && var.root_domain != "" ? "https://${local.custom_domain_fqdn}" : null,
  ]))
}

resource "aws_s3_bucket_cors_configuration" "memory" {
  bucket = aws_s3_bucket.memory.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT", "POST", "HEAD"]
    allowed_origins = local.memory_cors_allowed_origins
    expose_headers  = ["ETag", "x-amz-request-id", "x-amz-id-2"]
    max_age_seconds = 3000
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

# Allow Lambda service to pull images from this repository
resource "aws_ecr_repository_policy" "lambda" {
  repository = aws_ecr_repository.lambda.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "LambdaECRImageRetrievalPolicy"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
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

# Cleanup untagged images to avoid ECR bloat when reusing a stable tag
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
        action = {
          type = "expire"
        }
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
      CORS_ORIGINS                = var.use_custom_domain ? "https://${local.custom_domain_fqdn}" : "https://${aws_cloudfront_distribution.main.domain_name}"
      S3_BUCKET                   = aws_s3_bucket.memory.id
      USE_S3                      = "true"
      DEFAULT_AWS_REGION          = var.default_aws_region
      ENABLE_MCP_SEARCH           = var.enable_mcp_search ? "true" : "false"
      BEDROCK_MODEL_ID            = var.bedrock_model_id
      AI_PROVIDER                 = var.ai_provider
      GROK_MODEL_ID               = var.grok_model_id
      GROK_API_URL                = var.grok_api_url
      GROK_API_KEY                = var.grok_api_key
      BRAVE_API_KEY               = var.brave_api_key
      RESEND_API_KEY              = var.resend_api_key
      UPSTASH_REDIS_REST_URL      = var.upstash_redis_rest_url
      UPSTASH_REDIS_REST_TOKEN    = var.upstash_redis_rest_token
      ASYNC_CHAT_ENABLED          = var.async_chat_enabled ? "true" : "false"
      ASYNC_JOB_TTL_SECONDS       = tostring(var.async_job_ttl_seconds)
      DAILY_TOKEN_LIMIT           = tostring(var.daily_token_limit)
      SENTRY_DSN                  = var.sentry_dsn
      SENTRY_ENVIRONMENT          = var.environment
      SENTRY_SERVICE              = "${local.name_prefix}-api"
      SENTRY_RELEASE              = var.lambda_image_tag
      SENTRY_TRACES_SAMPLE_RATE   = tostring(var.sentry_traces_sample_rate)
      SENTRY_PROFILES_SAMPLE_RATE = tostring(var.sentry_profiles_sample_rate)
      ASYNC_WORKER_FUNCTION_NAME  = aws_lambda_function.worker.function_name
      MEMORY_EXTRACT_SYNC         = "false"
      UPLOADS_DIR                 = var.uploads_dir
      MAX_UPLOAD_MB               = tostring(var.max_upload_mb)
      UPLOAD_ALLOWED_EXTS         = var.upload_allowed_exts
    }
  }

  # Ensure Lambda waits for the distribution to exist
  depends_on = [aws_cloudfront_distribution.main]
}

# Async worker Lambda (same image, different handler)
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
      CORS_ORIGINS                = var.use_custom_domain ? "https://${local.custom_domain_fqdn}" : "https://${aws_cloudfront_distribution.main.domain_name}"
      S3_BUCKET                   = aws_s3_bucket.memory.id
      USE_S3                      = "true"
      DEFAULT_AWS_REGION          = var.default_aws_region
      ENABLE_MCP_SEARCH           = var.enable_mcp_search ? "true" : "false"
      BEDROCK_MODEL_ID            = var.bedrock_model_id
      AI_PROVIDER                 = var.ai_provider
      GROK_MODEL_ID               = var.grok_model_id
      GROK_API_URL                = var.grok_api_url
      GROK_API_KEY                = var.grok_api_key
      BRAVE_API_KEY               = var.brave_api_key
      RESEND_API_KEY              = var.resend_api_key
      UPSTASH_REDIS_REST_URL      = var.upstash_redis_rest_url
      UPSTASH_REDIS_REST_TOKEN    = var.upstash_redis_rest_token
      ASYNC_CHAT_ENABLED          = "false"
      ASYNC_JOB_TTL_SECONDS       = tostring(var.async_job_ttl_seconds)
      DAILY_TOKEN_LIMIT           = tostring(var.daily_token_limit)
      SENTRY_DSN                  = var.sentry_dsn
      SENTRY_ENVIRONMENT          = var.environment
      SENTRY_SERVICE              = "${local.name_prefix}-worker"
      SENTRY_RELEASE              = var.lambda_image_tag
      SENTRY_TRACES_SAMPLE_RATE   = tostring(var.sentry_traces_sample_rate)
      SENTRY_PROFILES_SAMPLE_RATE = tostring(var.sentry_profiles_sample_rate)
      WORKER_MAX_SECONDS          = tostring(var.worker_max_seconds)
      LLM_TIMEOUT_SECONDS         = tostring(var.worker_llm_timeout_seconds)
      MCP_STARTUP_TIMEOUT_SECONDS = tostring(var.worker_mcp_startup_timeout_seconds)
      RUNNER_TIMEOUT_SECONDS      = tostring(var.worker_runner_timeout_seconds)
      MEMORY_EXTRACT_SYNC         = "true"
      UPLOADS_DIR                 = var.uploads_dir
      MAX_UPLOAD_MB               = tostring(var.max_upload_mb)
      UPLOAD_ALLOWED_EXTS         = var.upload_allowed_exts
    }
  }

  depends_on = [aws_cloudfront_distribution.main]
}

resource "aws_iam_role_policy" "lambda_invoke_worker" {
  name = "${local.name_prefix}-invoke-worker"
  role = aws_iam_role.lambda_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = [
          aws_lambda_function.worker.arn,
          "${aws_lambda_function.worker.arn}:*"
        ]
      }
    ]
  })
}

# API Gateway REST API
data "aws_region" "current" {}

resource "aws_api_gateway_rest_api" "main" {
  name = "${local.name_prefix}-api-gateway"
  tags = local.common_tags
}

# Root ANY method -> Lambda proxy
resource "aws_api_gateway_method" "root_any" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_rest_api.main.root_resource_id
  http_method   = "ANY"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "root_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_rest_api.main.root_resource_id
  http_method             = aws_api_gateway_method.root_any.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  timeout_milliseconds    = var.api_integration_timeout_ms
  uri                     = aws_lambda_function.api.invoke_arn
}

# Proxy resource to handle all paths
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
  timeout_milliseconds    = var.api_integration_timeout_ms
  uri                     = aws_lambda_function.api.invoke_arn
}

resource "aws_api_gateway_deployment" "main" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  triggers = {
    redeploy = sha1(jsonencode([
      aws_api_gateway_integration.root_lambda.id,
      aws_api_gateway_integration.proxy_lambda.id,
      aws_api_gateway_integration.root_options.id,
      aws_api_gateway_integration.proxy_options.id,
    ]))
  }
  lifecycle {
    create_before_destroy = true
  }
  depends_on = [
    aws_api_gateway_integration.root_lambda,
    aws_api_gateway_integration.proxy_lambda,
  ]
}

resource "aws_api_gateway_stage" "main" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  deployment_id = aws_api_gateway_deployment.main.id
  stage_name    = var.environment
  tags          = local.common_tags
}

resource "aws_api_gateway_method_settings" "main" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  stage_name  = aws_api_gateway_stage.main.stage_name
  method_path = "*/*"

  settings {
    metrics_enabled        = true
    throttling_burst_limit = var.api_throttle_burst_limit
    throttling_rate_limit  = var.api_throttle_rate_limit
  }
}

# Lambda permission for API Gateway
resource "aws_lambda_permission" "api_gw" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

# CORS: OPTIONS for root
resource "aws_api_gateway_method" "root_options" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_rest_api.main.root_resource_id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "root_options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_rest_api.main.root_resource_id
  http_method = aws_api_gateway_method.root_options.http_method
  type        = "MOCK"
  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "root_options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_rest_api.main.root_resource_id
  http_method = aws_api_gateway_method.root_options.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Origin"  = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Headers" = true
  }
}

resource "aws_api_gateway_integration_response" "root_options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_rest_api.main.root_resource_id
  http_method = aws_api_gateway_method.root_options.http_method
  status_code = aws_api_gateway_method_response.root_options.status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Origin"  = "'${local.api_cors_origin}'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,POST,OPTIONS'"
    "method.response.header.Access-Control-Allow-Headers" = "'*'"
  }
}

# CORS: OPTIONS for proxy
resource "aws_api_gateway_method" "proxy_options" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.proxy.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "proxy_options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.proxy.id
  http_method = aws_api_gateway_method.proxy_options.http_method
  type        = "MOCK"
  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "proxy_options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.proxy.id
  http_method = aws_api_gateway_method.proxy_options.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Origin"  = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Headers" = true
  }
}

resource "aws_api_gateway_integration_response" "proxy_options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.proxy.id
  http_method = aws_api_gateway_method.proxy_options.http_method
  status_code = aws_api_gateway_method_response.proxy_options.status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Origin"  = "'${local.api_cors_origin}'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,POST,OPTIONS'"
    "method.response.header.Access-Control-Allow-Headers" = "'*'"
  }
}

# CloudFront distribution
resource "aws_cloudfront_distribution" "main" {
  aliases             = local.aliases
  wait_for_deployment = false
  depends_on = [
    aws_acm_certificate_validation.site,
    aws_s3_bucket_website_configuration.frontend,
    aws_s3_bucket_policy.frontend
  ]

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
