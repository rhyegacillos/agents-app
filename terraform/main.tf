data "aws_caller_identity" "current" {}

data "aws_route53_zone" "app_runner_custom_domain" {
  count        = trimspace(var.route53_hosted_zone_name) != "" ? 1 : 0
  name         = "${trimspace(var.route53_hosted_zone_name)}."
  private_zone = false
}

locals {
  name_prefix                         = "${var.project_name}-${var.environment}"
  app_runner_service_name             = trimspace(var.app_runner_service_name) != "" ? trimspace(var.app_runner_service_name) : "${local.name_prefix}-service"
  ecr_repository_name                 = trimspace(var.ecr_repository_name) != "" ? trimspace(var.ecr_repository_name) : "${local.name_prefix}-app"
  dynamodb_table_name                 = trimspace(var.dynamodb_table_name) != "" ? trimspace(var.dynamodb_table_name) : "${local.name_prefix}-memory"
  app_runner_custom_domain_dns_target = trimspace(var.app_runner_custom_domain_dns_target_override) != "" ? trimspace(var.app_runner_custom_domain_dns_target_override) : try(aws_apprunner_custom_domain_association.app[0].dns_target, "")
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_dynamodb_table" "memory" {
  name         = local.dynamodb_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"
  tags         = merge(local.common_tags, { Name = local.dynamodb_table_name })

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  attribute {
    name = "doc_id"
    type = "S"
  }

  dynamic "global_secondary_index" {
    for_each = var.dynamodb_doc_id_gsi_enabled ? [1] : []
    content {
      name            = "doc_id-index"
      hash_key        = "doc_id"
      projection_type = "ALL"
    }
  }

  point_in_time_recovery {
    enabled = var.dynamodb_point_in_time_recovery_enabled
  }
}

resource "aws_ecr_repository" "app" {
  name                 = local.ecr_repository_name
  force_delete         = true
  image_tag_mutability = "MUTABLE"
  tags                 = local.common_tags

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep the most recent 20 tagged images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["latest"]
          countType     = "imageCountMoreThan"
          countNumber   = 20
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Expire untagged images after 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

resource "aws_iam_role" "apprunner_ecr_access" {
  name = "${local.name_prefix}-apprunner-ecr-access"
  tags = local.common_tags

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "build.apprunner.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "apprunner_ecr_access" {
  role       = aws_iam_role.apprunner_ecr_access.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
}

resource "aws_iam_role" "apprunner_instance" {
  name = "${local.name_prefix}-apprunner-instance"
  tags = local.common_tags

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "tasks.apprunner.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "apprunner_instance_runtime" {
  name = "${local.name_prefix}-apprunner-runtime"
  role = aws_iam_role.apprunner_instance.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = [
          aws_secretsmanager_secret.openai_api_key.arn,
          aws_secretsmanager_secret.gemini_api_key.arn,
          aws_secretsmanager_secret.deepseek_api_key.arn,
          aws_secretsmanager_secret.grok_api_key.arn,
          aws_secretsmanager_secret.resend_api_key.arn,
          aws_secretsmanager_secret.clerk_secret_key.arn,
          aws_secretsmanager_secret.clerk_jwks_url.arn,
          aws_secretsmanager_secret.brave_api_key.arn,
          aws_secretsmanager_secret.upstash_redis_rest_url.arn,
          aws_secretsmanager_secret.upstash_redis_rest_token.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:BatchWriteItem",
          "dynamodb:DeleteItem",
          "dynamodb:DescribeTable",
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:UpdateItem"
        ]
        Resource = [
          aws_dynamodb_table.memory.arn,
          "${aws_dynamodb_table.memory.arn}/index/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "kms:ViaService" = "secretsmanager.${var.aws_region}.amazonaws.com"
          }
        }
      }
    ]
  })
}

resource "aws_apprunner_auto_scaling_configuration_version" "main" {
  auto_scaling_configuration_name = "${local.name_prefix}-autoscaling"
  min_size                        = var.app_runner_min_size
  max_size                        = var.app_runner_max_size
  max_concurrency                 = var.app_runner_max_concurrency
  tags                            = local.common_tags
}

resource "aws_apprunner_service" "app" {
  count        = var.app_runner_enabled ? 1 : 0
  service_name = local.app_runner_service_name
  tags         = local.common_tags

  source_configuration {
    auto_deployments_enabled = true

    authentication_configuration {
      access_role_arn = aws_iam_role.apprunner_ecr_access.arn
    }

    image_repository {
      image_repository_type = "ECR"
      image_identifier      = "${aws_ecr_repository.app.repository_url}:${var.ecr_image_tag}"

      image_configuration {
        port = tostring(var.app_port)
        runtime_environment_variables = {
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
        runtime_environment_secrets = {
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
      }
    }
  }

  instance_configuration {
    cpu               = var.app_runner_cpu
    memory            = var.app_runner_memory
    instance_role_arn = aws_iam_role.apprunner_instance.arn
  }

  network_configuration {
    ingress_configuration {
      is_publicly_accessible = true
    }

    egress_configuration {
      egress_type = "DEFAULT"
    }
  }

  observability_configuration {
    observability_enabled = false
  }

  health_check_configuration {
    protocol            = "HTTP"
    path                = var.health_check_path
    interval            = var.health_check_interval
    timeout             = var.health_check_timeout
    healthy_threshold   = var.health_check_healthy_threshold
    unhealthy_threshold = var.health_check_unhealthy_threshold
  }

  auto_scaling_configuration_arn = aws_apprunner_auto_scaling_configuration_version.main.arn

  depends_on = [
    aws_dynamodb_table.memory,
    aws_iam_role_policy_attachment.apprunner_ecr_access,
    aws_iam_role_policy.apprunner_instance_runtime,
  ]
}

resource "aws_apprunner_custom_domain_association" "app" {
  count = var.app_runner_enabled && trimspace(var.app_runner_custom_domain) != "" ? 1 : 0

  domain_name          = trimspace(var.app_runner_custom_domain)
  enable_www_subdomain = var.app_runner_enable_www_subdomain
  service_arn          = aws_apprunner_service.app[0].arn
}

resource "aws_route53_record" "app_runner_custom_domain" {
  count = var.app_runner_enabled && trimspace(var.app_runner_custom_domain) != "" && trimspace(var.route53_hosted_zone_name) != "" && local.app_runner_custom_domain_dns_target != "" ? 1 : 0

  zone_id         = data.aws_route53_zone.app_runner_custom_domain[0].zone_id
  name            = trimspace(var.app_runner_custom_domain)
  type            = "CNAME"
  ttl             = 60
  allow_overwrite = true
  records         = [local.app_runner_custom_domain_dns_target]
}
