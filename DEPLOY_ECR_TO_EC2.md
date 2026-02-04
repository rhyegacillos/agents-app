# Deploy to AWS ECR + EC2 (First-Time, Detailed)

This guide covers a full first-time setup:

1) create IAM role(s)  
2) create ECR repo  
3) launch EC2 with correct security + role  
4) push Docker image to ECR  
5) pull and run on EC2  
6) update safely with versioned tags

It is written for this repository (`autonomous-trader`) and uses one EC2 instance + one Docker container.

---

## 0) Before You Start

- AWS account/region (example: `ap-southeast-1`)
- Local machine with:
  - Docker
  - AWS CLI configured (`aws configure`)
- SSH keypair (`.pem`) for EC2 login

Recommended for this app:
- EC2 type: `t3.small` (or higher)
- OS: **Amazon Linux 2023**
- Storage: 20 GB gp3

---

## 1) One-Time AWS Setup (Roles, ECR, EC2)

## 1.1 Create ECR repository

### Option A: AWS Console
- Open **ECR** -> **Repositories** -> **Create repository**
- Name: `autonomous-trader`
- Leave defaults (private repo)
- Create

### Option B: AWS CLI
```bash
aws ecr describe-repositories --repository-names autonomous-trader --region ap-southeast-1 \
  || aws ecr create-repository --repository-name autonomous-trader --region ap-southeast-1
```

What this does:
- `describe-repositories`: checks if repo exists
- `create-repository`: creates it only when missing

---

## 1.2 Create IAM role for EC2 (pull from ECR)

This role is attached to the EC2 instance so EC2 can run `aws ecr get-login-password` without static keys.

### Console steps
- Open **IAM** -> **Roles** -> **Create role**
- Trusted entity: **AWS service**
- Use case: **EC2**
- Attach policy:
  - `AmazonEC2ContainerRegistryReadOnly`
- Role name example: `ec2-ecr-readonly-role`
- Create role

### Attach role to EC2 later
You attach this role during launch (or via **Actions -> Security -> Modify IAM role** on existing instance).

---

## 1.3 Local IAM permissions (for push from laptop)

Your local AWS identity (user or role) needs ECR push permissions. Easiest:

- `AmazonEC2ContainerRegistryPowerUser` (or admin-level equivalent)

Why:
- EC2 role above is read-only (pull).  
- Local machine needs push access (login, upload layers, push manifests).

---

## 1.4 Launch EC2 instance

### Required instance launch choices
- AMI: **Amazon Linux 2023**
- Instance type: `t3.small` (or `t3.medium` if workload is heavier)
- Key pair: choose/create one and download `.pem`
- Auto-assign Public IP: **Enable**
- IAM role: `ec2-ecr-readonly-role`

### Security group inbound rules (recommended)
1. `SSH` TCP 22, Source: **My IP**  
2. `HTTP` TCP 80, Source: `0.0.0.0/0`  
3. (Optional debug) `Custom TCP` 8000, Source: **My IP**

Why:
- Port 80 gives URL access without `:8000`.
- Port 8000 is only for temporary debug/testing.

---

## 1.5 Verify EC2 role is active

SSH into the instance:
```bash
ssh -i /path/to/key.pem ec2-user@<EC2_PUBLIC_DNS>
```

Then verify identity:
```bash
aws sts get-caller-identity
```

Expected:
- `Arn` should include `assumed-role/ec2-ecr-readonly-role/...`

If this fails:
- role not attached
- wrong role
- IMDS/instance profile issue

---

## 2) Local Build + Push to ECR

## 2.1 Set deploy variables (local)

```bash
export AWS_ACCOUNT_ID=348375262167
export AWS_REGION=ap-southeast-1
export ECR_REPO=autonomous-trader
export IMAGE_TAG=ec2-v1
```

Use versioned tags (`ec2-v1`, `ec2-v2`) instead of `latest`.

---

## 2.2 Build linux/amd64 image

```bash
docker build --platform linux/amd64 -t ${ECR_REPO}:${IMAGE_TAG} .
```

Why:
- avoids architecture mismatch (common when building on Apple Silicon)
- EC2 runtime is linux/amd64

---

## 2.3 Tag image for ECR URL

```bash
docker tag ${ECR_REPO}:${IMAGE_TAG} \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}
```

---

## 2.4 Login + Push

```bash
aws ecr get-login-password --region ${AWS_REGION} \
  | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}
```

---

## 3) Prepare EC2 Runtime (First Time Only)

## 3.1 Install Docker and tools

On EC2:
```bash
sudo dnf update -y
sudo dnf install -y docker awscli
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user
newgrp docker
```

Verify:
```bash
docker --version
aws --version
```

---

## 3.2 Set deployment variables on EC2

```bash
export AWS_ACCOUNT_ID=348375262167
export AWS_REGION=ap-southeast-1
export ECR_REPO=autonomous-trader
export IMAGE_TAG=ec2-v1
```

---

## 3.3 Login + Pull image on EC2

```bash
aws ecr get-login-password --region ${AWS_REGION} \
  | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

docker pull ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}
```

---

## 3.4 Create persistent data directory

```bash
sudo mkdir -p /opt/autonomous-trader/data
sudo chown -R ec2-user:ec2-user /opt/autonomous-trader
```

Why:
- keeps SQLite and runtime files outside container
- survives container recreation and upgrades

---

## 3.5 Create environment file on EC2

Create `/home/ec2-user/autonomous-trader.env`:

```env
TRADER_ENGINE_DIR=/app/api/trader_engine
TRADER_DATA_DIR=/app/api/data

READ_ONLY_MODE=true
AUTO_TRADE_BY_MARKET=true
MARKET_WATCH_INTERVAL_SEC=60
RUN_EVERY_N_MINUTES=60
RUN_EVEN_WHEN_MARKET_IS_CLOSED=false
STRICT_FLAT_WHEN_NO_TRADE=true

OPENAI_API_KEY=YOUR_OPENAI_KEY
DEEPSEEK_API_KEY=YOUR_DEEPSEEK_KEY
GOOGLE_API_KEY=YOUR_GOOGLE_KEY
GROK_API_KEY=YOUR_GROK_KEY

POLYGON_API_KEY=YOUR_POLYGON_KEY
POLYGON_PLAN=free
BRAVE_API_KEY=YOUR_BRAVE_KEY

ENABLE_BRAVE_MCP=true
ENABLE_FETCH_MCP=true
ENABLE_MEMORY_MCP=true
```

Notes:
- If a provider is unused, you can leave its key blank.
- Use `true/false` (case-insensitive in current app parser).

---

## 4) Run Container on EC2

## 4.1 Run on HTTP port 80 (recommended)

```bash
docker rm -f autonomous-trader 2>/dev/null || true

docker run -d --name autonomous-trader \
  -p 80:8000 \
  --env-file /home/ec2-user/autonomous-trader.env \
  -v /opt/autonomous-trader/data:/app/api/data \
  --restart unless-stopped \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}
```

What key flags mean:
- `-p 80:8000`: public HTTP on EC2 port 80 -> app listens in container on 8000
- `--env-file`: runtime config/secrets
- `-v`: persistence
- `--restart unless-stopped`: auto-start after reboot

---

## 4.2 Verify service

```bash
docker ps
docker logs --tail 100 autonomous-trader
curl http://localhost/health
```

From browser:
- `http://<EC2_PUBLIC_DNS>`
- or `http://<EC2_PUBLIC_IP>`

---

## 5) First-Time Reset Flow (if needed)

If you want to reset portfolios via API:
- `POST /api/reset` only works when `READ_ONLY_MODE=false`

Temporary flow:
1. set `READ_ONLY_MODE=false` in env file  
2. recreate container  
3. call reset  
4. set `READ_ONLY_MODE=true` again  
5. recreate container

Example:
```bash
sed -i 's/^READ_ONLY_MODE=.*/READ_ONLY_MODE=false/' /home/ec2-user/autonomous-trader.env
docker rm -f autonomous-trader
docker run -d --name autonomous-trader -p 80:8000 \
  --env-file /home/ec2-user/autonomous-trader.env \
  -v /opt/autonomous-trader/data:/app/api/data \
  --restart unless-stopped \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}

curl -X POST http://localhost/api/reset
```

---

## 6) Update Deployment (New Image Version)

## 6.1 Local: build/push new tag

```bash
export IMAGE_TAG=ec2-v2
docker build --platform linux/amd64 -t ${ECR_REPO}:${IMAGE_TAG} .
docker tag ${ECR_REPO}:${IMAGE_TAG} ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}
```

## 6.2 EC2: pull + recreate

```bash
docker pull ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}
docker rm -f autonomous-trader
docker run -d --name autonomous-trader \
  -p 80:8000 \
  --env-file /home/ec2-user/autonomous-trader.env \
  -v /opt/autonomous-trader/data:/app/api/data \
  --restart unless-stopped \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}
```

---

## 7) Rollback

If `ec2-v2` fails, roll back quickly:

```bash
export IMAGE_TAG=ec2-v1
docker pull ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}
docker rm -f autonomous-trader
docker run -d --name autonomous-trader \
  -p 80:8000 \
  --env-file /home/ec2-user/autonomous-trader.env \
  -v /opt/autonomous-trader/data:/app/api/data \
  --restart unless-stopped \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}
```

---

## 8) Troubleshooting Checklist

## A) SSH timeout
- instance not running
- wrong public DNS/IP
- SG missing inbound TCP 22 from your IP
- wrong key pair / wrong `.pem` path

## B) `aws sts get-caller-identity` fails on EC2
- IAM role not attached to instance
- metadata/instance profile issue

## C) `docker: invalid reference format`
- one of `${AWS_ACCOUNT_ID}`, `${AWS_REGION}`, `${ECR_REPO}`, `${IMAGE_TAG}` is empty
- check with:
```bash
echo "$AWS_ACCOUNT_ID" "$AWS_REGION" "$ECR_REPO" "$IMAGE_TAG"
```

## D) Browser timeout
- SG missing HTTP 80 inbound
- container not healthy (`docker ps`, `docker logs`)
- app mapped to 8000 but browser opened without `:8000`

## E) Health works locally on EC2 but not from internet
- verify SG uses correct source CIDR (`0.0.0.0/0` for public HTTP)
- confirm instance has public IPv4 and route to internet gateway

---

## 9) Operational Recommendations

- Use one EC2 instance for this single-loop architecture.
- Keep `READ_ONLY_MODE=true` for public/read-mostly access.
- Use versioned tags (`ec2-vX`), not `latest`.
- Backup `/opt/autonomous-trader/data` periodically if results matter.
- Move to ECS/Fargate + managed DB when you need horizontal scale.

