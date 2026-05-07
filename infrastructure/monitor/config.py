# ─── Project-specific resource names ──────────────────────────────────────────
# Edit these if your Terraform naming convention changes.

REGION = "eu-west-1"
PROJECT = "yr4-project"
REFRESH_SECONDS = 10

# Terraform bootstrap resources (shared across all environments)
BOOTSTRAP_CONFIG = {
    "s3_bucket":      "yr4-project-tf-state",
    "dynamodb_table": "yr4-project-terraform-locks",
}

# Microservices deployed to the cluster (matches CD pipeline SERVICES list)
DEPLOYMENTS = [
    "nginx-gateway",
    "auth-service",
    "user-bl-service",
    "user-db-access-service",
    "job-bl-service-deployment",
    "job-db-access-service-deployment",
    "customer-bl-service",
    "customer-db-access-service",
    "admin-bl-service",
    "maps-access-service",
    "notification-service",
    "frontend-deployment",
]

ENV_CONFIG: dict[str, dict] = {
    "staging": {
        "eks_cluster": "yr4-project-staging-eks",
        "node_group":  "yr4-project-staging-eks-nodes",
        "rds_id":      "yr4-project-staging-postgres",
        "redis_id":    "yr4-project-staging-redis",
        "vpc_tag":     "yr4-project-staging",
        "namespace":   "year4-project-staging",
        "iam_roles": [
            "yr4-project-staging-eks-cluster-role",
            "yr4-project-staging-eks-node-role",
            "yr4-project-staging-eso-role",
        ],
        "secrets": [
            "yr4-project/staging/db-credentials",
            "yr4-project/staging/redis-credentials",
            "yr4-project/staging/app-secrets",
            "yr4-project/staging/api-keys",
        ],
        "eks_addons": ["vpc-cni", "coredns", "kube-proxy"],
    },
    "production": {
        "eks_cluster": "yr4-project-production-eks",
        "node_group":  "yr4-project-production-eks-nodes",
        "rds_id":      "yr4-project-production-postgres",
        "redis_id":    "yr4-project-production-redis",
        "vpc_tag":     "yr4-project-production",
        "namespace":   "year4-project",
        "iam_roles": [
            "yr4-project-production-eks-cluster-role",
            "yr4-project-production-eks-node-role",
            "yr4-project-production-eso-role",
        ],
        "secrets": [
            "yr4-project/prod/db-credentials",
            "yr4-project/prod/redis-credentials",
            "yr4-project/prod/app-secrets",
            "yr4-project/prod/api-keys",
        ],
        "eks_addons": ["vpc-cni", "coredns", "kube-proxy"],
    },
}
