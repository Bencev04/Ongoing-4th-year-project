# =============================================================================
# Makefile — Local convenience commands for infrastructure management
# =============================================================================
#
# This Makefile provides shortcuts so you don't have to remember long commands.
# All commands are run from your laptop (not CI/CD).
#
# USAGE:
#   make init          — Initialise Terraform (download providers, configure backend)
#   make plan          — Show planned changes without applying
#   make apply         — Apply infrastructure changes (creates/modifies AWS resources)
#   make destroy       — Destroy ALL infrastructure (nuclear option!)
#   make kubeconfig    — Update local kubectl config for the EKS cluster
#   make scale-down    — Scale node group to 0 (keep control plane, save ~$2/day)
#   make scale-up      — Scale node group to 2 nodes
#   make status        — Check if cluster is running and how many nodes
#   make bootstrap     — One-time setup: create S3 state bucket + DynamoDB lock table
#
# PREREQUISITES:
#   - Terraform installed (>= 1.5)
#   - AWS CLI configured (aws configure)
#   - TF_VAR_rds_username and TF_VAR_rds_password set as environment variables
# =============================================================================

# Use bash for all shell commands (not sh)
SHELL := /bin/bash

# Configuration variables — change these if you renamed the project
TF_DIR := terraform                    # Directory containing root Terraform module
REGION := eu-west-1                    # AWS region (must match providers.tf)
CLUSTER := yr4-project-eks             # EKS cluster name (must match terraform.tfvars)
NODE_GROUP := yr4-project-eks-nodes    # Node group name (from EKS module)

# Declare all targets as phony (not real files)
# This tells Make to always run the recipe, even if a file with that name exists.
.PHONY: init plan apply destroy kubeconfig scale-down scale-up status bootstrap fmt validate output lint test scan-trivy policy test-all

# =============================================================================
# Bootstrap — Run this ONCE before anything else
# =============================================================================
# Creates the S3 bucket and DynamoDB table needed for Terraform remote state.
# See bootstrap/main.tf for details on what this creates.

bootstrap:
	cd bootstrap && terraform init && terraform apply

# =============================================================================
# Terraform Commands — Infrastructure as Code workflow
# =============================================================================

# Download providers and configure the S3 backend.
# Must run before plan/apply/destroy.
init:
	cd $(TF_DIR) && terraform init -input=false

# Show what Terraform would create/change/destroy WITHOUT actually doing it.
# "plan" depends on "init" (runs init first).
plan: init
	cd $(TF_DIR) && terraform plan -input=false

# Actually create/modify/destroy AWS resources to match the code.
# Terraform will prompt for confirmation.
apply: init
	cd $(TF_DIR) && terraform apply -input=false

# Destroy ALL infrastructure. Terraform will prompt for confirmation.
# WARNING: This deletes VPC, EKS, RDS, Redis — all data is lost!
destroy: init
	cd $(TF_DIR) && terraform destroy -input=false

# Auto-format all .tf files to follow HashiCorp's style guide.
fmt:
	terraform fmt -recursive .

# Check Terraform configuration for syntax errors.
validate: init
	cd $(TF_DIR) && terraform validate

# Print all Terraform outputs (cluster endpoint, RDS address, etc.).
output:
	cd $(TF_DIR) && terraform output

# =============================================================================
# Cluster Management — Day-to-day operations
# =============================================================================

# Update your local kubectl config to connect to the EKS cluster.
# After this, "kubectl get pods" will talk to the right cluster.
kubeconfig:
	./scripts/setup-kubeconfig.sh $(REGION) $(CLUSTER)

# Check if the cluster is running and report its status.
# Exit code 0 = running, 1 = nodes at 0, 2 = doesn't exist.
status:
	./scripts/ensure-cluster.sh $(REGION) $(CLUSTER) $(NODE_GROUP)

# Scale worker nodes to 0. The EKS control plane stays running (~$2.40/day)
# but no pods can be scheduled. Use this at end of day to save money.
scale-down:
	aws eks update-nodegroup-config \
		--cluster-name $(CLUSTER) \
		--nodegroup-name $(NODE_GROUP) \
		--region $(REGION) \
		--scaling-config desiredSize=0,minSize=0,maxSize=4
	@echo "Node group scaling to 0. EKS control plane still running."

# Scale worker nodes back to 2 and wait for them to be ready.
# This takes ~3-5 minutes as new EC2 instances are launched.
scale-up:
	aws eks update-nodegroup-config \
		--cluster-name $(CLUSTER) \
		--nodegroup-name $(NODE_GROUP) \
		--region $(REGION) \
		--scaling-config desiredSize=2,minSize=0,maxSize=4
	@echo "Node group scaling to 2 nodes..."
	aws eks wait nodegroup-active \
		--cluster-name $(CLUSTER) \
		--nodegroup-name $(NODE_GROUP) \
		--region $(REGION)
	@echo "Nodes are active."

# =============================================================================
# Testing Commands — Run all validation checks locally
# =============================================================================

# Run TFLint with AWS plugin (catches invalid instance types, naming issues)
lint: init
	tflint --init --config .tflint.hcl
	cd $(TF_DIR) && tflint --config ../.tflint.hcl --recursive

# Run native Terraform tests (terraform/tests/*.tftest.hcl)
test: init
	cd $(TF_DIR) && terraform test

# Security scan with Trivy (CIS benchmarks)
scan-trivy:
	trivy config . --severity HIGH,CRITICAL --ignorefile .trivyignore

# OPA/Conftest policy check (custom Rego rules)
policy: init
	cd $(TF_DIR) && terraform plan -out=tfplan.binary -input=false
	cd $(TF_DIR) && terraform show -json tfplan.binary > tfplan.json
	conftest test $(TF_DIR)/tfplan.json --policy policy/

# Run ALL checks (the full testing pyramid, same as CI)
test-all: fmt validate lint scan-trivy test policy
	@echo "All tests passed."
