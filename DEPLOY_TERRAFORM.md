# Terraform Deployment Guide (Local, Detailed)

This guide covers deploying the app with local Terraform + scripts.

Use this path when you want:

- Full local control over infra and rollout timing
- Optional SSH-based env sync to EC2 from your machine
- Optional local image build/push during deploy

Use GitHub Actions instead when you want automated CI/CD on push.

## Terraform Files Explained (What, How, Why)

This section explains each file under `terraform/` and why it exists in this project.

### `terraform/versions.tf`

What it is for:
- Pins Terraform and provider compatibility.

How it is used:
- Enforces `terraform >= 1.5.0`.
- Enforces AWS provider version family (`hashicorp/aws >= 5.0.0`).

Why this exists:
- Prevents local/CI drift caused by incompatible provider upgrades.
- Keeps plans reproducible across machines.

### `terraform/variables.tf`

What it is for:
- Defines all deployment inputs for this stack.

How it is used:
- Inputs control mode and behavior:
  - existing-vs-new instance (`existing_instance_id`, `manage_existing`)
  - existing SG rule management (`manage_existing_sg_rules`, `existing_security_group_id`, `allowed_ssh_cidr`)
  - image settings (`ecr_repo`, `image_tag`)
  - runtime env map (`env_vars`)
  - HTTPS and DNS (`enable_https`, `domain_name`, `certbot_email`, `enable_route53_dns`, zone values)

Why this exists:
- Keeps environment-specific settings out of Terraform code.
- Lets the same code run in local, EC2, and CI contexts.

### `terraform/main.tf`

What it is for:
- Core infrastructure logic and conditional resource creation.

How it is used in this project:
- Configures AWS provider region (`var.aws_region`).
- Reads account and baseline network data (`aws_caller_identity`, default VPC/subnets).
- Detects an existing instance (by explicit ID or by `tag:Name` lookup).
- Supports two deployment paths:
  - Manage existing instance
  - Create new instance and security group
- Builds derived values in `locals`:
  - ECR `image_uri`
  - rendered env file content from `env_vars`
  - routing decisions (`use_existing`, `manage_existing`, `existing_sg_id`)
- Manages ingress rules using `aws_vpc_security_group_ingress_rule`:
  - Existing SG path: `existing_http`, `existing_https`, `existing_ssh`
  - New SG path: `new_http`, `new_https`, `new_ssh`
- Optionally creates Route53 A record when enabled.
- For new instance path:
  - Creates EC2 IAM role/profile with ECR pull policy
  - Boots instance with `userdata.sh.tpl`
- For existing instance path:
  - Reuses AMI/type/subnet/SG/instance profile attributes from live instance
  - Does not apply user data (`user_data = null`)

Why this exists:
- A single Terraform stack supports both "new infra" and "adopt existing infra" without duplicating files.
- Conditional logic and preconditions fail fast for invalid configs.
- `prevent_destroy = true` protects against accidental instance deletion.

### `terraform/outputs.tf`

What it is for:
- Exposes deployment values for scripts and CI.

How it is used:
- `public_ip`, `public_dns`, `app_url`: connection outputs.
- `image_uri`: image reference used by deploy scripts/CI.
- `env_file_content` (sensitive): rendered `KEY=VALUE` content from `env_vars`.

Why this exists:
- Scripts can consume outputs directly instead of re-deriving values.
- Reduces manual copy/paste mistakes.

### `terraform/userdata.sh.tpl`

What it is for:
- First-boot bootstrap script for newly created EC2 instances.

How it is used:
- Installs Docker.
- Creates persistent data dir (`/opt/<project_name>/data`).
- Writes app env file (`/home/ec2-user/autonomous-trader.env`) from rendered Terraform vars.
- Logs into ECR and pulls image.
- Runs container with restart policy and data volume mount.
- Optional HTTPS path:
  - installs Nginx + Certbot
  - writes reverse-proxy config
  - obtains/renews certificate

Why this exists:
- New instances become runnable without manual SSH provisioning.
- Encodes baseline host setup as code.

### `terraform/terraform.tfvars.example`

What it is for:
- Template of expected inputs and defaults.

How it is used:
- Copy to `terraform/terraform.tfvars.local`.
- Fill real values (instance IDs, domain, API keys).

Why this exists:
- Documents all required/optional variables in a working structure.
- Speeds onboarding and reduces config omissions.

### `terraform/terraform.tfvars.local` (local only, gitignored)

What it is for:
- Your real deployment values, including sensitive keys.

How it is used:
- `scripts/terraform-deploy.sh` copies it to `terraform/terraform.tfvars` before running Terraform.

Why this exists:
- Keeps secrets out of git while preserving reproducible local deploys.

### `terraform/terraform.tfstate*` and `terraform/.terraform` (generated)

What they are for:
- Terraform state and provider/plugin cache.

How they are used:
- Track what Terraform manages and with which resource IDs.

Why this matters:
- Must remain gitignored.
- Losing local state is recoverable for this repo because import helpers exist, but state consistency still saves time.

## What This Path Does

`scripts/terraform-deploy.sh` orchestrates:

1. Load `terraform/terraform.tfvars.local` into `terraform/terraform.tfvars`
2. `terraform init`
3. Optional import of existing EC2 instance
4. Optional import of existing SG rules (to avoid duplicate create errors)
5. `terraform apply -auto-approve`
6. Optional Docker build/push to ECR (default enabled)
7. Optional SSH env sync + container restart on EC2
8. Optional Nginx + Certbot setup on EC2 when HTTPS is enabled

## Prerequisites

### Local machine

- `terraform` installed
- `aws` CLI installed and authenticated (`aws sts get-caller-identity` works)
- `docker` installed (if `BUILD_AND_PUSH=true`)
- SSH key file available if you want SSH sync (`DEPLOY_SSH_KEY` or `rgkey.pem`)

### AWS account resources

- ECR repository (or permission to create it)
- EC2 instance (existing mode), or permissions to create one
- Route53 hosted zone (only if enabling Route53 DNS)

## Files Used

- Terraform code: `terraform/main.tf`, `terraform/variables.tf`, `terraform/outputs.tf`
- Local vars template: `terraform/terraform.tfvars.example`
- Local vars runtime: `terraform/terraform.tfvars.local` (gitignored)
- Deploy script: `scripts/terraform-deploy.sh`
- SG import helper: `scripts/terraform-import-sg.sh`

## Step 1: Prepare Terraform Variables

Create local vars file:

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars.local
```

Edit `terraform/terraform.tfvars.local`.

## Step 2: Choose Deployment Mode

### Mode A: Manage existing EC2 (recommended for this repo)

Set:

```hcl
manage_existing      = true
existing_instance_id = "i-xxxxxxxxxxxxxxxxx"
```

Optional auto-detect alternative:

```hcl
existing_instance_id       = ""
existing_instance_tag_name = "autonomous-trader-app"
```

Why:
- You keep your current EC2 instance and let Terraform manage metadata and optional DNS/rules.

### Mode B: Create new EC2 from Terraform

Set:

```hcl
manage_existing      = false
existing_instance_id = ""
```

Why:
- Terraform provisions a fresh EC2 + SG + IAM profile path.

## Step 3: Security Group Rule Strategy (Existing Instance)

If your existing SG already has ingress rules, enable import management:

```hcl
manage_existing_sg_rules = true
existing_security_group_id = "sg-xxxxxxxxxxxxxxxxx" # optional but recommended
allowed_ssh_cidr = "YOUR_PUBLIC_IP/32"
```

Why:
- Avoids `InvalidPermission.Duplicate` on apply.
- `scripts/terraform-import-sg.sh` imports existing `80/443/22` rules by `sgr-...` IDs.

How to get your public IP CIDR:

```bash
echo "$(curl -s https://checkip.amazonaws.com)/32"
```

## Step 4: App Environment Variables in Terraform

Set runtime env in `env_vars` map inside `terraform/terraform.tfvars.local`, for example:

```hcl
env_vars = {
  POLYGON_API_KEY                = "REPLACE_ME"
  POLYGON_PLAN                   = "free"
  BRAVE_API_KEY                  = "REPLACE_ME"
  ENABLE_BRAVE_MCP               = "true"
  READ_ONLY_MODE                 = "true"
  AUTO_TRADE_BY_MARKET           = "true"
  RUN_EVEN_WHEN_MARKET_IS_CLOSED = "false"
}
```

What this is for:
- Script generates `/home/ec2-user/autonomous-trader.env` content from these values.
- EC2 container runs with that env file.

## Step 5: Optional HTTPS + DNS

Enable:

```hcl
enable_https      = true
domain_name       = "autonomous-trader.agentairg.site"
certbot_email     = "you@example.com"
enable_route53_dns = true
route53_zone_name  = "agentairg.site"
```

Why:
- Enables Nginx reverse proxy + Let's Encrypt cert on EC2.
- Terraform can manage Route53 A record.

When to use:
- You control DNS zone in Route53.
- Port 80/443 inbound is allowed in instance SG.

## Step 6: Run Deploy

Run:

```bash
./scripts/terraform-deploy.sh
```

What success looks like:
- `terraform apply` completes
- script prints `HTTP URL: ...` or `HTTPS URL: ...`
- EC2 container restarts with new image/env

## Step 7: Verify

From local:

```bash
curl -fsS http://<EC2_PUBLIC_DNS>/health
```

or with domain/HTTPS:

```bash
curl -fsS https://autonomous-trader.agentairg.site/health
```

## Optional Runtime Controls

Disable image build/push during deploy:

```bash
BUILD_AND_PUSH=false ./scripts/terraform-deploy.sh
```

Force platform:

```bash
DOCKER_PLATFORM=linux/amd64 ./scripts/terraform-deploy.sh
```

Use explicit env file instead of Terraform output env:

```bash
DEPLOY_ENV_FILE=/path/to/autonomous-trader.env ./scripts/terraform-deploy.sh
```

Use explicit SSH key/user:

```bash
DEPLOY_SSH_KEY=/path/to/rgkey.pem DEPLOY_SSH_USER=ec2-user ./scripts/terraform-deploy.sh
```

## Common Errors and Fixes

### Duplicate SG rule error

Symptom:
- `InvalidPermission.Duplicate` during Terraform apply.

Fix:
1. Set `manage_existing_sg_rules = true`
2. Set correct `allowed_ssh_cidr`
3. Run `./scripts/terraform-import-sg.sh`
4. Re-run deploy

### Rule import says not found

Root causes:
- Wrong AWS region
- Wrong SG ID
- CIDR mismatch on port 22

Fix:
- Ensure `aws_region` and `existing_security_group_id` in `terraform.tfvars.local` are correct.

### HTTPS setup fails with certbot

Root causes:
- Domain DNS does not point to EC2 public IP yet
- Port 80/443 blocked

Fix:
- Confirm A record and SG inbound rules before enabling `enable_https=true`.

## Destroy

Use:

```bash
./scripts/terraform-destroy.sh
```

Important:
- Existing instance resources are protected by `prevent_destroy` in Terraform.
- Review plan carefully before destroy.
