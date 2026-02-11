# GitHub Actions Deployment Guide (OIDC, Detailed)

This guide covers the CI/CD path for this repo.

Use this path when you want:

- Single sequential automated deploy on push
- No long-lived AWS keys in GitHub
- Deterministic build -> push -> smoke test -> terraform -> SSM redeploy

## Workflow Files

- `.github/workflows/deploy-ec2.yml`
  - Main pipeline for this project
  - Trigger: push to `autonomous-trader-agent-aws` and manual dispatch

- `.github/workflows/push-ecr.yml`
  - Manual image-only workflow

- `.github/workflows/ci.yml`
  - PR checks (build/smoke) only

## Deployment Sequence (Main Workflow)

`deploy-ec2.yml` runs:

1. Assume AWS role via OIDC using `AWS_ROLE_ARN_TRADER`
2. Print assumed identity for verification
3. Build and push image to ECR (`latest` and commit SHA)
4. Smoke test the pushed image (`/health`)
5. Generate `terraform/terraform.tfvars` in CI
6. Import existing EC2 instance into ephemeral CI Terraform state
7. Optional SG rule import if enabled by variable
8. `terraform apply`
9. Redeploy container on EC2 via SSM (`docker pull` + restart)

## Why OIDC Is Used

OIDC replaces static AWS access keys in GitHub.

Benefits:
- Short-lived AWS credentials
- Better security posture
- Easier credential rotation (trust policy driven)

## Required GitHub Secrets

Go to:
- GitHub repo -> Settings -> Secrets and variables -> Actions -> Secrets

Create:

1. `AWS_ROLE_ARN_TRADER`
   - Example: `arn:aws:iam::348375262167:role/github-actions-autonomous-trader-deploy`
   - Purpose: Role assumed by GitHub OIDC for deploy permissions.

2. `DEFAULT_AWS_REGION`
   - Example: `ap-southeast-1`
   - Purpose: Region used by workflows and Terraform tfvars generation.

3. `ECR_REPOSITORY`
   - Example: `autonomous-trader`
   - Purpose: ECR repository name for build/push/pull.

4. `EC2_INSTANCE_ID`
   - Example: `i-0bdcead3b436c1ba4`
   - Purpose: Target instance for SSM redeploy and Terraform import.

## Required GitHub Variables

Go to:
- GitHub repo -> Settings -> Secrets and variables -> Actions -> Variables

Set:

1. `EC2_KEY_NAME`
   - Example: `rgkey`
   - Used by Terraform metadata when handling existing instance config.

Optional:

2. `PROJECT_NAME` (default `autonomous-trader`)
3. `APP_DOMAIN_NAME` (for deployment link output)
4. `ENABLE_ROUTE53_DNS` (`true` / `false`)
5. `ROUTE53_ZONE_NAME` (if Route53 enabled)
6. `MANAGE_EXISTING_SG_RULES` (`true` / `false`)
7. `EXISTING_SECURITY_GROUP_ID`
8. `ALLOWED_SSH_CIDR`

## One-Time IAM Setup (Role + Policy + Trust)

Use helper script:

- `scripts/aws-iam-setup-gha-deploy-role.sh`

Run:

```bash
./scripts/aws-iam-setup-gha-deploy-role.sh \
  arn:aws:iam::<ACCOUNT_ID>:role/github-actions-autonomous-trader-deploy
```

What it does:
- Ensures GitHub OIDC provider exists
- Creates role if missing
- Updates role trust policy
- Creates/updates deploy policy
- Attaches policy or falls back to inline if managed-policy quota is reached

## Trust Policy Notes (Important)

GitHub token `sub` differs by context:

- Branch run: `repo:<owner>/<repo>:ref:refs/heads/<branch>`
- Environment run: `repo:<owner>/<repo>:environment:<env>`

This repo uses workflow environments (`dev`, `prod`) in deploy workflow.
The setup script handles both patterns by default.

If you use different environments, set before running script:

```bash
export GITHUB_ENVIRONMENTS="dev,prod,staging"
```

## EC2 Requirements For CI Redeploy

Because redeploy uses SSM:

- EC2 instance must be SSM-managed and online
- EC2 instance role must allow ECR pull (`AmazonEC2ContainerRegistryReadOnly`)

Verify SSM:

```bash
aws ssm describe-instance-information \
  --query "InstanceInformationList[?InstanceId=='i-xxxxxxxxxxxxxxxxx'].[InstanceId,PingStatus]" \
  --output table
```

## Triggering Deploy

### Automatic

Push to:

- `autonomous-trader-agent-aws`

### Manual

GitHub:
- Actions -> "Deploy To EC2 (Terraform + ECR)" -> Run workflow
- Choose environment (`dev` or `prod`)

## Troubleshooting

### Could not assume role with OIDC

Cause:
- Trust `sub` mismatch or wrong `AWS_ROLE_ARN_TRADER`.

Fix:
1. Confirm secret `AWS_ROLE_ARN_TRADER` points to correct role.
2. Re-run IAM setup script for that role.
3. Check "Verify Assumed AWS Identity" step output.

### Unauthorized `ec2:Describe*`

Cause:
- Missing EC2 read permissions in role policy.

Fix:
- Re-run setup script (policy includes `ec2:Describe*`).

### Unauthorized `ecr:GetDownloadUrlForLayer`

Cause:
- Missing ECR pull action in role policy.

Fix:
- Re-run setup script (policy includes this action).

### Terraform import/state related errors in CI

Cause:
- CI state is ephemeral.

Fix:
- Workflow already imports existing instance each run.
- If SG rule management is enabled, ensure SG vars are correct and `ALLOWED_SSH_CIDR` matches actual rule.

### Deploy succeeds but app not updated on EC2

Check on EC2:

```bash
docker ps
docker logs --tail 100 autonomous-trader
```

Also verify workflow SSM step succeeded and pulled expected `:latest` image.

## When To Prefer Local Terraform Instead

Use local Terraform (`scripts/terraform-deploy.sh`) when:
- You need immediate manual control of env sync via SSH
- You need to debug infra changes interactively
- You are introducing new network/security settings and want manual rollout

Reference:
- `DEPLOY_TERRAFORM.md`
