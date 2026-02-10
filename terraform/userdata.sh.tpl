#!/bin/bash
set -euo pipefail

dnf -y update
dnf -y install docker
systemctl enable --now docker
usermod -aG docker ec2-user

mkdir -p /opt/${project_name}/data
chown -R ec2-user:ec2-user /opt/${project_name}

cat <<'EOF' > /home/ec2-user/autonomous-trader.env
${env_file_content}
EOF

chown ec2-user:ec2-user /home/ec2-user/autonomous-trader.env
chmod 600 /home/ec2-user/autonomous-trader.env

aws ecr get-login-password --region ${aws_region} \
  | docker login --username AWS --password-stdin ${image_uri%/*}

docker pull ${image_uri}

if docker ps -a --format '{{.Names}}' | grep -q '^${project_name}$'; then
  docker stop ${project_name} || true
  docker rm ${project_name} || true
fi

docker run -d --name ${project_name} \
  -p ${host_port}:8000 \
  --env-file /home/ec2-user/autonomous-trader.env \
  -v /opt/${project_name}/data:/app/api/data \
  --restart unless-stopped \
  ${image_uri}

if [[ "${enable_https}" == "true" && -n "${domain_name}" && -n "${certbot_email}" && "${certbot_email}" != "REPLACE_ME" ]]; then
  dnf -y install nginx certbot python3-certbot-nginx
  systemctl enable --now nginx

  cat > /etc/nginx/conf.d/${project_name}.conf <<EOF
server {
  server_name ${domain_name};

  location / {
    proxy_pass http://localhost:8000;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
  }
}
EOF

  nginx -t && systemctl reload nginx
  certbot --nginx -d ${domain_name} --non-interactive --agree-tos -m ${certbot_email}
  systemctl enable --now certbot-renew.timer || true
fi
