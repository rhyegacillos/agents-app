resource "aws_secretsmanager_secret" "database_url_prod" {
  name = "${local.name_prefix}/app/DATABASE_URL_PROD"
  tags = local.common_tags
}

resource "aws_secretsmanager_secret" "openai_api_key" {
  name = "${local.name_prefix}/app/OPENAI_API_KEY"
  tags = local.common_tags
}

resource "aws_secretsmanager_secret" "gemini_api_key" {
  name = "${local.name_prefix}/app/GEMINI_API_KEY"
  tags = local.common_tags
}

resource "aws_secretsmanager_secret" "deepseek_api_key" {
  name = "${local.name_prefix}/app/DEEPSEEK_API_KEY"
  tags = local.common_tags
}

resource "aws_secretsmanager_secret" "grok_api_key" {
  name = "${local.name_prefix}/app/GROK_API_KEY"
  tags = local.common_tags
}

resource "aws_secretsmanager_secret" "resend_api_key" {
  name = "${local.name_prefix}/app/RESEND_API_KEY"
  tags = local.common_tags
}
