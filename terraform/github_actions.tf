# Optional: attach permissions to an existing GitHub Actions OIDC role.
#
# Why this exists:
# - Terraform in CI needs ECR permissions to refresh/create/push the Lambda image repo.
# - The role is typically created out-of-band (docs), but we can manage the policy attachment
#   from Terraform when you run `terraform apply` locally with admin IAM permissions.

resource "aws_iam_role_policy_attachment" "github_actions_ecr_poweruser" {
  count = var.manage_github_actions_role_policies && var.github_actions_role_name != "" ? 1 : 0

  role       = var.github_actions_role_name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser"
}

