# CRM Calendar — Public Project Mirror

This repository is a public GitHub mirror of my ongoing 4th-year college project. The active development, CI/CD, deployment, and infrastructure workflows run on DKIT's internal GitLab instance; this GitHub repository exists so the project can be reviewed publicly from a CV/portfolio link.

## Repository layout

```text
development/      Application source code and development CI pipeline
deployment/       Kubernetes, Helm, Kustomize, and deployment pipeline code
infrastructure/   Terraform AWS infrastructure, monitoring, and policy code
```

## Project summary

CRM Calendar is a containerised multi-service CRM/workflow platform for service businesses. The platform uses FastAPI microservices, PostgreSQL, Redis, an NGINX gateway, Docker Compose for local development, Kubernetes for deployment, and Terraform-managed AWS infrastructure.

## What this mirror demonstrates

- Multi-service backend and frontend architecture using FastAPI, PostgreSQL, Redis, and NGINX.
- Dockerised local development and integration testing workflows.
- GitLab CI/CD pipelines for linting, tests, security scanning, image builds, image promotion, and downstream deployment triggering.
- Kubernetes deployment automation using Kustomize and Helm.
- Terraform infrastructure-as-code for AWS EKS, VPC, RDS PostgreSQL, ElastiCache Redis, IAM, S3 state, and DynamoDB state locking.
- Staging deployment reliability checks including preflight validation, readiness gates, smoke tests, migration execution, and staging teardown verification.
- Observability components including Prometheus, Grafana, Loki, Fluent Bit, CloudWatch, kube-state-metrics, and node-exporter.

## Folder guide

### development/

Application and CI source repository. Includes service code, Dockerfiles, tests, shared libraries, Docker Compose files, and the main development GitLab pipeline.

### deployment/

Deployment automation repository. Includes Kubernetes manifests, Kustomize overlays, Helm values, deployment scripts, local validation scripts, and GitLab deployment pipeline definitions.

### infrastructure/

Infrastructure repository. Includes Terraform modules/environments, AWS infrastructure definitions, policy checks, monitoring scripts, and infrastructure pipeline definitions.

## Public mirror sanitisation

This mirror intentionally excludes files that should not be published publicly, including:

- Terraform state files
- local Terraform variable files
- `.env` files
- kubeconfig files
- private keys/certificates
- generated Python cache files
- local Kubernetes Secret manifests

Example Terraform variable files are included where useful, but real deployment values are not published.

## Status

Ongoing final-year project, February 2026 to present.

Team project: Bence Veres and Tadgh Brady.
