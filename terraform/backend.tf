terraform {
  backend "s3" {
    # Configured at runtime by scripts/deploy.sh or scripts/destroy.sh.
  }
}
