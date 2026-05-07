package main

runtime_environments := {"staging", "production", "prod"}

required_staging_alarm_resources := {
  "rds_cpu_high",
  "rds_storage_low",
  "rds_connections_high",
  "redis_cpu_high",
  "redis_memory_high",
  "redis_evictions",
  "app_error_logs_high",
}

resource_environment(resource) = environment {
  tags := object.get(resource.values, "tags", {})
  environment := object.get(tags, "Environment", "")
}

is_runtime_resource(resource) {
  runtime_environments[resource_environment(resource)]
}

resource_exists(resource_type, resource_name) {
  resource := all_resources[_]
  resource.type == resource_type
  resource.name == resource_name
}

staging_environment_present {
  resource := all_resources[_]
  resource.type == "aws_eks_cluster"
  resource_environment(resource) == "staging"
}

loki_bucket_present {
  resource := all_resources[_]
  resource.type == "aws_s3_bucket"
  tags := object.get(resource.values, "tags", {})
  object.get(tags, "Service", "") == "loki"
}

loki_bucket_encryption_present {
  resource := all_resources[_]
  resource.type == "aws_s3_bucket_server_side_encryption_configuration"
  resource.name == "loki"
}

finite_retention(retention) {
  is_number(retention)
  retention > 0
}

finite_retention(retention) {
  is_string(retention)
  to_number(retention) > 0
}

deny[msg] {
  resource := all_resources[_]
  resource.type == "aws_eks_cluster"
  is_runtime_resource(resource)
  enabled_logs := object.get(resource.values, "enabled_cluster_log_types", [])
  count(enabled_logs) == 0
  msg := sprintf(
    "OBSERVABILITY: EKS cluster '%s' must enable control-plane logs for runtime environments",
    [resource.name]
  )
}

deny[msg] {
  resource := all_resources[_]
  resource.type == "aws_cloudwatch_log_group"
  is_runtime_resource(resource)
  retention := object.get(resource.values, "retention_in_days", null)
  not finite_retention(retention)
  msg := sprintf(
    "OBSERVABILITY: CloudWatch log group '%s' must have finite retention_in_days",
    [resource.name]
  )
}

deny[msg] {
  loki_bucket_present
  not loki_bucket_encryption_present
  msg := "OBSERVABILITY: Loki S3 bucket must have server-side encryption configuration"
}

deny[msg] {
  staging_environment_present
  required_alarm := required_staging_alarm_resources[_]
  not resource_exists("aws_cloudwatch_metric_alarm", required_alarm)
  msg := sprintf(
    "OBSERVABILITY: staging must define CloudWatch alarm resource '%s'",
    [required_alarm]
  )
}
