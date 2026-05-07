#!/usr/bin/env bash
# =============================================================================
# setup-kubeconfig.sh — Configure kubectl for the EKS cluster
# =============================================================================
#
# This script updates your local ~/.kube/config so that kubectl can talk to
# the EKS cluster. It also tests the connection and lists namespaces.
#
# USAGE:
#   ./scripts/setup-kubeconfig.sh [region] [cluster-name]
#   ./scripts/setup-kubeconfig.sh                          # Uses defaults
#   ./scripts/setup-kubeconfig.sh eu-west-1 yr4-project-eks
#
# PREREQUISITES:
#   - AWS CLI configured with valid credentials (aws configure)
#   - kubectl installed
#   - The EKS cluster must exist and be ACTIVE
# =============================================================================
set -euo pipefail  # Exit on error, undefined vars, and pipe failures

# Default values if no arguments provided
REGION="${1:-eu-west-1}"              # First arg or default to Ireland
CLUSTER_NAME="${2:-yr4-project-eks}"  # Second arg or default cluster name

# Update kubeconfig — this adds the EKS cluster to your kubectl config.
# --alias gives the context a friendly name instead of the full ARN.
echo "Updating kubeconfig for cluster: $CLUSTER_NAME in $REGION..."
aws eks update-kubeconfig \
  --region "$REGION" \
  --name "$CLUSTER_NAME" \
  --alias "$CLUSTER_NAME"

# Quick smoke test — if this fails, your credentials or cluster config is wrong
echo "Testing connection..."
kubectl cluster-info

echo ""
echo "Kubeconfig updated. Current context: $CLUSTER_NAME"
echo "Namespaces:"
kubectl get namespaces
