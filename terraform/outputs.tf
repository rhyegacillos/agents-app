output "public_ip" {
  value       = local.use_existing ? data.aws_instance.existing[0].public_ip : aws_instance.app[0].public_ip
  description = "Public IP for the EC2 instance."
}

output "public_dns" {
  value       = local.use_existing ? data.aws_instance.existing[0].public_dns : aws_instance.app[0].public_dns
  description = "Public DNS for the EC2 instance."
}

output "app_url" {
  value       = "http://${local.use_existing ? data.aws_instance.existing[0].public_dns : aws_instance.app[0].public_dns}"
  description = "HTTP URL for the app."
}

output "image_uri" {
  value       = local.image_uri
  description = "ECR image URI used by the deployment."
}

output "env_file_content" {
  value       = local.env_file_content
  description = "Rendered env file content for the container."
  sensitive   = true
}
