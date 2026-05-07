# ============================================================================
# ElastiCache Module - Redis (shared, different DB numbers per environment)
# ============================================================================
#
# This module creates a single Amazon ElastiCache Redis instance that both
# staging and production use. Each environment uses different Redis DB numbers:
#   - Staging: DB 0-5 (one per service that needs Redis)
#   - Production: DB 6-11 (or separate range)
# This matches the local docker-compose setup where each service has its own DB number.
#
# WHY REDIS?
#   The CRM Calendar app uses Redis for:
#     - Session storage (auth-service stores JWT sessions)
#     - Caching (frequently accessed data like job listings)
#     - Pub/Sub (real-time notifications between services)
#
# WHY A SINGLE INSTANCE?
#   Same reasoning as RDS - two ElastiCache instances doubles the cost.
#   Redis DB numbers provide logical separation within one instance.
#
# SECURITY:
#   - Redis is in PRIVATE subnets (no internet access)
#   - Security group only allows connections from EKS cluster
#   - At-rest encryption enabled (data on disk is encrypted)
#   - Transit encryption disabled (to avoid TLS overhead for in-VPC traffic)
# ============================================================================

# =============================================================================
# Subnet Group - Tells ElastiCache which subnets it can launch in
# =============================================================================

resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.project_name}-redis-subnet"
  subnet_ids = var.private_subnet_ids # Both private subnets

  tags = merge(var.tags, {
    Name = "${var.project_name}-redis-subnet"
  })
}

# =============================================================================
# Security Group - Firewall rules for the Redis instance
# =============================================================================
# Same pattern as RDS: only allow connections from EKS cluster on the Redis port.

resource "aws_security_group" "redis" {
  name_prefix = "${var.project_name}-redis-"
  vpc_id      = var.vpc_id
  description = "Allow Redis access from EKS nodes only"

  tags = merge(var.tags, {
    Name = "${var.project_name}-redis-sg"
  })
}

# Inbound: allow Redis (6379) from EKS cluster security group
resource "aws_security_group_rule" "redis_ingress" {
  type                     = "ingress"
  from_port                = 6379 # Redis port
  to_port                  = 6379
  protocol                 = "tcp"
  source_security_group_id = var.eks_security_group_id # Only from EKS!
  security_group_id        = aws_security_group.redis.id
  description              = "Redis access from EKS cluster pods"
}

# Outbound: allow all
resource "aws_security_group_rule" "redis_egress" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.redis.id
  description       = "Allow all outbound"
}

# =============================================================================
# ElastiCache Redis Replication Group
# =============================================================================
# A "replication group" is ElastiCache's term for a Redis cluster. Even with
# a single node (num_cache_clusters = 1), it must be a replication group.
#
# KEY SETTINGS:
#   - cache.t3.micro: 2 vCPU, 0.5GB RAM - smallest instance, sufficient for our use
#   - num_cache_clusters = 1: single node, no replicas (saves cost)
#   - at_rest_encryption_enabled: data encrypted on disk
#   - transit_encryption_enabled = false: no TLS for connections (simpler, faster;
#     traffic is already within the private VPC so not exposed)
#   - automatic_failover_enabled = false: requires 2+ nodes, which we don't have
#   - parameter_group_name: uses the default Redis 7 parameter group

# Custom parameter group (TFLint flags default groups as non-editable)
resource "aws_elasticache_parameter_group" "redis7" {
  name   = "${var.project_name}-redis7"
  family = "redis7"

  tags = var.tags
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "${var.project_name}-redis"
  description          = "Redis cache/session store for ${var.project_name}"

  engine             = "redis"
  engine_version     = var.engine_version # Default: "7.0"
  node_type          = var.node_type      # Default: "cache.t3.micro"
  num_cache_clusters = 1                  # Single node (no replicas)
  port               = 6379               # Standard Redis port

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]

  at_rest_encryption_enabled = true  # Encrypt data on disk
  transit_encryption_enabled = false # No TLS (internal VPC traffic only)
  automatic_failover_enabled = false # Requires 2+ nodes - we only have 1

  parameter_group_name = aws_elasticache_parameter_group.redis7.name

  tags = merge(var.tags, {
    Name = "${var.project_name}-redis"
  })
}
