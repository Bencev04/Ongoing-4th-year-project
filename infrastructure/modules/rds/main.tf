# ============================================================================
# RDS Module - PostgreSQL instance (shared, separate DBs per environment)
# ============================================================================
#
# This module creates a single Amazon RDS PostgreSQL instance that both staging
# and production use. Each environment gets its own DATABASE within the instance:
#   - crm_calendar_staging  (used by the staging K8s namespace)
#   - crm_calendar_prod     (used by the prod K8s namespace)
#
# WHY A SINGLE INSTANCE?
#   Two RDS instances would double the cost. Since staging and prod don't run
#   simultaneously at high load (it's a college demo), sharing is fine.
#   Each environment gets its own database with separate tables and data.
#
# SECURITY:
#   - The RDS instance is in PRIVATE subnets (not accessible from the internet)
#   - A security group only allows connections from the EKS cluster's security group
#   - Storage is encrypted at rest (AES-256)
#   - The username/password are set via TF_VAR environment variables (never in code)
# ============================================================================

# =============================================================================
# Subnet Group - Tells RDS which subnets it can launch in
# =============================================================================
# RDS requires a subnet group with at least 2 subnets in different AZs
# (even for single-AZ deployments). This is an AWS requirement.

resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnet"
  subnet_ids = var.private_subnet_ids # Both private subnets (AZ-a and AZ-b)

  tags = merge(var.tags, {
    Name = "${var.project_name}-db-subnet"
  })
}

# =============================================================================
# Security Group - Firewall rules for the RDS instance
# =============================================================================
# Only allows inbound connections on port 5432 (PostgreSQL) from the EKS cluster.
# This means ONLY pods running in our EKS cluster can reach the database.
# Nothing from the internet or other AWS services can connect.

resource "aws_security_group" "rds" {
  name_prefix = "${var.project_name}-rds-"
  vpc_id      = var.vpc_id
  description = "Allow PostgreSQL access from EKS nodes only"

  tags = merge(var.tags, {
    Name = "${var.project_name}-rds-sg"
  })
}

# Inbound: allow PostgreSQL (5432) from EKS cluster security group
resource "aws_security_group_rule" "rds_ingress" {
  type                     = "ingress"
  from_port                = 5432 # PostgreSQL port
  to_port                  = 5432
  protocol                 = "tcp"
  source_security_group_id = var.eks_security_group_id # Only from EKS!
  security_group_id        = aws_security_group.rds.id
  description              = "PostgreSQL access from EKS cluster pods"
}

# Outbound: allow all (RDS may need to reach AWS internal services)
resource "aws_security_group_rule" "rds_egress" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1" # All protocols
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.rds.id
  description       = "Allow all outbound (needed for AWS internal communication)"
}

# =============================================================================
# RDS Instance - The actual PostgreSQL database server
# =============================================================================
# This is the managed PostgreSQL instance where all application data is stored.
# AWS handles: backups, patching, monitoring, and host maintenance.
#
# KEY SETTINGS:
#   - db.t3.micro: 2 vCPU, 1GB RAM - smallest instance, sufficient for our workload
#   - 20 GB storage: minimum, auto-expandable if needed
#   - storage_encrypted: data at rest is encrypted with AES-256
#   - skip_final_snapshot: don't create a snapshot when destroying (saves time/cost)
#   - multi_az = false: single AZ (no failover replica) - saves ~50% cost
#   - publicly_accessible = false: can't be reached from the internet
#   - deletion_protection = false: allows terraform destroy to work

resource "aws_db_instance" "main" {
  identifier = "${var.project_name}-postgres"

  engine              = "postgres"
  engine_version      = var.engine_version    # Default: "15"
  instance_class      = var.instance_class    # Default: "db.t3.micro"
  allocated_storage   = var.allocated_storage # Default: 20 GB
  storage_encrypted   = true                  # Encrypt data at rest
  skip_final_snapshot = true                  # Don't create snapshot on destroy

  db_name  = var.db_name     # Default database created on launch ("crm_calendar")
  username = var.db_username # Master username (from TF_VAR_rds_username)
  password = var.db_password # Master password (from TF_VAR_rds_password)

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  multi_az                   = false # Single AZ - no automatic failover (saves cost)
  publicly_accessible        = false # NOT reachable from the internet
  auto_minor_version_upgrade = true  # Auto-apply minor Postgres patches
  deletion_protection        = false # Allow terraform destroy to remove this

  tags = merge(var.tags, {
    Name = "${var.project_name}-postgres"
  })
}
