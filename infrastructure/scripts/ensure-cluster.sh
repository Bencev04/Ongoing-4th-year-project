#!/usr/bin/env bash
# =============================================================================
# ensure-cluster.sh — Check if the EKS cluster is running, report status
# =============================================================================
#
# This script is used by the CD pipeline (deployment repo) to decide whether
# it needs to trigger the infrastructure pipeline before deploying.
#
# It checks three things in order:
#   1. Does the EKS cluster EXIST?
#   2. Is the cluster in ACTIVE status?
#   3. Are there running worker NODES?
#
# EXIT CODES (used by the CD pipeline to decide what to do):
#   0 = Cluster is up and has running nodes → safe to deploy
#   1 = Cluster exists but nodes are at 0   → needs scale-up (ENSURE_UP=true)
#   2 = Cluster does not exist              → needs full terraform apply
#
# USAGE:
#   ./scripts/ensure-cluster.sh [region] [cluster-name] [node-group-name]
#   ./scripts/ensure-cluster.sh                          # Uses all defaults
#
# PREREQUISITES:
#   - AWS CLI configured with valid credentials
# =============================================================================
set -euo pipefail  # Exit on error, undefined vars, and pipe failures

# Default values if no arguments provided
REGION="${1:-eu-west-1}"                         # AWS region
CLUSTER_NAME="${2:-yr4-project-eks}"              # EKS cluster name
NODE_GROUP_NAME="${3:-yr4-project-eks-nodes}"     # Managed node group name

echo "Checking EKS cluster: $CLUSTER_NAME in $REGION..."

# --- Step 1: Does the cluster exist? -----------------------------------------
# aws eks describe-cluster fails with non-zero if the cluster doesn't exist.
# &>/dev/null suppresses both stdout and stderr.
if ! aws eks describe-cluster --name "$CLUSTER_NAME" --region "$REGION" &>/dev/null; then
  echo "STATUS: CLUSTER_NOT_FOUND"
  echo "Cluster does not exist. Trigger infra pipeline with full apply."
  exit 2  # → CD pipeline should trigger infra pipeline with terraform apply
fi

# --- Step 2: Is the cluster ACTIVE? ------------------------------------------
# The cluster could exist but be in "CREATING", "UPDATING", or "FAILED" state.
CLUSTER_STATUS=$(aws eks describe-cluster \
  --name "$CLUSTER_NAME" \
  --region "$REGION" \
  --query 'cluster.status' \
  --output text)

echo "Cluster status: $CLUSTER_STATUS"

if [ "$CLUSTER_STATUS" != "ACTIVE" ]; then
  echo "STATUS: CLUSTER_NOT_ACTIVE"
  echo "Cluster exists but is not ACTIVE (status: $CLUSTER_STATUS)."
  exit 2  # → Treat as "doesn't exist" for the CD pipeline's purposes
fi

# --- Step 3: Are there running worker nodes? ---------------------------------
# Check how many nodes the node group is configured to run.
# If desiredSize is 0, the cluster is technically running but can't run any pods.
DESIRED=$(aws eks describe-nodegroup \
  --cluster-name "$CLUSTER_NAME" \
  --nodegroup-name "$NODE_GROUP_NAME" \
  --region "$REGION" \
  --query 'nodegroup.scalingConfig.desiredSize' \
  --output text 2>/dev/null || echo "0")

if [ "$DESIRED" = "0" ] || [ "$DESIRED" = "None" ]; then
  echo "STATUS: NODES_SCALED_DOWN"
  echo "Cluster is active but node group has 0 desired nodes."
  echo "Trigger infra pipeline with ENSURE_UP=true to scale up."
  exit 1  # → CD pipeline should trigger infra pipeline with ENSURE_UP=true
fi

# --- All good! ---------------------------------------------------------------
echo "STATUS: RUNNING"
echo "Cluster is active with $DESIRED node(s). Ready for ArgoCD sync."
exit 0  # → CD pipeline can proceed with deployment
