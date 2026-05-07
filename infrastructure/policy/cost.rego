# =============================================================================
# OPA/Conftest Policy — Cost Controls
# =============================================================================
#
# This Rego policy prevents accidental deployment of expensive resources.
# For a college project, we need strict cost guardrails:
#   - Only t3 family instances (burstable, cheapest)
#   - Single-AZ resources (no expensive HA configurations)
#   - Limited storage sizes
#
# These policies act as a SAFETY NET — if someone changes terraform.tfvars
# to use m5.xlarge instances, this policy catches it at plan time before
# any money is spent.
# =============================================================================

package main

# Allowed EC2 instance type families (for EKS nodes)
allowed_node_types := {
  "t3.micro",
  "t3.small",
  "t3.medium",
  "t3.large",
}

# Allowed RDS instance classes
allowed_rds_classes := {
  "db.t3.micro",
  "db.t3.small",
  "db.t3.medium",
}

# Allowed ElastiCache node types
allowed_cache_types := {
  "cache.t3.micro",
  "cache.t3.small",
  "cache.t3.medium",
}

# =============================================================================
# DENY: EKS node group with expensive instance types
# =============================================================================
deny[msg] {
  resource := all_resources[_]
  resource.type == "aws_eks_node_group"
  instance_types := resource.values.instance_types
  instance_type := instance_types[_]
  not allowed_node_types[instance_type]
  msg := sprintf(
    "COST: EKS node group '%s' uses '%s' — only t3 family allowed: %v",
    [resource.name, instance_type, allowed_node_types]
  )
}

# =============================================================================
# DENY: RDS with expensive instance class
# =============================================================================
deny[msg] {
  resource := all_resources[_]
  resource.type == "aws_db_instance"
  not allowed_rds_classes[resource.values.instance_class]
  msg := sprintf(
    "COST: RDS instance '%s' uses '%s' — only allowed: %v",
    [resource.name, resource.values.instance_class, allowed_rds_classes]
  )
}

# =============================================================================
# DENY: ElastiCache with expensive node type
# =============================================================================
deny[msg] {
  resource := all_resources[_]
  resource.type == "aws_elasticache_replication_group"
  not allowed_cache_types[resource.values.node_type]
  msg := sprintf(
    "COST: ElastiCache '%s' uses '%s' — only allowed: %v",
    [resource.name, resource.values.node_type, allowed_cache_types]
  )
}

# =============================================================================
# DENY: RDS with excessive storage
# =============================================================================
# More than 50GB of storage is overkill for a college project demo.
deny[msg] {
  resource := all_resources[_]
  resource.type == "aws_db_instance"
  resource.values.allocated_storage > 50
  msg := sprintf(
    "COST: RDS instance '%s' has %dGB storage — max 50GB for college project",
    [resource.name, resource.values.allocated_storage]
  )
}

# =============================================================================
# DENY: Multi-AZ RDS (doubles the cost)
# =============================================================================
deny[msg] {
  resource := all_resources[_]
  resource.type == "aws_db_instance"
  resource.values.multi_az == true
  msg := sprintf(
    "COST: RDS instance '%s' has multi_az = true — this doubles the cost, disable for college project",
    [resource.name]
  )
}
