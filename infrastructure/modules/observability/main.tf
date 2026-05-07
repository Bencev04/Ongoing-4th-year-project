data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

locals {
  loki_bucket_name = var.loki_bucket_name != "" ? var.loki_bucket_name : "${var.project_name}-${var.environment}-loki-${data.aws_caller_identity.current.account_id}"

  loki_tags = merge(var.tags, {
    Component = "observability"
    Service   = "loki"
  })
}

resource "aws_kms_key" "loki" {
  count = var.create_loki_kms_key ? 1 : 0

  description             = "KMS key for ${var.project_name} ${var.environment} Loki object storage"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = local.loki_tags
}

resource "aws_kms_alias" "loki" {
  count = var.create_loki_kms_key ? 1 : 0

  name          = "alias/${var.project_name}-${var.environment}-loki"
  target_key_id = aws_kms_key.loki[0].key_id
}

resource "aws_s3_bucket" "loki" {
  bucket        = local.loki_bucket_name
  force_destroy = var.loki_bucket_force_destroy

  tags = local.loki_tags
}

resource "aws_s3_bucket_public_access_block" "loki" {
  bucket = aws_s3_bucket.loki.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "loki" {
  bucket = aws_s3_bucket.loki.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "loki" {
  bucket = aws_s3_bucket.loki.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "loki" {
  bucket = aws_s3_bucket.loki.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = var.create_loki_kms_key ? aws_kms_key.loki[0].arn : null
      sse_algorithm     = var.create_loki_kms_key ? "aws:kms" : "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "loki" {
  bucket = aws_s3_bucket.loki.id

  rule {
    id     = "expire-loki-objects"
    status = "Enabled"

    filter {
      prefix = ""
    }

    expiration {
      days = var.loki_retention_days
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}
