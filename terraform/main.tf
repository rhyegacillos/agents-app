provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64*"]
  }
}

locals {
  image_uri        = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com/${var.ecr_repo}:${var.image_tag}"
  env_file_content = join("\n", [for key, value in var.env_vars : "${key}=${value}"])
  use_existing_id  = var.existing_instance_id != ""
  host_port        = var.enable_https ? 8000 : 80
}

data "aws_instances" "by_tag" {
  count = local.use_existing_id ? 0 : 1
  filter {
    name   = "tag:Name"
    values = [var.existing_instance_tag_name]
  }
  filter {
    name   = "instance-state-name"
    values = ["pending", "running", "stopping", "stopped"]
  }
}

locals {
  detected_instance_id = local.use_existing_id ? var.existing_instance_id : (
    length(data.aws_instances.by_tag[0].ids) > 0 ? data.aws_instances.by_tag[0].ids[0] : ""
  )
  use_existing    = local.detected_instance_id != ""
  manage_existing = var.manage_existing && local.use_existing
  existing_sg_id = var.existing_security_group_id != "" ? var.existing_security_group_id : (
    local.use_existing ? tolist(data.aws_instance.existing[0].vpc_security_group_ids)[0] : ""
  )
}

data "aws_instance" "existing" {
  count       = local.use_existing ? 1 : 0
  instance_id = local.detected_instance_id
}

data "aws_route53_zone" "selected" {
  count        = var.route53_zone_id == "" && var.route53_zone_name != "" ? 1 : 0
  name         = var.route53_zone_name
  private_zone = false
}

locals {
  route53_zone_id = var.route53_zone_id != "" ? var.route53_zone_id : (
    var.route53_zone_name != "" ? data.aws_route53_zone.selected[0].zone_id : ""
  )
  ssh_cidr = var.allowed_ssh_cidr != "" ? var.allowed_ssh_cidr : "0.0.0.0/0"
}

resource "aws_security_group" "app" {
  count       = local.use_existing ? 0 : 1
  name        = "${var.project_name}-sg"
  description = "Security group for ${var.project_name}"
  vpc_id      = data.aws_vpc.default.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_route53_record" "app" {
  count   = var.enable_route53_dns && local.route53_zone_id != "" && var.domain_name != "" ? 1 : 0
  zone_id = local.route53_zone_id
  name    = var.domain_name
  type    = "A"
  ttl     = 60
  records = [local.use_existing ? data.aws_instance.existing[0].public_ip : aws_instance.app[0].public_ip]
}

resource "aws_vpc_security_group_ingress_rule" "existing_http" {
  count             = var.manage_existing_sg_rules && local.use_existing && local.existing_sg_id != "" ? 1 : 0
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
  cidr_ipv4         = "0.0.0.0/0"
  security_group_id = local.existing_sg_id
}

resource "aws_vpc_security_group_ingress_rule" "existing_https" {
  count             = var.manage_existing_sg_rules && local.use_existing && local.existing_sg_id != "" ? 1 : 0
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  cidr_ipv4         = "0.0.0.0/0"
  security_group_id = local.existing_sg_id
}

resource "aws_vpc_security_group_ingress_rule" "existing_ssh" {
  count             = var.manage_existing_sg_rules && local.use_existing && local.existing_sg_id != "" ? 1 : 0
  from_port         = 22
  to_port           = 22
  ip_protocol       = "tcp"
  cidr_ipv4         = local.ssh_cidr
  security_group_id = local.existing_sg_id

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "new_http" {
  count             = local.use_existing ? 0 : 1
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
  cidr_ipv4         = "0.0.0.0/0"
  security_group_id = aws_security_group.app[0].id
}

resource "aws_vpc_security_group_ingress_rule" "new_https" {
  count             = local.use_existing ? 0 : 1
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  cidr_ipv4         = "0.0.0.0/0"
  security_group_id = aws_security_group.app[0].id
}

resource "aws_vpc_security_group_ingress_rule" "new_ssh" {
  count             = local.use_existing ? 0 : 1
  from_port         = 22
  to_port           = 22
  ip_protocol       = "tcp"
  cidr_ipv4         = local.ssh_cidr
  security_group_id = aws_security_group.app[0].id

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_iam_role" "ec2_role" {
  count = local.use_existing ? 0 : 1
  name  = "${var.project_name}-ec2-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecr_readonly" {
  count      = local.use_existing ? 0 : 1
  role       = aws_iam_role.ec2_role[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_instance_profile" "ec2_profile" {
  count = local.use_existing ? 0 : 1
  name  = "${var.project_name}-ec2-profile"
  role  = aws_iam_role.ec2_role[0].name
}

resource "aws_instance" "app" {
  count                       = local.manage_existing ? 1 : (local.use_existing ? 0 : 1)
  ami                         = local.use_existing ? data.aws_instance.existing[0].ami : data.aws_ami.al2023.id
  instance_type               = local.use_existing ? data.aws_instance.existing[0].instance_type : var.instance_type
  key_name                    = local.use_existing ? data.aws_instance.existing[0].key_name : var.key_name
  subnet_id                   = local.use_existing ? data.aws_instance.existing[0].subnet_id : element(data.aws_subnets.default.ids, 0)
  vpc_security_group_ids      = local.use_existing ? tolist(data.aws_instance.existing[0].vpc_security_group_ids) : [aws_security_group.app[0].id]
  iam_instance_profile        = local.use_existing ? data.aws_instance.existing[0].iam_instance_profile : aws_iam_instance_profile.ec2_profile[0].name
  associate_public_ip_address = local.use_existing ? data.aws_instance.existing[0].associate_public_ip_address : true

  user_data = local.use_existing ? null : templatefile("${path.module}/userdata.sh.tpl", {
    aws_region       = var.aws_region,
    image_uri        = local.image_uri,
    env_file_content = local.env_file_content,
    project_name     = var.project_name,
    host_port        = local.host_port,
    enable_https     = var.enable_https,
    domain_name      = var.domain_name,
    certbot_email    = var.certbot_email
  })

  tags = {
    Name = "${var.project_name}-app"
  }

  lifecycle {
    ignore_changes  = [user_data, user_data_base64]
    prevent_destroy = true
    precondition {
      condition     = !(local.manage_existing && local.use_existing && var.existing_instance_id == "")
      error_message = "manage_existing=true requires existing_instance_id to be set (auto-detect does not import)."
    }
    precondition {
      condition     = !(var.manage_existing_sg_rules && local.use_existing && local.existing_sg_id == "")
      error_message = "manage_existing_sg_rules=true requires an existing security group ID to be detected."
    }
  }
}
