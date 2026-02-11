#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="${SCRIPT_DIR}/../terraform"

if [[ ! -d "${TF_DIR}" ]]; then
  echo "Terraform directory not found at ${TF_DIR}" >&2
  exit 1
fi

if [[ -f "${TF_DIR}/terraform.tfvars.local" ]]; then
  cp "${TF_DIR}/terraform.tfvars.local" "${TF_DIR}/terraform.tfvars"
fi

if [[ ! -f "${TF_DIR}/terraform.tfvars" ]]; then
  if [[ -f "${TF_DIR}/terraform.tfvars.example" ]]; then
    echo "Missing terraform/terraform.tfvars. Copy terraform/terraform.tfvars.example to terraform.tfvars.local and fill values." >&2
  else
    echo "Missing terraform/terraform.tfvars." >&2
  fi
  exit 1
fi

cd "${TF_DIR}"
terraform init

read_tfvar() {
  local key="$1"
  local raw
  raw=$(awk -F= -v k="$key" '$1 ~ "^[ \t]*"k"[ \t]*$" {print $2}' terraform.tfvars | tail -n1)
  raw="${raw#"${raw%%[![:space:]]*}"}"
  raw="${raw%"${raw##*[![:space:]]}"}"
  raw="${raw%\"}"; raw="${raw#\"}"
  raw="${raw%\'}"; raw="${raw#\'}"
  echo "$raw"
}

existing_instance_id="$(read_tfvar existing_instance_id)"
existing_instance_tag_name="$(read_tfvar existing_instance_tag_name)"
manage_existing="$(read_tfvar manage_existing)"
project_name="$(read_tfvar project_name)"
aws_region="$(read_tfvar aws_region)"
tf_deploy_key="$(read_tfvar deploy_ssh_key)"
tf_deploy_user="$(read_tfvar deploy_ssh_user)"
enable_https="$(read_tfvar enable_https)"
domain_name="$(read_tfvar domain_name)"
certbot_email="$(read_tfvar certbot_email)"
manage_existing_sg_rules="$(read_tfvar manage_existing_sg_rules)"
build_and_push="${BUILD_AND_PUSH:-true}"
docker_platform="${DOCKER_PLATFORM:-linux/amd64}"

if [[ -z "${existing_instance_id}" && -n "${existing_instance_tag_name}" ]]; then
  if command -v aws >/dev/null 2>&1; then
    detected_id="$(aws ec2 describe-instances --region "${aws_region}" \
      --filters "Name=tag:Name,Values=${existing_instance_tag_name}" \
                "Name=instance-state-name,Values=pending,running,stopping,stopped" \
      --query "Reservations[].Instances[].InstanceId" --output text 2>/dev/null | awk '{print $1}')"
    if [[ -n "${detected_id}" && "${detected_id}" != "None" ]]; then
      existing_instance_id="${detected_id}"
      export TF_VAR_existing_instance_id="${existing_instance_id}"
      echo "Detected existing instance: ${existing_instance_id}"
    fi
  fi
fi

if [[ "${manage_existing}" == "true" ]]; then
  if [[ -z "${existing_instance_id}" ]]; then
    echo "manage_existing=true but no existing_instance_id detected. Set it in terraform.tfvars." >&2
    exit 1
  fi

  if ! terraform state list 2>/dev/null | grep -q '^aws_instance\.app\[0\]$'; then
    terraform import aws_instance.app[0] "${existing_instance_id}"
  fi
fi

if [[ "${manage_existing_sg_rules}" == "true" ]]; then
  # Avoid duplicate SG rule creation by importing existing rules automatically when present.
  "${SCRIPT_DIR}/terraform-import-sg.sh"
fi

terraform apply -auto-approve

# Some AWS provider operations can transiently drop SG rule resources from state
# during refresh right after creation. Re-import after apply to keep state stable.
if [[ "${manage_existing_sg_rules}" == "true" ]]; then
  "${SCRIPT_DIR}/terraform-import-sg.sh" || true
fi

deploy_key="${DEPLOY_SSH_KEY:-${tf_deploy_key:-}}"
deploy_user="${DEPLOY_SSH_USER:-${tf_deploy_user:-ec2-user}}"
deploy_env_file="${DEPLOY_ENV_FILE:-}"

if [[ -z "${deploy_key}" ]]; then
  default_key="${SCRIPT_DIR}/../rgkey.pem"
  if [[ -f "${default_key}" ]]; then
    deploy_key="${default_key}"
  fi
fi

if [[ -n "${deploy_key}" ]]; then
  deploy_host="$(terraform output -raw public_dns 2>/dev/null || true)"
  if [[ -z "${deploy_host}" && -n "${existing_instance_id}" && $(command -v aws) ]]; then
    deploy_host="$(aws ec2 describe-instances --region "${aws_region}" --instance-ids "${existing_instance_id}" \
      --query "Reservations[].Instances[].PublicDnsName" --output text 2>/dev/null)"
  fi

  if [[ -n "${deploy_host}" ]]; then
    image_uri="$(terraform output -raw image_uri)"

    # Optional: build+push the image to ECR so EC2 can pull fresh code/UI changes.
    #
    # This keeps Terraform as "infra + deploy orchestration" without introducing
    # a separate CI pipeline requirement for personal projects.
    if [[ "${build_and_push}" == "true" ]]; then
      if ! command -v aws >/dev/null 2>&1; then
        echo "ERROR: BUILD_AND_PUSH=true requires the AWS CLI on this machine." >&2
        exit 1
      fi
      if ! command -v docker >/dev/null 2>&1; then
        echo "ERROR: BUILD_AND_PUSH=true requires Docker on this machine." >&2
        exit 1
      fi

      # Derive repo name from the computed image_uri so we don't require `ecr_repo`
      # to be explicitly set in terraform.tfvars (it has a sensible default).
      image_path="${image_uri#*/}"           # <repo>:<tag>
      ecr_repo="${image_path%%:*}"           # <repo>
      if [[ -z "${ecr_repo}" || "${ecr_repo}" == "${image_uri}" ]]; then
        echo "ERROR: Could not derive ECR repo from image_uri: ${image_uri}" >&2
        exit 1
      fi

      # Ensure repo exists (portable: no manual console steps).
      if ! aws ecr describe-repositories --repository-names "${ecr_repo}" --region "${aws_region}" >/dev/null 2>&1; then
        echo "ECR repo ${ecr_repo} not found; creating..."
        aws ecr create-repository --repository-name "${ecr_repo}" --region "${aws_region}" >/dev/null
      fi

      registry="${image_uri%/*}"
      echo "Logging into ECR registry ${registry}..."
      aws ecr get-login-password --region "${aws_region}" | docker login --username AWS --password-stdin "${registry}" >/dev/null

      repo_root="$(cd "${SCRIPT_DIR}/.." && pwd)"
      echo "Building and pushing ${image_uri} (platform: ${docker_platform})..."
      cd "${repo_root}"

      if docker buildx version >/dev/null 2>&1; then
        docker buildx build --platform "${docker_platform}" -t "${image_uri}" --push .
      else
        docker build -t "${image_uri}" .
        docker push "${image_uri}"
      fi

      cd "${TF_DIR}"
    fi

    if [[ -n "${deploy_env_file}" ]]; then
      if [[ ! -f "${deploy_env_file}" ]]; then
        echo "DEPLOY_ENV_FILE not found: ${deploy_env_file}" >&2
        exit 1
      fi
      env_source="${deploy_env_file}"
    else
      env_content="$(terraform output -raw env_file_content)"
      tmp_env="$(mktemp)"
      printf "%s\n" "${env_content}" > "${tmp_env}"
      env_source="${tmp_env}"
    fi

    scp -o StrictHostKeyChecking=accept-new -i "${deploy_key}" "${env_source}" \
      "${deploy_user}@${deploy_host}:/home/ec2-user/autonomous-trader.env"

    host_port="80"
    if [[ "${enable_https}" == "true" ]]; then
      host_port="8000"
    fi

    remote_script="$(mktemp)"
    # NOTE: This outer heredoc must be quoted. Otherwise bash will expand nginx vars like `$host`
    # while generating the remote script, and with `set -u` that crashes with `host: unbound variable`.
    cat > "${remote_script}" <<'REMOTE_SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

sudo mkdir -p /opt/__PROJECT_NAME__/data
sudo chown -R ec2-user:ec2-user /opt/__PROJECT_NAME__

aws ecr get-login-password --region "__AWS_REGION__" | sudo docker login --username AWS --password-stdin "__ECR_REGISTRY__"
sudo docker pull "__IMAGE_URI__"
sudo docker stop __PROJECT_NAME__ >/dev/null 2>&1 || true
sudo docker rm __PROJECT_NAME__ >/dev/null 2>&1 || true
sudo docker run -d \
  --name "__PROJECT_NAME__" \
  -p "__HOST_PORT__:8000" \
  --env-file "/home/ec2-user/autonomous-trader.env" \
  -v "/opt/__PROJECT_NAME__/data:/app/api/data" \
  --restart unless-stopped \
  "__IMAGE_URI__"

if [[ "__ENABLE_HTTPS__" == "true" && -n "__DOMAIN_NAME__" && -n "__CERTBOT_EMAIL__" && "__CERTBOT_EMAIL__" != "REPLACE_ME" ]]; then
  sudo dnf -y install nginx certbot python3-certbot-nginx
  sudo systemctl enable --now nginx

  # Use a quoted heredoc so nginx variables like $host are never expanded by bash (set -u).
  # ${domain_name} is already substituted when this remote script is generated locally.
  sudo tee /etc/nginx/conf.d/__PROJECT_NAME__.conf >/dev/null <<'NGINX'
server {
  listen 80;
  server_name __DOMAIN_NAME__;

  location / {
    proxy_pass http://localhost:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}
NGINX

  sudo nginx -t && sudo systemctl reload nginx
  sudo certbot --nginx -d __DOMAIN_NAME__ --non-interactive --agree-tos -m __CERTBOT_EMAIL__
  sudo systemctl enable --now certbot-renew.timer || true
fi
REMOTE_SCRIPT

    PROJECT_NAME="${project_name}" \
    AWS_REGION="${aws_region}" \
    IMAGE_URI="${image_uri}" \
    ECR_REGISTRY="${image_uri%/*}" \
    HOST_PORT="${host_port}" \
    ENABLE_HTTPS="${enable_https}" \
    DOMAIN_NAME="${domain_name}" \
    CERTBOT_EMAIL="${certbot_email}" \
      python3 - "${remote_script}" <<'PY'
import os
import sys

path = sys.argv[1]
data = open(path, "r", encoding="utf-8").read()

repl = {
    "__PROJECT_NAME__": os.environ["PROJECT_NAME"],
    "__AWS_REGION__": os.environ["AWS_REGION"],
    "__IMAGE_URI__": os.environ["IMAGE_URI"],
    "__ECR_REGISTRY__": os.environ["ECR_REGISTRY"],
    "__HOST_PORT__": os.environ["HOST_PORT"],
    "__ENABLE_HTTPS__": os.environ["ENABLE_HTTPS"],
    "__DOMAIN_NAME__": os.environ["DOMAIN_NAME"],
    "__CERTBOT_EMAIL__": os.environ["CERTBOT_EMAIL"],
}

for k, v in repl.items():
    data = data.replace(k, v)

open(path, "w", encoding="utf-8").write(data)
PY

    scp -o StrictHostKeyChecking=accept-new -i "${deploy_key}" "${remote_script}" \
      "${deploy_user}@${deploy_host}:/home/ec2-user/autonomous-trader-deploy.sh"

    ssh -o StrictHostKeyChecking=accept-new -i "${deploy_key}" "${deploy_user}@${deploy_host}" \
      "bash /home/ec2-user/autonomous-trader-deploy.sh && rm -f /home/ec2-user/autonomous-trader-deploy.sh"

    rm -f "${remote_script}"

    if [[ -n "${tmp_env:-}" ]]; then
      rm -f "${tmp_env}"
    fi
    if [[ "${enable_https}" == "true" && -n "${domain_name}" ]]; then
      echo "HTTPS URL: https://${domain_name}"
    else
      if [[ -n "${deploy_host}" ]]; then
        echo "HTTP URL: http://${deploy_host}"
      fi
    fi
    echo "Updated env file and restarted container on ${deploy_host}"
  else
    echo "Skipping env sync: could not resolve public DNS."
  fi
else
  echo "Skipping env sync: set DEPLOY_SSH_KEY to update env on instance."
fi
