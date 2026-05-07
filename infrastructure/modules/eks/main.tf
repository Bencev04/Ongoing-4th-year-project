# ============================================================================
# EKS Module - Shared Kubernetes cluster with managed node group
# ============================================================================
#
# This module creates:
#   1. The EKS cluster (managed Kubernetes control plane)
#   2. A security group for the cluster
#   3. An OIDC provider for IRSA (IAM Roles for Service Accounts)
#   4. A managed node group (the EC2 worker instances that run pods)
#   5. Core EKS addons (VPC CNI, CoreDNS, kube-proxy)
#
# WHAT IS EKS?
#   Amazon EKS (Elastic Kubernetes Service) manages the Kubernetes control plane
#   for us - the API server, etcd database, scheduler, and controller manager.
#   We just provide the worker nodes (EC2 instances) via a managed node group.
#
# WHAT IS A MANAGED NODE GROUP?
#   AWS manages the EC2 instances lifecycle: launching, draining during upgrades,
#   and replacing unhealthy nodes. We just specify the instance type and scaling
#   config. Nodes auto-register with the cluster using the node role from the IAM module.
#
# SCALING STRATEGY:
#   min_size = 0 allows us to scale nodes to zero when not demoing (cost saving).
#   The EKS control plane stays alive (~$0.10/hr) but nodes cost nothing at 0.
#   The CD pipeline triggers scale-up automatically before deploying.
# ============================================================================

# =============================================================================
# EKS Cluster - The managed Kubernetes control plane
# =============================================================================
# This creates the Kubernetes API server, etcd, scheduler etc.
# AWS manages all of this - we can't SSH into the control plane.
# Takes ~10 minutes to create on first apply.

# KMS key for encrypting Kubernetes secrets at rest (e.g. ConfigMaps, Secrets)
resource "aws_kms_key" "eks_secrets" {
  description             = "KMS key for EKS secrets encryption - ${var.cluster_name}"
  deletion_window_in_days = 7
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.kms_key_policy.json

  tags = merge(var.tags, {
    Name = "${var.cluster_name}-eks-secrets"
  })
}

# KMS key policy: account root gets full admin, EKS cluster role gets usage permissions
data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "kms_key_policy" {
  # Allow account root full management of the key
  statement {
    sid    = "AllowRootAdmin"
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
    actions   = ["kms:*"]
    resources = ["*"]
  }

  # Allow EKS cluster role to use the key for secrets encryption
  statement {
    sid    = "AllowEKSClusterRole"
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = [var.cluster_role_arn]
    }
    actions = [
      "kms:Encrypt",
      "kms:Decrypt",
      "kms:ReEncrypt*",
      "kms:GenerateDataKey*",
      "kms:DescribeKey",
      "kms:CreateGrant",
    ]
    resources = ["*"]
  }
}

resource "aws_eks_cluster" "main" {
  name                      = var.cluster_name
  version                   = var.kubernetes_version # e.g. "1.31"
  role_arn                  = var.cluster_role_arn   # IAM role from the iam module
  enabled_cluster_log_types = var.enabled_cluster_log_types

  access_config {
    authentication_mode = var.authentication_mode
  }

  # Network configuration - which subnets and security groups the cluster uses
  vpc_config {
    # The cluster needs both public and private subnets:
    #   - Public: for the ALB (internet-facing load balancer)
    #   - Private: for the worker nodes (not directly internet-accessible)
    subnet_ids = concat(var.public_subnet_ids, var.private_subnet_ids)

    # API server endpoint access:
    #   - Private: nodes communicate with the API server within the VPC (faster, no internet)
    #   - Public: we can run kubectl from our laptops (via the internet)
    endpoint_private_access = true # Nodes → API server stays within VPC
    endpoint_public_access  = true # Our laptops → API server via internet

    security_group_ids = [aws_security_group.cluster.id]
  }

  # Encrypt Kubernetes secrets at rest using our KMS key
  encryption_config {
    provider {
      key_arn = aws_kms_key.eks_secrets.arn
    }
    resources = ["secrets"]
  }

  tags = merge(var.tags, {
    Name = var.cluster_name
  })
}

# =============================================================================
# Cluster Security Group - Controls network access to/from the cluster
# =============================================================================
# This security group is attached to the EKS cluster's ENIs (Elastic Network Interfaces).
# The RDS and ElastiCache modules reference this SG to allow inbound connections
# from the cluster (i.e. only pods in this cluster can reach the databases).

resource "aws_security_group" "cluster" {
  name_prefix = "${var.cluster_name}-cluster-"
  vpc_id      = var.vpc_id
  description = "EKS cluster security group - referenced by RDS and Redis SGs"

  tags = merge(var.tags, {
    Name = "${var.cluster_name}-cluster-sg"
  })
}

# Allow all outbound traffic from the cluster (nodes need to reach Docker Hub, ECR, etc.)
resource "aws_security_group_rule" "cluster_egress" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"          # All protocols
  cidr_blocks       = ["0.0.0.0/0"] # All destinations
  security_group_id = aws_security_group.cluster.id
  description       = "Allow all outbound traffic from EKS"
}

# =============================================================================
# OIDC Provider - Enables IRSA (IAM Roles for Service Accounts)
# =============================================================================
# OIDC = OpenID Connect. EKS creates an OIDC identity provider that associates
# Kubernetes service accounts with IAM roles. This is how the ALB controller pod
# gets AWS permissions without giving those permissions to every pod on the node.
#
# The tls_certificate data source fetches the OIDC provider's TLS certificate
# thumbprint, which AWS needs to verify the identity tokens.

data "tls_certificate" "eks" {
  url = aws_eks_cluster.main.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "eks" {
  client_id_list  = ["sts.amazonaws.com"]                                       # Standard audience for IRSA
  thumbprint_list = [data.tls_certificate.eks.certificates[0].sha1_fingerprint] # TLS cert thumbprint
  url             = aws_eks_cluster.main.identity[0].oidc[0].issuer             # EKS OIDC issuer URL

  tags = var.tags
}

# =============================================================================
# Managed Node Group - The EC2 worker instances that actually run our pods
# =============================================================================
# These are the machines where our 12 microservice containers run.
# AWS handles:
#   - Launching instances from the latest EKS-optimised AMI
#   - Registering them with the cluster automatically
#   - Draining pods gracefully during updates
#   - Replacing unhealthy instances
#
# SCALING:
#   desired_size = 2  - normal running state (12 services fit on 2×t3.medium)
#   min_size = 0      - allows scaling to zero when not in use
#   max_size = 4      - ceiling for burst traffic or if we add more services
#
# update_config.max_unavailable = 1 means during a rolling update, only one node
# is taken down at a time (pods are moved to the other node first).

resource "aws_eks_node_group" "main" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.cluster_name}-nodes"
  node_role_arn   = var.node_role_arn      # IAM role from the iam module
  subnet_ids      = var.private_subnet_ids # Nodes go in PRIVATE subnets only

  instance_types = [var.node_instance_type] # e.g. ["t3.medium"] (2 vCPU, 4GB RAM)

  scaling_config {
    desired_size = var.node_desired_size # How many nodes to run right now (default: 2)
    min_size     = var.node_min_size     # Minimum nodes (default: 0 for cost saving)
    max_size     = var.node_max_size     # Maximum nodes (default: 4)
  }

  update_config {
    max_unavailable = 1 # Rolling update: take down 1 node at a time
  }

  labels = {
    role = "general" # Kubernetes label - can be used in nodeSelector if needed
  }

  tags = merge(var.tags, {
    Name = "${var.cluster_name}-nodes"
  })

  depends_on = [aws_eks_cluster.main] # Cluster must exist before adding nodes
}

resource "aws_eks_access_entry" "admin" {
  for_each = var.access_entries

  cluster_name      = aws_eks_cluster.main.name
  principal_arn     = each.value.principal_arn
  kubernetes_groups = each.value.kubernetes_groups
  type              = each.value.type

  depends_on = [aws_eks_cluster.main]
}

resource "aws_eks_access_policy_association" "admin" {
  for_each = var.access_entries

  cluster_name  = aws_eks_cluster.main.name
  principal_arn = aws_eks_access_entry.admin[each.key].principal_arn
  policy_arn    = each.value.policy_arn

  access_scope {
    type       = each.value.access_scope_type
    namespaces = each.value.access_scope_type == "namespace" ? each.value.access_scope_namespaces : null
  }

  depends_on = [aws_eks_access_entry.admin]
}

# =============================================================================
# EKS Addons - Core cluster components managed by AWS
# =============================================================================
# These are Kubernetes system components that AWS manages and updates for us.
# They run as pods on the worker nodes (which is why they depend on the node group).
#
# vpc-cni:    The Amazon VPC CNI plugin - assigns each pod a real VPC IP address.
#             This is how pods can communicate with RDS and Redis directly.
# coredns:    Kubernetes DNS - resolves service names (e.g. "auth-service") to pod IPs.
#             Without this, services can't find each other by name.
# kube-proxy: Network proxy on each node - handles Kubernetes Service routing.
#             Routes traffic from a Service IP to the correct backend pod.

resource "aws_eks_addon" "vpc_cni" {
  cluster_name = aws_eks_cluster.main.name
  addon_name   = "vpc-cni"

  depends_on = [aws_eks_node_group.main] # Needs nodes to schedule the addon pods
}

resource "aws_eks_addon" "coredns" {
  cluster_name = aws_eks_cluster.main.name
  addon_name   = "coredns"

  depends_on = [aws_eks_node_group.main]
}

resource "aws_eks_addon" "kube_proxy" {
  cluster_name = aws_eks_cluster.main.name
  addon_name   = "kube-proxy"

  depends_on = [aws_eks_node_group.main]
}

resource "aws_eks_addon" "ebs_csi" {
  cluster_name             = aws_eks_cluster.main.name
  addon_name               = "aws-ebs-csi-driver"
  service_account_role_arn = var.ebs_csi_driver_role_arn

  depends_on = [aws_eks_node_group.main]
}

resource "aws_eks_addon" "cloudwatch_observability" {
  count = var.enable_cloudwatch_observability ? 1 : 0

  cluster_name  = aws_eks_cluster.main.name
  addon_name    = "amazon-cloudwatch-observability"
  addon_version = var.cloudwatch_observability_addon_version
  configuration_values = jsonencode({
    manager = {
      applicationSignals = {
        autoMonitor = {
          # Keep Container Insights/log collection enabled, but do not mutate every
          # application workload with ADOT auto-instrumentation by default. The
          # injected Python instrumentation overrides PYTHONPATH and broke the
          # services' shared `common` imports in staging.
          monitorAllServices = false
          languages          = []
          restartPods        = false
        }
      }
    }
  })
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"

  tags = merge(var.tags, {
    Name      = "${var.cluster_name}-cloudwatch-observability"
    Component = "observability"
  })

  depends_on = [aws_eks_node_group.main]
}
