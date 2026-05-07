# ============================================================================
# IAM Module - Roles for EKS cluster, node group, and IRSA
# ============================================================================
#
# This module creates the IAM roles that allow EKS to function.
# AWS uses IAM (Identity and Access Management) to control what each service
# is allowed to do. Without these roles, EKS can't manage nodes, and nodes
# can't pull container images.
#
# THREE ROLES:
#   1. EKS Cluster Role - the EKS control plane assumes this role to manage
#      the cluster (create ENIs, manage security groups, write logs)
#   2. EKS Node Role - the EC2 worker nodes assume this role to join the
#      cluster, run pods, pull images from ECR, and configure networking
#   3. ALB Controller Role (IRSA) - the AWS Load Balancer Controller pod
#      assumes this role to create/manage Application Load Balancers
#
# WHAT IS IRSA?
#   IAM Roles for Service Accounts. It lets a SPECIFIC Kubernetes pod assume
#   an AWS IAM role, without giving all pods on the node that permission.
#   The pod's ServiceAccount is linked to the IAM role via the OIDC provider.
# ============================================================================

# =============================================================================
# 1. EKS Cluster Role
# =============================================================================
# The EKS service (eks.amazonaws.com) assumes this role to:
#   - Create and manage the Kubernetes control plane
#   - Manage network interfaces in the VPC
#   - Write logs to CloudWatch

# Trust policy: allows the EKS service to assume this role
data "aws_iam_policy_document" "eks_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"] # "I want to act as this role"

    principals {
      type        = "Service"
      identifiers = ["eks.amazonaws.com"] # Only the EKS service can assume this
    }
  }
}

resource "aws_iam_role" "eks_cluster" {
  name               = "${var.project_name}-eks-cluster-role"
  assume_role_policy = data.aws_iam_policy_document.eks_assume_role.json

  tags = var.tags
}

# AmazonEKSClusterPolicy - required, lets EKS manage the cluster
resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  role       = aws_iam_role.eks_cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

# AmazonEKSVPCResourceController - lets EKS manage ENIs for pod networking
resource "aws_iam_role_policy_attachment" "eks_vpc_resource_controller" {
  role       = aws_iam_role.eks_cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSVPCResourceController"
}

# =============================================================================
# 2. EKS Node Group Role
# =============================================================================
# The EC2 instances (worker nodes) assume this role to:
#   - Register themselves with the EKS cluster (WorkerNodePolicy)
#   - Configure VPC networking for pods (CNI_Policy)
#   - Pull container images from ECR public gallery (ECR ReadOnly)
#     Note: our images are on Docker Hub, but EKS addons (CoreDNS etc.) are on ECR

# Trust policy: allows EC2 instances to assume this role
data "aws_iam_policy_document" "node_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"] # Only EC2 instances can assume this
    }
  }
}

resource "aws_iam_role" "eks_nodes" {
  name               = "${var.project_name}-eks-node-role"
  assume_role_policy = data.aws_iam_policy_document.node_assume_role.json

  tags = var.tags
}

# AmazonEKSWorkerNodePolicy - required, lets nodes register with the cluster
resource "aws_iam_role_policy_attachment" "node_worker_policy" {
  role       = aws_iam_role.eks_nodes.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

# AmazonEKS_CNI_Policy - required, lets the VPC CNI plugin assign pod IPs
resource "aws_iam_role_policy_attachment" "node_cni_policy" {
  role       = aws_iam_role.eks_nodes.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

# AmazonEC2ContainerRegistryReadOnly - lets nodes pull EKS addon images from ECR
resource "aws_iam_role_policy_attachment" "node_ecr_read" {
  role       = aws_iam_role.eks_nodes.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# =============================================================================
# 3. IRSA: AWS Load Balancer Controller
# =============================================================================
# This role is assumed by the aws-load-balancer-controller pod (runs in kube-system
# namespace). It uses IRSA (IAM Roles for Service Accounts) so only THIS specific
# pod gets ALB management permissions - not every pod on the node.
#
# HOW IRSA WORKS:
#   1. EKS has an OIDC identity provider (created in the EKS module)
#   2. This trust policy says: "Allow the OIDC provider to assume this role,
#      but ONLY if the request comes from the 'aws-load-balancer-controller'
#      service account in the 'kube-system' namespace"
#   3. The pod gets temporary AWS credentials injected as environment variables
#
# NOTE: oidc_provider_arn and oidc_provider_url come from the EKS module.
# They default to "" so Terraform can create the IAM role and EKS cluster in
# the same apply (the OIDC values are filled in after the cluster is created).

data "aws_iam_policy_document" "alb_controller_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"] # IRSA uses web identity federation

    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn] # The EKS OIDC provider
    }

    # Only allow this SPECIFIC service account to assume the role
    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider_url}:sub"
      values   = ["system:serviceaccount:kube-system:aws-load-balancer-controller"]
    }

    # Audience must be the STS service (standard for IRSA)
    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "alb_controller" {
  name               = "${var.project_name}-alb-controller-role"
  assume_role_policy = data.aws_iam_policy_document.alb_controller_assume.json

  tags = var.tags
}

# ElasticLoadBalancingFullAccess - lets the controller create/manage ALBs and target groups
# In production, you'd use a more restrictive custom policy. Full access is simpler for now.
resource "aws_iam_role_policy_attachment" "alb_controller" {
  role       = aws_iam_role.alb_controller.name
  policy_arn = "arn:aws:iam::aws:policy/ElasticLoadBalancingFullAccess"
}

# =============================================================================
# 4. IRSA: External Secrets Operator (ESO)
# =============================================================================
# This role is assumed by the external-secrets pod. It uses IRSA so only the
# ESO service account gets access to Secrets Manager - not every pod on the node.
#
# WHAT ESO DOES:
#   1. Reads secrets from AWS Secrets Manager
#   2. Creates/updates Kubernetes Secret objects automatically
#   3. Pods reference the K8s Secrets as normal (envFrom, volumes, etc.)
#
# If RDS is destroyed and recreated:
#   1. Terraform apply updates the secret in Secrets Manager
#   2. ESO polls Secrets Manager (default: every 1h, configurable)
#   3. ESO updates the K8s Secret with the new endpoint
#   4. Pods pick up the new value on next restart/rollout

data "aws_iam_policy_document" "eso_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }

    # Only allow the external-secrets service account in the external-secrets namespace
    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider_url}:sub"
      values   = ["system:serviceaccount:external-secrets:external-secrets-sa"]
    }

    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eso" {
  name               = "${var.project_name}-eso-role"
  assume_role_policy = data.aws_iam_policy_document.eso_assume.json

  tags = var.tags
}

# Custom policy: allow reading secrets under the project prefix
# Uses path-based scoping (yr4-project/*) instead of exact ARNs to avoid
# circular dependencies (IAM → Secrets → RDS → EKS → IAM).
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

data "aws_iam_policy_document" "eso_policy" {
  statement {
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
    ]
    resources = [
      "arn:aws:secretsmanager:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:secret:${coalesce(var.secrets_path_prefix, var.project_name)}/*"
    ]
  }
}

resource "aws_iam_policy" "eso" {
  name   = "${var.project_name}-eso-secrets-read"
  policy = data.aws_iam_policy_document.eso_policy.json

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "eso" {
  role       = aws_iam_role.eso.name
  policy_arn = aws_iam_policy.eso.arn
}

# =============================================================================
# 5. IRSA: Fluent Bit CloudWatch Logs Writer
# =============================================================================

data "aws_iam_policy_document" "fluent_bit_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider_url}:sub"
      values   = ["system:serviceaccount:${var.fluent_bit_namespace}:${var.fluent_bit_service_account_name}"]
    }

    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "fluent_bit" {
  name               = "${var.project_name}-fluent-bit-role"
  assume_role_policy = data.aws_iam_policy_document.fluent_bit_assume.json

  tags = var.tags
}

locals {
  fluent_bit_log_group_names = length(var.fluent_bit_log_group_names) > 0 ? var.fluent_bit_log_group_names : [
    "/aws/eks/year4-project/staging/logs",
    "/aws/eks/year4-project/prod/logs",
  ]

  fluent_bit_log_group_arns = flatten([
    for name in local.fluent_bit_log_group_names : [
      "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:${name}",
      "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:${name}:*",
    ]
  ])
}

data "aws_iam_policy_document" "fluent_bit_cloudwatch" {
  statement {
    effect = "Allow"
    actions = [
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:DescribeLogStreams",
      "logs:PutLogEvents",
    ]
    resources = local.fluent_bit_log_group_arns
  }
}

resource "aws_iam_policy" "fluent_bit_cloudwatch" {
  name   = "${var.project_name}-fluent-bit-cloudwatch"
  policy = data.aws_iam_policy_document.fluent_bit_cloudwatch.json

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "fluent_bit_cloudwatch" {
  role       = aws_iam_role.fluent_bit.name
  policy_arn = aws_iam_policy.fluent_bit_cloudwatch.arn
}

# =============================================================================
# 5b. Node permissions: Amazon CloudWatch Observability add-on
# =============================================================================

resource "aws_iam_role_policy_attachment" "node_cloudwatch_agent" {
  count = var.enable_cloudwatch_observability ? 1 : 0

  role       = aws_iam_role.eks_nodes.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

# =============================================================================
# 6. IRSA: AWS EBS CSI Driver
# =============================================================================

data "aws_iam_policy_document" "ebs_csi_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider_url}:sub"
      values   = ["system:serviceaccount:kube-system:${var.ebs_csi_service_account_name}"]
    }

    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ebs_csi_driver" {
  name               = "${var.project_name}-ebs-csi-driver-role"
  assume_role_policy = data.aws_iam_policy_document.ebs_csi_assume.json

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "ebs_csi_driver" {
  role       = aws_iam_role.ebs_csi_driver.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}

# =============================================================================
# 7. IRSA: Loki S3 Object Storage
# =============================================================================

data "aws_iam_policy_document" "loki_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider_url}:sub"
      values   = ["system:serviceaccount:${var.loki_namespace}:${var.loki_service_account_name}"]
    }

    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "loki" {
  name               = "${var.project_name}-loki-role"
  assume_role_policy = data.aws_iam_policy_document.loki_assume.json

  tags = var.tags
}

data "aws_iam_policy_document" "loki_s3" {
  count = length(var.loki_s3_bucket_arns) > 0 ? 1 : 0

  statement {
    effect = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation",
    ]
    resources = var.loki_s3_bucket_arns
  }

  statement {
    effect = "Allow"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:DeleteObject",
      "s3:GetObject",
      "s3:ListMultipartUploadParts",
      "s3:PutObject",
    ]
    resources = [for bucket_arn in var.loki_s3_bucket_arns : "${bucket_arn}/*"]
  }

  dynamic "statement" {
    for_each = length(var.loki_kms_key_arns) > 0 ? [1] : []

    content {
      effect = "Allow"
      actions = [
        "kms:Decrypt",
        "kms:DescribeKey",
        "kms:Encrypt",
        "kms:GenerateDataKey",
        "kms:ReEncrypt*",
      ]
      resources = var.loki_kms_key_arns
    }
  }
}

resource "aws_iam_policy" "loki_s3" {
  count = length(var.loki_s3_bucket_arns) > 0 ? 1 : 0

  name   = "${var.project_name}-loki-s3"
  policy = data.aws_iam_policy_document.loki_s3[0].json

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "loki_s3" {
  count = length(var.loki_s3_bucket_arns) > 0 ? 1 : 0

  role       = aws_iam_role.loki.name
  policy_arn = aws_iam_policy.loki_s3[0].arn
}
