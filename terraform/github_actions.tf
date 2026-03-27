resource "aws_iam_role_policy_attachment" "github_actions_ecr_poweruser" {
  count = var.manage_github_actions_role_policies && var.github_actions_role_name != "" ? 1 : 0

  role       = var.github_actions_role_name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser"
}

resource "aws_iam_role_policy_attachment" "github_actions_apprunner_fullaccess" {
  count = var.manage_github_actions_role_policies && var.github_actions_role_name != "" ? 1 : 0

  role       = var.github_actions_role_name
  policy_arn = "arn:aws:iam::aws:policy/AWSAppRunnerFullAccess"
}

resource "aws_iam_role_policy_attachment" "github_actions_secretsmanager_readwrite" {
  count = var.manage_github_actions_role_policies && var.github_actions_role_name != "" ? 1 : 0

  role       = var.github_actions_role_name
  policy_arn = "arn:aws:iam::aws:policy/SecretsManagerReadWrite"
}

resource "aws_iam_role_policy_attachment" "github_actions_dynamodb_fullaccess" {
  count = var.manage_github_actions_role_policies && var.github_actions_role_name != "" ? 1 : 0

  role       = var.github_actions_role_name
  policy_arn = "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess"
}

resource "aws_iam_role_policy_attachment" "github_actions_route53_fullaccess" {
  count = var.manage_github_actions_role_policies && var.github_actions_role_name != "" ? 1 : 0

  role       = var.github_actions_role_name
  policy_arn = "arn:aws:iam::aws:policy/AmazonRoute53FullAccess"
}

resource "aws_iam_role_policy_attachment" "github_actions_s3_fullaccess" {
  count = var.manage_github_actions_role_policies && var.github_actions_role_name != "" ? 1 : 0

  role       = var.github_actions_role_name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
}

resource "aws_iam_role_policy_attachment" "github_actions_iam_fullaccess" {
  count = var.manage_github_actions_role_policies && var.github_actions_role_name != "" ? 1 : 0

  role       = var.github_actions_role_name
  policy_arn = "arn:aws:iam::aws:policy/IAMFullAccess"
}
