# =============================================================================
# OPA/Conftest Policy — Tagging Requirements
# =============================================================================
#
# This Rego policy ensures all AWS resources have required tags.
# Tags are critical for:
#   - Cost allocation (who owns this resource?)
#   - Environment identification (staging vs production)
#   - Automation (scripts can filter by tag)
#   - Compliance (auditors want to know who manages what)
#
# REQUIRED TAGS:
#   - Project: identifies which project the resource belongs to
#   - ManagedBy: should always be "terraform" (not manually created)
#   - Environment: which environment (shared, staging, production)
# =============================================================================

package main

# The tags every resource must have
required_tags := {"Project", "ManagedBy", "Environment"}

# Resource types that should have tags (AWS resources that support tagging)
taggable_types := {
  "aws_vpc",
  "aws_subnet",
  "aws_internet_gateway",
  "aws_nat_gateway",
  "aws_eip",
  "aws_route_table",
  "aws_eks_cluster",
  "aws_eks_node_group",
  "aws_db_instance",
  "aws_db_subnet_group",
  "aws_elasticache_replication_group",
  "aws_elasticache_subnet_group",
  "aws_security_group",
  "aws_iam_role",
  "aws_s3_bucket",
  "aws_kms_key",
  "aws_sns_topic",
  "aws_cloudwatch_log_group",
  "aws_cloudwatch_metric_alarm",
}

# =============================================================================
# DENY: Taggable resource missing required tags
# =============================================================================
deny[msg] {
  resource := all_resources[_]
  taggable_types[resource.type]

  # Get the tags (or empty object if no tags)
  tags := object.get(resource.values, "tags", {})

  # Check each required tag
  required_tag := required_tags[_]
  not tags[required_tag]

  msg := sprintf(
    "TAGGING: Resource '%s' (type: %s) is missing required tag '%s'",
    [resource.name, resource.type, required_tag]
  )
}
