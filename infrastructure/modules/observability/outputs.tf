output "loki_bucket_name" {
  description = "S3 bucket name used by Loki for object storage."
  value       = aws_s3_bucket.loki.bucket
}

output "loki_bucket_arn" {
  description = "S3 bucket ARN used by Loki for object storage."
  value       = aws_s3_bucket.loki.arn
}

output "loki_kms_key_arn" {
  description = "KMS key ARN used for Loki object storage encryption, or an empty string when AES256 is used."
  value       = var.create_loki_kms_key ? aws_kms_key.loki[0].arn : ""
}

output "loki_region" {
  description = "AWS region where Loki object storage is created."
  value       = data.aws_region.current.name
}
