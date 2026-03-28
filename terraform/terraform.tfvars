project_name                       = "digital-assistant"
environment                        = "dev"
bedrock_model_id                   = "arn:aws:bedrock:ap-southeast-1:348375262167:inference-profile/apac.amazon.nova-lite-v1:0"
grok_model_id                      = "grok-4-1-fast"
grok_api_url                       = "https://api.x.ai/v1"
ai_provider                        = "bedrock"
default_aws_region                 = "ap-southeast-1"
enable_mcp_search                  = true
uploads_dir                        = "/tmp/uploads"
max_upload_mb                      = 50
upload_allowed_exts                = "pdf,docx,txt,md"
lambda_timeout                     = 60
worker_lambda_timeout              = 300
worker_max_seconds                 = 240
worker_llm_timeout_seconds         = 120
worker_mcp_startup_timeout_seconds = 120
worker_runner_timeout_seconds      = 220
lambda_memory_mb                   = 512
worker_lambda_memory_mb            = 2048
lambda_image_tag                   = "dev-latest"
api_throttle_burst_limit           = 10
api_throttle_rate_limit            = 5
use_custom_domain                  = false
root_domain                        = ""
async_chat_enabled                 = true
async_job_ttl_seconds              = 3600
daily_token_limit                  = 1000000
otel_enabled                       = true
otel_exporter_otlp_endpoint        = "https://o4510895849472000.ingest.us.sentry.io/api/4510896623845376/integration/otlp/v1/traces"
otel_exporter_otlp_headers         = "x-sentry-auth=sentry sentry_key=ee8a81b082a6c0a7d11084072379db13"
otel_traces_sample_rate            = 1.0
otel_logs_enabled                  = true
otel_exporter_otlp_logs_endpoint   = "https://o4510895849472000.ingest.us.sentry.io/api/4510896623845376/integration/otlp/v1/logs"
otel_exporter_otlp_logs_headers    = "x-sentry-auth=sentry sentry_key=ee8a81b082a6c0a7d11084072379db13"
otel_logs_min_level                = "INFO"

