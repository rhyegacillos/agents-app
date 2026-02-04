# Deploy From ECR to EC2 (Detailed)

This guide deploys this repo as a Docker container on one EC2 instance, pulling the image from ECR.

## Why this guide avoids `latest`

Use a versioned tag (example: `ec2-v1`) to avoid pulling the wrong image accidentally.
If multiple projects push `latest` to the same repo, EC2 can run unexpected code.

---

## 0) Required prerequisites

- You already have an ECR repository (example: `autonomous-trader`).
- Your EC2 instance has an IAM role with:
  - `AmazonEC2ContainerRegistryReadOnly`
- Security group allows:
  - `22/tcp` from your IP (SSH)
  - `8000/tcp` from your IP (or trusted CIDR) for app access

---

## 1) Local build and push to ECR

### 1.1 Set variables once (local machine)

```bash
export AWS_ACCOUNT_ID=348375262167
export AWS_REGION=ap-southeast-1
export ECR_REPO=autonomous-trader
export IMAGE_TAG=ec2-v1
```

What this does:
- `AWS_ACCOUNT_ID` and `AWS_REGION` build the ECR registry URL.
- `ECR_REPO` is your ECR repository name.
- `IMAGE_TAG` is your deploy version.

Optional quick check:
```bash
echo "$AWS_ACCOUNT_ID"
echo "$AWS_REGION"
echo "$ECR_REPO"
echo "$IMAGE_TAG"
```

### 1.2 Build Linux x86_64 image

```bash
docker build --platform linux/amd64 -t ${ECR_REPO}:${IMAGE_TAG} .
```

Why:
- App Runner/EC2 here run x86_64 Linux.
- Building with `--platform linux/amd64` avoids architecture mismatch (common on Apple Silicon).

### 1.3 Tag image for ECR

```bash
docker tag ${ECR_REPO}:${IMAGE_TAG} \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}
```

Why:
- Docker local tags are not enough for ECR.
- This adds the full remote ECR path.

### 1.4 Login to ECR

```bash
aws ecr get-login-password --region ${AWS_REGION} \
  | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com
```

Why:
- ECR requires auth token for push/pull.
- Token comes from AWS CLI using your local AWS credentials.

### 1.5 Push image

```bash
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}
```

Why:
- Uploads that exact tagged image so EC2 can pull it.

---

## 2) EC2 setup (first time only)

### 2.1 Launch instance

Recommended:
- AMI: Amazon Linux 2023
- Size: `t3.small` minimum
- Disk: 20 GB gp3+
- Auto-assign public IP: enabled

### 2.2 Attach IAM role to instance

Use role with:
- `AmazonEC2ContainerRegistryReadOnly`

Verify on EC2 later with:
```bash
aws sts get-caller-identity
```

### 2.3 Connect via SSH

From your local machine:
```bash
ssh -i /path/to/key.pem ec2-user@<EC2_PUBLIC_DNS_OR_IP>
```

### 2.4 Install Docker + AWS CLI on Amazon Linux 2023

```bash
sudo dnf update -y
sudo dnf install -y docker awscli
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user
newgrp docker
```

What each command does:
- `dnf update/install`: installs required packages.
- `systemctl enable --now`: starts Docker now and on reboot.
- `usermod -aG docker`: lets `ec2-user` run Docker without `sudo`.
- `newgrp docker`: refreshes shell group permissions immediately.

### 2.5 Verify runtime tools

```bash
docker --version
aws --version
aws sts get-caller-identity
```

`aws sts get-caller-identity` must return your account/role ARN. If it fails, fix IAM role first.

---

## 3) Pull image on EC2

### 3.1 Set same variables on EC2

```bash
export AWS_ACCOUNT_ID=348375262167
export AWS_REGION=ap-southeast-1
export ECR_REPO=autonomous-trader
export IMAGE_TAG=ec2-v1
```

### 3.2 Login to ECR from EC2

```bash
aws ecr get-login-password --region ${AWS_REGION} \
  | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com
```

### 3.3 Pull exact image tag

```bash
docker pull ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}
```

Why:
- Pulling an exact tag guarantees you run the expected build.

---

## 4) Create environment file on EC2

Create `/home/ec2-user/autonomous-trader.env`:

```env
TRADER_ENGINE_DIR=/app/api/trader_engine
TRADER_DATA_DIR=/app/api/data

READ_ONLY_MODE=true
AUTO_TRADE_BY_MARKET=true
MARKET_WATCH_INTERVAL_SEC=60
RUN_EVERY_N_MINUTES=60
RUN_EVEN_WHEN_MARKET_IS_CLOSED=false

OPENAI_API_KEY=YOUR_OPENAI_KEY
POLYGON_API_KEY=YOUR_POLYGON_KEY
POLYGON_PLAN=free
BRAVE_API_KEY=YOUR_BRAVE_KEY
ENABLE_BRAVE_MCP=true
ENABLE_FETCH_MCP=true
ENABLE_MEMORY_MCP=true
```

Why:
- Keeps secrets/config outside image.
- Easy to rotate keys without rebuilding image.

---

## 5) Run container on EC2

### 5.1 Create persistent host directory

```bash
sudo mkdir -p /opt/autonomous-trader/data
sudo chown -R ec2-user:ec2-user /opt/autonomous-trader
```

Why:
- Stores SQLite/runtime files on host disk so restarts do not wipe data.

### 5.2 Run container

```bash
docker run -d --name autonomous-trader \
  -p 8000:8000 \
  --env-file /home/ec2-user/autonomous-trader.env \
  -v /opt/autonomous-trader/data:/app/api/data \
  --restart unless-stopped \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}
```

What key flags do:
- `-d`: run in background
- `--name`: stable container name for logs/restarts
- `-p 8000:8000`: expose app port
- `--env-file`: load runtime config/secrets
- `-v ...:/app/api/data`: persist app data
- `--restart unless-stopped`: auto-restart after reboot

---

## 6) Verify deployment

```bash
docker ps
docker logs --tail 100 autonomous-trader
curl http://localhost:8000/health
```

Expected:
- `docker ps` shows container `Up`.
- `curl` returns `{"status":"ok"}`.

From your laptop/browser:
```text
http://<EC2_PUBLIC_DNS_OR_IP>:8000
```

---

## 7) Update deployment (new app version)

### 7.1 Build and push new tag (local)

```bash
export IMAGE_TAG=ec2-v2
docker build --platform linux/amd64 -t ${ECR_REPO}:${IMAGE_TAG} .
docker tag ${ECR_REPO}:${IMAGE_TAG} ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}
```

### 7.2 Pull and switch on EC2

```bash
docker pull ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}
docker rm -f autonomous-trader
docker run -d --name autonomous-trader \
  -p 8000:8000 \
  --env-file /home/ec2-user/autonomous-trader.env \
  -v /opt/autonomous-trader/data:/app/api/data \
  --restart unless-stopped \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}
```

---

## 8) Troubleshooting

- **Container resets immediately**
  - Check: `docker logs --tail 200 autonomous-trader`
  - Common cause: wrong image tag/repo.
- **`aws sts get-caller-identity` fails**
  - IAM role missing/not attached to EC2.
- **Cannot access from browser**
  - Security group missing inbound `8000/tcp`.
- **`Permission denied` under `/opt`**
  - Run the `sudo mkdir` + `sudo chown` commands in step 5.1.

---

## 9) Operational notes

- Run one EC2 instance for this architecture (single trading loop).
- Keep `READ_ONLY_MODE=true` in internet-facing deployments.
- Keep versioned tags; avoid `latest` for production safety.
