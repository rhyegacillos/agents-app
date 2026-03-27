resource "aws_secretsmanager_secret" "openai_api_key" {
  name                    = "${local.name_prefix}/app/OPENAI_API_KEY"
  recovery_window_in_days = 0
  tags                    = local.common_tags
}

resource "aws_secretsmanager_secret" "gemini_api_key" {
  name                    = "${local.name_prefix}/app/GEMINI_API_KEY"
  recovery_window_in_days = 0
  tags                    = local.common_tags
}

resource "aws_secretsmanager_secret" "deepseek_api_key" {
  name                    = "${local.name_prefix}/app/DEEPSEEK_API_KEY"
  recovery_window_in_days = 0
  tags                    = local.common_tags
}

resource "aws_secretsmanager_secret" "grok_api_key" {
  name                    = "${local.name_prefix}/app/GROK_API_KEY"
  recovery_window_in_days = 0
  tags                    = local.common_tags
}

resource "aws_secretsmanager_secret" "resend_api_key" {
  name                    = "${local.name_prefix}/app/RESEND_API_KEY"
  recovery_window_in_days = 0
  tags                    = local.common_tags
}

resource "aws_secretsmanager_secret" "clerk_secret_key" {
  name                    = "${local.name_prefix}/app/CLERK_SECRET_KEY"
  recovery_window_in_days = 0
  tags                    = local.common_tags
}

resource "aws_secretsmanager_secret" "clerk_jwks_url" {
  name                    = "${local.name_prefix}/app/CLERK_JWKS_URL"
  recovery_window_in_days = 0
  tags                    = local.common_tags
}

resource "aws_secretsmanager_secret" "brave_api_key" {
  name                    = "${local.name_prefix}/app/BRAVE_API_KEY"
  recovery_window_in_days = 0
  tags                    = local.common_tags
}

resource "aws_secretsmanager_secret" "upstash_redis_rest_url" {
  name                    = "${local.name_prefix}/app/UPSTASH_REDIS_REST_URL"
  recovery_window_in_days = 0
  tags                    = local.common_tags
}

resource "aws_secretsmanager_secret" "upstash_redis_rest_token" {
  name                    = "${local.name_prefix}/app/UPSTASH_REDIS_REST_TOKEN"
  recovery_window_in_days = 0
  tags                    = local.common_tags
}
