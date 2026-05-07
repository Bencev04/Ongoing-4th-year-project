# YR4 - Project Infrastructure Repository

Terraform infrastructure-as-code for the CRM Calendar platform on AWS EKS.

---

## Table of Contents

- [Purpose](#purpose)
- [Design Decisions & Rationale](#design-decisions--rationale)
- [The Three-Repo Architecture](#the-three-repo-architecture)
- [AWS Architecture](#aws-architecture)
- [Repository Structure](#repository-structure)
- [Getting Started](#getting-started)
- [Infra Pipeline](#infra-pipeline)
- [Testing & Validation](#testing--validation)
- [CD Repo Integration](#cd-repo-integration)
- [Operational Runbook](#operational-runbook)
- [Cost Breakdown](#cost-breakdown)
- [CI/CD Variables Required](#cicd-variables-required)
- [How to Go Forward](#how-to-go-forward)

---

## Purpose

This repository contains all the Terraform code needed to provision and manage the AWS infrastructure that the CRM Calendar microservices platform runs on. It is the **foundation layer** — without it, there is nowhere for the Kubernetes workloads to run.

The infra repo is responsible for:
- Creating and managing the **AWS Virtual Private Cloud (VPC)** — the isolated network where everything lives
- Provisioning the **Amazon EKS cluster** — the managed Kubernetes control plane and worker nodes
- Setting up **Amazon RDS PostgreSQL** — the managed relational database
- Setting up **Amazon ElastiCache Redis** — the managed in-memory cache/session store
- Managing **IAM roles and policies** — secure access between AWS services
- Providing **scale-up/scale-down/destroy** capabilities — so we only pay for what we use

It is **not** responsible for deploying application workloads (that's the CD repo) or building container images (that's the Dev repo).

---

## Design Decisions & Rationale

### Why Three Separate Repositories?

This follows the **GitOps** model. Each repo has a single, clear responsibility:

1. **Dev repo** = "What does the application look like?" (Code, tests, Dockerfiles)
2. **Deployment repo** = "How should it be deployed?" (K8s manifests, Helm charts, ArgoCD)
3. **Infra repo** = "Where does it run?" (AWS resources via Terraform)

**Why not put everything in one repo?**
- **Separation of concerns** — infrastructure changes (e.g. upgrading Kubernetes version) don't touch application code and vice versa. Each repo can evolve independently with its own merge reviews.
- **Security** — the infra repo needs AWS IAM credentials. The dev repo needs Docker Hub credentials. The CD repo needs ArgoCD tokens. Keeping them separate means each repo only has the secrets it needs.
- **Pipeline isolation** — a typo in a Python file shouldn't accidentally trigger an infrastructure change. A Terraform change shouldn't rebuild all Docker images.
- **Team workflow** — developers working on features only need to touch the dev repo. Infrastructure changes go through the infra repo with their own review process.
- **Industry standard** — this is how GitOps is practiced at companies using ArgoCD/FluxCD. The deployment repo is the "source of truth" for what's deployed, the infra repo is the source of truth for where it runs.

### Why AWS EKS?

We need Kubernetes because:
- The application is already designed as **12 microservices** with Docker containers
- The deployment repo already has **Kubernetes manifests, Helm charts, and Kustomize overlays**
- We need **canary deployments** via Argo Rollouts (which requires Kubernetes)
- We need **namespace-based environment separation** (staging vs prod in one cluster)

We chose **Amazon EKS (Elastic Kubernetes Service)** specifically because:
- **Managed control plane** — AWS handles Kubernetes master nodes, etcd, API server upgrades, and HA. We don't need to manage any of that.
- **Managed node groups** — AWS handles EC2 instance lifecycle, AMI updates, and draining nodes during upgrades.
- **Native AWS integration** — IAM Roles for Service Accounts (IRSA) lets Kubernetes pods securely access RDS and Redis without hardcoding credentials.
- **ALB Ingress Controller** — the AWS Load Balancer Controller can automatically provision Application Load Balancers from Kubernetes Ingress resources.
- **Cost control** — node groups can scale to 0 workers, meaning we only pay for the control plane (~$0.10/hr) when idle.

**Alternatives considered:**
| Option | Why we didn't choose it |
|--------|------------------------|
| **Self-managed K8s on EC2** | Too much operational overhead — managing etcd, control plane upgrades, certificate rotation |
| **AWS ECS/Fargate** | No native support for Argo Rollouts canary strategy. Would need to rewrite all K8s manifests as ECS task definitions. |
| **DigitalOcean/Linode K8s** | Cheaper control plane, but less mature IAM integration and no native managed PostgreSQL/Redis that matches our RDS/ElastiCache needs. |
| **GKE (Google)** | Excellent K8s support, but the rest of the project is already oriented toward AWS tooling. |

### Why Separate Clusters Per Environment?

Staging and production each get their **own EKS cluster**, with independent VPCs, RDS instances, ElastiCache, and IAM roles.

**Rationale:**
- **True isolation** — a staging misconfiguration (e.g. resource quota, RBAC change, CRD update) cannot affect production. No shared blast radius.
- **Independent lifecycle** — staging can be fully destroyed after validation without touching production. Production can be kept running independently.
- **CD workflow** — the deployment pipeline spins up staging, validates, then spins up production and tears down staging. This makes the cost pattern predictable: you only pay for both clusters during the short promotion window.
- **Separate Terraform state** — `terraform destroy` on staging cannot accidentally touch production resources. Each environment has its own state file in S3.
- **VPC separation** — staging uses `10.0.0.0/16`, production uses `10.1.0.0/16`. No overlap, and VPCs can be peered if needed in future.

**Cost impact:**
- Two EKS control planes at $0.10/hr each = ~$146/month if both run 24/7.
- In practice, staging only runs during deployments (~15-30 min per cycle), so the real cost increase is minimal.
- The CD pipeline automatically tears down staging after production is validated.

**Configuration:**
- `terraform/environments/staging/` — staging cluster with `t3.medium` × 2 nodes, `db.t3.micro` RDS, `cache.t3.micro` Redis
- `terraform/environments/production/` — production cluster with `t3.medium` × 3 nodes, `db.t3.small` RDS, `cache.t3.micro` Redis

### Why Managed RDS + ElastiCache (Not Pods)?

The databases run as **AWS managed services**, not as Pods inside Kubernetes.

**Rationale:**
- **Data persistence** — if a Kubernetes node dies, pods restart. If PostgreSQL was running as a pod, the data could be lost (unless using StatefulSets with EBS volumes, which adds complexity). RDS handles replication, backups, and failover automatically.
- **Automated backups** — RDS takes daily snapshots and supports point-in-time recovery. We'd have to configure this manually with PostgreSQL in a pod.
- **Performance** — RDS runs on dedicated compute, not competing with application pods for CPU/memory.
- **Security** — RDS and ElastiCache are in private subnets, accessible only from within the VPC. Security groups restrict access to only the EKS cluster.
- **Operational simplicity** — no need to manage PostgreSQL upgrades, Redis memory tuning, or storage provisioning inside Kubernetes.

**Shared instance, per-environment databases:**
Rather than two separate RDS instances ($$), we use one instance with:
- `crm_calendar_staging` database for the staging namespace
- `crm_calendar_prod` database for the production namespace

Same for Redis — one ElastiCache instance, staging and prod use different DB numbers (0-5 per environment), matching the local docker-compose setup.

### Why Terraform?

**Terraform** is the industry-standard tool for infrastructure-as-code on AWS.

- **Declarative** — we describe the desired state, Terraform figures out what to create/update/destroy.
- **State management** — Terraform tracks what resources exist in a state file (stored in S3 with DynamoDB locking), so it knows the difference between "create new" and "update existing".
- **Modular** — we've structured the code into reusable modules (vpc, eks, rds, elasticache, iam) that compose together in the root module.
- **Plan before apply** — `terraform plan` shows exactly what will change before anything is touched. This is critical for infrastructure — you don't want to accidentally delete a database.
- **GitLab CI integration** — the HashiCorp Terraform Docker image runs natively in GitLab CI jobs.

**Alternatives considered:**
| Option | Why we didn't choose it |
|--------|------------------------|
| **AWS CloudFormation** | AWS-only, verbose JSON/YAML, slower rollbacks, no plan equivalent |
| **Pulumi** | Richer language support (Python/TypeScript), but smaller community and less CI tooling |
| **AWS CDK** | Compiles to CloudFormation — same limitations, extra abstraction layer |
| **Manual console clicks** | Not reproducible, not version-controlled, not auditable |

### Why Remote State in S3 + DynamoDB?

Terraform must store its state file somewhere. Options:
- **Local file** — works for one person, breaks with teams. If two people apply simultaneously, the state corrupts.
- **Terraform Cloud** — managed service, but adds another account/dependency and has usage limits.
- **S3 + DynamoDB** — the standard AWS approach. S3 stores the state file with versioning and encryption. DynamoDB provides a lock so two pipelines can't apply simultaneously.

We create the state backend in the `bootstrap/` directory as a one-time manual step (chicken-and-egg: Terraform needs a backend before it can manage resources, so the backend itself is bootstrapped separately).

### Why the Modular Structure?

```
modules/
├── vpc/           # Can be reused for other projects
├── eks/           # Cluster config independent of networking
├── rds/           # Database independent of cluster
├── elasticache/   # Cache independent of database
└── iam/           # Security independent of all above
```

Each module is:
- **Self-contained** — has its own `variables.tf` (inputs), `main.tf` (resources), and `outputs.tf` (outputs)
- **Reusable** — could be dropped into another project with different variable values
- **Independently testable** — can run `terraform validate` on any module in isolation
- **Clearly scoped** — when something breaks with Redis, you look at `modules/elasticache/`, not a 500-line monolith

The `terraform/` directory is the **root module** that wires everything together, passing outputs from one module as inputs to another (e.g. VPC subnet IDs → EKS, EKS security group → RDS).

### Separate Terraform State Per Environment

Each environment has its own Terraform state file in S3:
- Staging: `s3://yr4-project-terraform-state/staging/terraform.tfstate`
- Production: `s3://yr4-project-terraform-state/production/terraform.tfstate`

This means `terraform destroy` in the staging directory only affects staging resources. Production is completely isolated with its own state, preventing accidental cross-environment damage.

The `terraform/environments/staging/` and `terraform/environments/production/` directories each contain their own `backend.tf`, `providers.tf`, `variables.tf`, `main.tf`, `outputs.tf`, and `terraform.tfvars` — calling the shared modules in `modules/` with environment-specific values.

---

## The Three-Repo Architecture

This project is split across three GitLab repositories, each with a distinct responsibility:

| Repository | Purpose | Pipeline |
|------------|---------|----------|
| **yr4-projectdevelopmentrepo** (Dev) | Application source code, Dockerfiles, unit/integration tests | CI — lint, test, build, push images to Docker Hub |
| **yr4-projectdeploymentrepo** (CD) | Kubernetes manifests, Helm charts, Kustomize overlays, ArgoCD config | CD — validate manifests, deploy staging, test, promote to prod |
| **yr4-projectinfrarepo** (Infra — this repo) | Terraform modules for AWS infrastructure (VPC, EKS, RDS, Redis) | Infra — provision/destroy cloud resources, scale cluster up/down |

### How They Interact

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                         COMPLETE PIPELINE FLOW                                   │
│                                                                                  │
│  ┌─────────────────────────────────────────────────┐                             │
│  │           DEV REPO (CI Pipeline)                │                             │
│  │                                                 │                             │
│  │  Push → Lint (Ruff) → Test (×8 services, 80%   │                             │
│  │  coverage) → Security (Bandit) → Integration    │                             │
│  │  Tests → Build & Push to Docker Hub             │                             │
│  │                                                 │                             │
│  │  Images: bencev04/4th-year-proj-tadgh-bence:    │                             │
│  │          {service}-{short-sha}                   │                             │
│  │          {service}-latest                        │                             │
│  └──────────────────┬──────────────────────────────┘                             │
│                     │                                                            │
│                     │ Manual trigger (webhook with IMAGE_TAG,                    │
│                     │ IMAGE_VERSION, SOURCE_COMMIT)                              │
│                     ▼                                                            │
│  ┌──────────────────────────────────────────────────────────────┐                │
│  │            CD REPO (Deployment Pipeline)                     │                │
│  │                                                              │                │
│  │  1. Validate manifests (kubeconform + helm template)         │                │
│  │                                                              │                │
│  │  2. Ensure infrastructure is up ──trigger──┐                 │                │
│  │     (cross-project trigger)                │                 │                │
│  │                                            ▼                 │                │
│  │                              ┌──────────────────────────┐    │                │
│  │                              │  INFRA REPO (this repo)  │    │                │
│  │                              │                          │    │                │
│  │                              │  ensure-cluster-up:      │    │                │
│  │                              │  ├─ Cluster + nodes up?  │    │                │
│  │                              │  │  → exit 0 (instant)   │    │                │
│  │                              │  ├─ Nodes scaled to 0?   │    │                │
│  │                              │  │  → scale nodes up     │    │                │
│  │                              │  └─ No cluster at all?   │    │                │
│  │                              │     → terraform apply    │    │                │
│  │                              └──────────┬───────────────┘    │                │
│  │                                         │                    │                │
│  │     CD pipeline waits (strategy:depend) │                    │                │
│  │     ◄───────────────────────────────────┘                    │                │
│  │                                                              │                │
│  │  3. Update staging image tag in kustomization.yaml           │                │
│  │  4. ArgoCD syncs staging namespace                           │                │
│  │     └─ Canary: 10% → 50% → 100% (fast)                     │                │
│  │  5. Run staging tests (parallel):                            │                │
│  │     ├─ Smoke tests (hard gate) — /health on all services    │                │
│  │     ├─ Playwright E2E (soft gate)                            │                │
│  │     └─ k6 load tests (soft gate)                             │                │
│  │  6. Manual gate: Promote to production                       │                │
│  │  7. Update prod image tag in kustomization.yaml              │                │
│  │  8. ArgoCD syncs prod namespace                              │                │
│  │     └─ Canary: 10% → 30% → 60% → 100% (conservative)      │                │
│  │     └─ Auto-rollback on 5xx > 5% or pod restarts > 2       │                │
│  │  9. Production smoke tests                                   │                │
│  └──────────────────────────────────────────────────────────────┘                │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Repo Interaction Summary

| Trigger | From → To | Mechanism | When |
|---------|-----------|-----------|------|
| **Build complete** | Dev → CD | GitLab webhook (`curl --form`) with image tag + SHA | Manual gate after CI passes |
| **Need infra up** | CD → Infra | Cross-project trigger with `ENSURE_UP=true` | Before every staging/prod deploy |
| **Infra ready** | Infra → CD | `strategy: depend` (CD waits for infra job to finish) | After cluster confirmed running |
| **Deploy app** | CD → ArgoCD | ArgoCD watches CD repo, auto-syncs on kustomization.yaml change | After image tag updated |
| **Scale down** | Manual | Infra pipeline `scale-down` job or `make scale-down` | After demo/testing complete |

### What Each Repo Owns

```
DEV REPO owns:                    CD REPO owns:                    INFRA REPO owns:
─────────────                     ────────────                     ────────────────
✓ Application code                ✓ K8s manifests (base)           ✓ VPC + subnets
✓ Dockerfiles                     ✓ Kustomize overlays             ✓ EKS cluster + node group
✓ Unit tests                      ✓ Helm charts + values           ✓ RDS PostgreSQL
✓ Integration tests               ✓ ArgoCD app definitions         ✓ ElastiCache Redis
✓ Docker image builds             ✓ CD pipeline (.gitlab-ci.yml)   ✓ IAM roles + IRSA
✓ CI pipeline (.gitlab-ci.yml)    ✓ Staging/prod test suites       ✓ Infra pipeline (.gitlab-ci.yml)
✓ Shared Python libraries         ✓ Image tag management           ✓ Scale up/down scripts
✓ docker-compose (local dev)      ✓ Canary rollout config          ✓ Terraform state management
```

---

## AWS Architecture

**Separate EKS clusters per environment** — staging and production each have their own VPC, EKS cluster, RDS, ElastiCache, and IAM roles. Dev environment is local only (docker-compose).

### Staging Environment
| Resource | Service | Details |
|----------|---------|--------|
| **VPC** | Networking | CIDR `10.0.0.0/16`, 2-AZ, public + private subnets, single NAT gateway |
| **EKS** | Kubernetes | Cluster `yr4-project-staging-eks` (1.29), managed node group (t3.medium), 0-3 nodes |
| **RDS** | PostgreSQL 15 | `db.t3.micro`, database `crm_calendar_staging` |
| **ElastiCache** | Redis 7 | `cache.t3.micro`, single node |
| **IAM** | Access control | Cluster role, node role, IRSA for ALB controller |

### Production Environment
| Resource | Service | Details |
|----------|---------|--------|
| **VPC** | Networking | CIDR `10.1.0.0/16`, 2-AZ, public + private subnets, single NAT gateway |
| **EKS** | Kubernetes | Cluster `yr4-project-production-eks` (1.29), managed node group (t3.medium), 0-5 nodes |
| **RDS** | PostgreSQL 15 | `db.t3.small`, database `crm_calendar_prod` |
| **ElastiCache** | Redis 7 | `cache.t3.micro`, single node |
| **IAM** | Access control | Cluster role, node role, IRSA for ALB controller |

### Shared Resources
| Resource | Service | Details |
|----------|---------|--------|
| **S3 + DynamoDB** | Terraform state | Remote state backend with locking (shared bucket, separate keys per env) |

### Network Layout

```
Staging VPC 10.0.0.0/16                    Production VPC 10.1.0.0/16
├── Public Subnets (10.0.0.0/24, ...)      ├── Public Subnets (10.1.0.0/24, ...)
│   ├── Internet Gateway                  │   ├── Internet Gateway
│   ├── NAT Gateway                       │   ├── NAT Gateway
│   └── ALB (staging traffic)              │   └── ALB (production traffic)
└── Private Subnets (10.0.10.0/24, ...)    └── Private Subnets (10.1.10.0/24, ...)
    ├── EKS Staging Nodes (t3.medium)          ├── EKS Production Nodes (t3.medium)
    ├── RDS PostgreSQL (staging)               ├── RDS PostgreSQL (production)
    └── ElastiCache Redis (staging)            └── ElastiCache Redis (production)
```

---

## Repository Structure

```
├── .gitlab-ci.yml          # Infrastructure pipeline (per-environment jobs)
├── .gitignore              # Terraform state, secrets, IDE files
├── .tflint.hcl             # TFLint config (AWS plugin + rules)
├── .trivyignore            # Trivy suppression file (known acceptable findings)
├── Makefile                # Local convenience commands
├── README.md               # This file
├── bootstrap/              # One-time setup: S3 state bucket + DynamoDB lock table
│   ├── main.tf
│   └── variables.tf
├── modules/                # Reusable Terraform modules (shared by both environments)
│   ├── vpc/                #   VPC, subnets, NAT, route tables
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── eks/                #   EKS cluster, node group, OIDC, addons
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── rds/                #   PostgreSQL RDS instance
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── elasticache/        #   Redis ElastiCache
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   └── iam/                #   IAM roles + IRSA
│       ├── main.tf
│       ├── variables.tf
│       └── outputs.tf
├── policy/                 # OPA/Conftest Rego policies (policy-as-code)
│   ├── encryption.rego     #   All storage must be encrypted
│   ├── network.rego        #   Databases must be VPC-only, no open SSH
│   ├── tagging.rego        #   All resources must have required tags
│   └── cost.rego           #   Only t3 instances, no expensive configs
├── terraform/              # Root module (legacy single-cluster) + per-environment configs
│   ├── main.tf             # Root module composition (legacy)
│   ├── variables.tf        # All input variables
│   ├── outputs.tf          # Cluster/RDS/Redis endpoints
│   ├── terraform.tfvars    # Default values (non-sensitive)
│   ├── backend.tf          # S3 remote state config
│   ├── providers.tf        # AWS provider + default tags
│   ├── tests/              # Native Terraform tests (terraform test)
│   │   ├── variables.tftest.hcl   # Variable defaults + constraints
│   │   └── security.tftest.hcl    # Security + module wiring assertions
│   └── environments/       # Per-environment Terraform configs (Option C)
│       ├── staging/        #   Staging cluster (yr4-project-staging-eks)
│       │   ├── backend.tf
│       │   ├── providers.tf
│       │   ├── variables.tf
│       │   ├── main.tf
│       │   ├── outputs.tf
│       │   └── terraform.tfvars
│       └── production/     #   Production cluster (yr4-project-production-eks)
│           ├── backend.tf
│           ├── providers.tf
│           ├── variables.tf
│           ├── main.tf
│           ├── outputs.tf
│           └── terraform.tfvars
└── scripts/
    ├── setup-kubeconfig.sh # Generate local kubeconfig for EKS
    └── ensure-cluster.sh   # Check if cluster is up (used by CD pipeline)
```

---

## Getting Started

### Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.5
- [AWS CLI](https://aws.amazon.com/cli/) v2 configured with credentials
- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- `make` (optional, for convenience commands)

### 1. Bootstrap State Backend (one-time)

```bash
cd bootstrap
terraform init
terraform apply
```

Creates the S3 bucket (`yr4-project-terraform-state`) and DynamoDB table (`yr4-project-terraform-locks`) for remote state.

### 2. Deploy Infrastructure

```bash
make init       # terraform init
make plan       # review the plan
make apply      # create VPC + EKS + RDS + Redis + IAM
```

### 3. Connect to the Cluster

```bash
make kubeconfig               # updates ~/.kube/config
kubectl get nodes              # verify nodes are running
kubectl get namespaces         # should see default, kube-system, etc.
```

After this, the CD repo's ArgoCD can deploy workloads into `staging` and `prod` namespaces.

---

## Infra Pipeline

### On Merge Request (per environment)
```
fmt-check ──────┐
validate ───────┤
tflint ─────────┤─→ plan-staging ─→ plan-safety-staging
trivy (SARIF) ──┤   plan-production ─→ plan-safety-production
tf-test ────────┤
policy-check ───┘
```

### On Merge to Main (per environment)
```
fmt-check ──────┐
validate ───────┤
tflint ─────────┤─→ plan-staging ──→ plan-safety-staging ──→ apply-staging (manual)
trivy (SARIF) ──┤   plan-production → plan-safety-production → apply-production (manual)
tf-test ────────┤
policy-check ───┘
```

### Cross-Project Trigger (from CD repo)
When the CD pipeline needs a cluster running, it triggers this repo with `ENSURE_UP=true` and `TARGET_ENV=staging` or `TARGET_ENV=production`:

```
ensure-cluster-up:
  TARGET_ENV=staging:
    ├─ Staging cluster exists + nodes running?    → exit 0 (instant)
    ├─ Staging cluster exists + nodes at 0?       → scale up to 2 nodes
    └─ Staging cluster doesn't exist?             → terraform apply (ensure-apply)

  TARGET_ENV=production:
    ├─ Production cluster exists + nodes running? → exit 0 (instant)
    ├─ Production cluster exists + nodes at 0?    → scale up to 3 nodes
    └─ Production cluster doesn't exist?          → terraform apply (ensure-apply)
```

### Manual Jobs (per environment)
| Job | Environment | Purpose | When to use |
|-----|-------------|---------|-------------|
| `scale-up-staging` | Staging | Scale staging nodes to 2 | Before a deployment or demo |
| `scale-down-staging` | Staging | Scale staging nodes to 0 | After staging validation |
| `scale-up-production` | Production | Scale production nodes to 3 | Before a production deploy |
| `scale-down-production` | Production | Scale production nodes to 0 | After demo, keep control plane alive |
| `destroy-staging` | Staging | Tear down ALL staging infrastructure | Zero staging cost needed |
| `destroy-production` | Production | Tear down ALL production infrastructure | End of sprint, zero cost needed |

---

## Testing & Validation

Our infrastructure pipeline implements **seven layers of testing**, each catching different types of issues. All tests run in the `validate` stage on every merge request — no AWS resources are created.

### Testing Pyramid

```
┌─────────────────────────────────────────────────────────────────────────┐
│ LAYER          │ TOOL              │ WHAT IT CATCHES                    │
├────────────────┼───────────────────┼────────────────────────────────────┤
│ Formatting     │ terraform fmt     │ Code style (tabs, spacing)         │
│ Syntax         │ terraform validate│ Invalid HCL, missing variables     │
│ Linting        │ TFLint + AWS      │ Invalid instance types, deprecated │
│ Security       │ Trivy (SARIF)     │ CIS benchmark → GitLab Dashboard   │
│ Unit Tests     │ terraform test    │ Variable constraints, module wiring│
│ Policy-as-Code │ OPA/Conftest      │ Custom Rego (cost, tags, access)   │
│ Safety Gate    │ Plan analysis     │ Warns on destructive changes       │
└────────────────┴───────────────────┴────────────────────────────────────┘
```

### Running Tests Locally

```bash
# Run the full testing pyramid in one command:
make test-all

# Or run individual layers:
make fmt              # Code formatting
make validate         # Syntax check
make lint             # TFLint with AWS plugin
make scan-trivy       # Trivy security scan
make test             # Native terraform test
make policy           # OPA/Conftest policy check
```

### Advanced Pipeline Features

| Feature | What It Does | Why It Matters |
|---------|--------------|----------------|
| **GitLab Security Dashboard** | Trivy outputs SARIF format → GitLab Security tab | Visual security overview in every MR |
| **Plan Safety Analysis** | Scans plan for destructive changes | Blocks apply if database/cache would be destroyed (data loss prevention) |

### Configuration Files

| File | Purpose |
|------|---------|
| `.tflint.hcl` | TFLint config — AWS plugin v0.31.0, naming rules, documentation rules |
| `.trivyignore` | Trivy suppressions — known acceptable findings with documented rationale |
| `terraform/tests/*.tftest.hcl` | Native Terraform tests — variable, security, and wiring assertions |
| `policy/*.rego` | OPA/Conftest Rego policies — encryption, network, tagging, cost rules |

### Why So Many Testing Tools?

Each tool catches a different class of issue — there is minimal overlap:

| Tool | Catches | Example |
|------|---------|---------|
| **terraform validate** | Syntax errors, missing variables | Typo in variable name |
| **TFLint** | Provider-specific issues | Invalid instance type `t3.nonexistent` |
| **Trivy** | CIS benchmark violations | RDS without encryption |
| **Terraform Test** | Logic/wiring errors | Module output not connected |
| **OPA/Conftest** | Custom project rules | Accidentally using m5.xlarge |
| **Plan Safety** | Destructive changes | Accidental database drop |

---

## CD Repo Integration

The deployment repo pipeline manages the full staging→production lifecycle with separate clusters.
Before each deploy, it **dynamically triggers this infra repo** to ensure the target cluster is up:

```
validate → update-tags
  → trigger-infra-staging → wait-staging-ready → deploy-staging → staging-tests
    → promote (manual)
      → trigger-infra-production → wait-production-ready → deploy-prod → prod-validation
        → teardown-staging → notify
```

**Key stages:**
1. `trigger-infra-staging` — cross-project trigger to this infra repo with `ENSURE_UP=true`, `TARGET_ENV=staging`. Uses `strategy: depend` so the CD pipeline waits for the infra pipeline to complete.
2. `wait-staging-ready` — AWS CLI readiness check confirming nodes are active after the infra pipeline finishes.
3. `deploy-staging` — ArgoCD syncs to staging cluster.
4. `staging-tests` — smoke tests, Playwright E2E, k6 load tests.
5. `promote` (manual gate) — updates production image tags.
6. `trigger-infra-production` — same cross-project trigger with `TARGET_ENV=production`.
7. `wait-production-ready` — readiness check for production cluster.
8. `deploy-prod` — ArgoCD syncs to production cluster (conservative canary).
9. `teardown-staging` — scales staging nodes to 0 after successful production deploy.

**How the cross-project trigger works:**

```yaml
# In yr4-projectdeploymentrepo/.gitlab-ci.yml — staging example
trigger-infra-staging:
  stage: ensure-staging
  trigger:
    project: finalproject/Prototypes/yr4-projectinfrarepo
    strategy: depend          # CD pipeline WAITS for infra pipeline to finish
  variables:
    ENSURE_UP: "true"
    TARGET_ENV: "staging"     # or "production" for the production trigger

wait-staging-ready:
  stage: ensure-staging
  needs:
    - trigger-infra-staging   # runs only after infra pipeline succeeds
  script:
    - aws eks describe-cluster --name $STAGING_CLUSTER_NAME ...
    - aws eks describe-nodegroup ... --query 'nodegroup.scalingConfig.desiredSize'
    # Confirms cluster exists and nodes > 0 before deploy begins
```

**What happens in the infra repo when triggered:**
1. `ensure-cluster-up` — checks if the cluster exists and has nodes scaled up. If nodes are at 0, scales them up. If cluster doesn't exist, exits with failure.
2. `ensure-apply` (on_failure fallback) — if `ensure-cluster-up` fails, runs `terraform apply` in `terraform/environments/$TARGET_ENV/` to create the full stack from scratch.

**Required CI/CD variables (set in the CD repo's GitLab settings):**

| Variable | Description |
|---|---|
| `INFRA_PROJECT_ID` | GitLab project ID of this infra repo |
| `INFRA_TRIGGER_TOKEN` | Pipeline trigger token (create in infra repo → Settings → CI/CD → Pipeline trigger tokens) |
| `GITLAB_API_TOKEN` | GitLab API token with `api` scope (for cross-project access) |

---

## Operational Runbook

This section provides step-by-step instructions for every common operational task.

### First-Time Setup (from scratch)

This assumes you have an AWS account, AWS CLI configured, and Terraform installed.

**Step 1 — Create the IAM user for Terraform:**
1. Log into AWS Console → IAM → Users → Create User
2. Name: `terraform-ci` (or similar)
3. Attach policies: `AdministratorAccess` (for initial setup; can scope down later)
4. Create access key → copy `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
5. Run `aws configure` locally with these credentials

**Step 2 — Bootstrap the state backend:**
```bash
cd bootstrap
terraform init
terraform apply -auto-approve
```
This creates:
- S3 bucket `yr4-project-terraform-state` — stores the Terraform state file (with versioning + encryption)
- DynamoDB table `yr4-project-terraform-locks` — prevents two people from applying simultaneously

You only do this once, ever. If the bucket already exists, this step is a no-op.

**Step 3 — Deploy all infrastructure:**
```bash
# Deploy staging environment
cd terraform/environments/staging
terraform init
terraform plan
terraform apply

# Deploy production environment
cd ../production
terraform init
terraform plan
terraform apply
```
Or using the Makefile from the repo root:
```bash
make init-staging
make plan-staging
make apply-staging

make init-production
make plan-production
make apply-production
```

This creates (in order, per environment):
1. VPC with public/private subnets across 2 availability zones
2. Internet Gateway + NAT Gateway for outbound traffic
3. IAM roles for EKS cluster, node group, and ALB controller
4. EKS cluster (control plane) — takes ~10 minutes
5. Managed node group (t3.medium instances) — takes ~5 minutes
6. RDS PostgreSQL instance in private subnets — takes ~5 minutes
7. ElastiCache Redis instance in private subnets — takes ~5 minutes

Total first-time provision per environment: ~15-20 minutes.

**Step 4 — Connect kubectl to the clusters:**
```bash
# Staging
aws eks update-kubeconfig --region eu-west-1 --name yr4-project-staging-eks --alias staging
kubectl --context staging get nodes

# Production
aws eks update-kubeconfig --region eu-west-1 --name yr4-project-production-eks --alias production
kubectl --context production get nodes
```

**Step 5 — Create the Kubernetes namespaces:**
```bash
# Staging cluster
kubectl --context staging create namespace year4-project-staging
kubectl --context staging create namespace argocd

# Production cluster
kubectl --context production create namespace year4-project
kubectl --context production create namespace argocd
```

**Step 6 — Install ArgoCD into the cluster:**
```bash
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
# Get the initial admin password:
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```

**Step 7 — Create Kubernetes secrets for database/Redis access:**
The RDS and Redis endpoints are in the per-environment Terraform outputs:
```bash
cd terraform/environments/staging
terraform output rds_endpoint      # e.g. yr4-project-staging-db.xxxx.eu-west-1.rds.amazonaws.com:5432
terraform output redis_endpoint    # e.g. yr4-project-staging-redis.xxxx.cache.amazonaws.com

cd ../production
terraform output rds_endpoint      # e.g. yr4-project-production-db.xxxx.eu-west-1.rds.amazonaws.com:5432
terraform output redis_endpoint    # e.g. yr4-project-production-redis.xxxx.cache.amazonaws.com
```
Create secrets in each cluster:
```bash
# Staging cluster
kubectl --context staging -n year4-project-staging create secret generic db-credentials \
  --from-literal=host=<staging-rds-endpoint> \
  --from-literal=username=<rds-username> \
  --from-literal=password=<rds-password> \
  --from-literal=database=crm_calendar_staging

# Production cluster
kubectl --context production -n year4-project create secret generic db-credentials \
  --from-literal=host=<production-rds-endpoint> \
  --from-literal=username=<rds-username> \
  --from-literal=password=<rds-password> \
  --from-literal=database=crm_calendar_prod
```

**Step 8 — Configure GitLab CI/CD variables:**
In all three GitLab repos, add the necessary CI/CD variables (see [CI/CD Variables Required](#cicd-variables-required)).

After these 8 steps, the platform is fully operational. Push code to the dev repo, the CI/CD pipeline handles the rest.

---

### Daily Demo Workflow

When you need to show the project to a supervisor or examiner:

**If cluster was scaled down (nodes at 0):**
```bash
make scale-up           # Takes ~5 min for nodes to join cluster
make kubeconfig         # Refresh kubeconfig just in case
kubectl get nodes       # Wait for nodes to show "Ready"
kubectl get pods -n staging   # Pods should start scheduling automatically
```

**If cluster was fully destroyed:**
```bash
make init
make apply              # Full provision, ~15-20 min
make kubeconfig
# Then recreate namespaces and secrets (Step 5-7 above)
```

**If cluster is already running:**
Nothing to do. Just deploy via the CD pipeline.

**After the demo:**
```bash
make scale-down         # Keeps control plane alive, nodes to 0 → saves ~$0.18/hr
# OR
make destroy            # Tears everything down → $0/hr (but ~20 min to rebuild)
```

---

### After-Hours Scale Down

When you're done for the day and don't want to leave the cluster running:

```bash
make scale-down
```

This sets the node group `min_size` and `desired_capacity` to 0. The EKS control plane stays alive (~$0.10/hr = ~$2.40/day), but worker nodes are terminated (~$0.18/hr saved).

**Why not destroy every night?**
- `make scale-down` → `make scale-up` takes ~5 minutes (nodes rejoin existing cluster)
- `make destroy` → `make apply` takes ~20 minutes (full infrastructure recreation)
- If you destroy, you also need to recreate namespaces, secrets, and reinstall ArgoCD

Scale-down is the sweet spot for "I'll be back tomorrow."

---

### End-of-Sprint Teardown

When you won't need the cluster for a while (e.g. over a holiday):

```bash
make destroy
```

This destroys **everything** — VPC, EKS, RDS, Redis, NAT gateway, all of it. Monthly cost drops to $0.

**What you'll need to redo when you rebuild:**
- `make apply` (full provision)
- Recreate namespaces (`kubectl create namespace staging`, `kubectl create namespace prod`, `kubectl create namespace argocd`)
- Reinstall ArgoCD
- Recreate Kubernetes secrets for database/Redis credentials
- Point ArgoCD at the CD repo again

The Terraform state in S3 is **not** destroyed by `make destroy` — it still exists and tracks that resources were deleted. The next `make apply` will create everything fresh.

---

### Troubleshooting

**"Nodes not joining the cluster after scale-up"**
```bash
kubectl get nodes                           # Check node status
# For staging:
aws eks describe-nodegroup --cluster-name yr4-project-staging-eks --nodegroup-name yr4-project-staging-eks-nodes
# For production:
aws eks describe-nodegroup --cluster-name yr4-project-production-eks --nodegroup-name yr4-project-production-eks-nodes
```
If nodes are stuck in `CREATE_IN_PROGRESS`, wait 5 minutes. If they fail, check the EC2 console for the Auto Scaling Group events.

**"Terraform plan shows changes I didn't expect"**
```bash
terraform plan -out=plan.out    # Save plan to file
terraform show plan.out         # Review in detail
```
Never run `terraform apply` without reviewing the plan first. If you see `destroy` on a resource you don't expect, **stop** and investigate.

**"State lock error"**
```
Error: Error locking state: Error acquiring the state lock
```
This means someone (or a CI job) is currently applying. Check GitLab pipelines. If the lock is stale (job crashed), manually release it:
```bash
terraform force-unlock <LOCK_ID>
```

**"RDS connection refused from pods"**
Check security groups — the RDS security group should allow ingress from the EKS node security group on port 5432. Verify:
```bash
aws ec2 describe-security-groups --filters "Name=group-name,Values=*rds*"
```

**"kubectl: The connection to the server was refused"**
The cluster might be destroyed or your kubeconfig is stale:
```bash
make kubeconfig                 # Regenerate
kubectl cluster-info            # Test connection
```

---

## Cost Breakdown

### Hourly Cost When Running

**Per environment (staging OR production):**
| Resource | Hourly Cost | Notes |
|----------|-------------|-------|
| EKS control plane | $0.10/hr | Always running while cluster exists |
| t3.medium nodes | $0.0832/hr each | Staging: ×2, Production: ×3 |
| NAT Gateway | ~$0.045/hr | + $0.045/GB data processed |
| RDS (staging: db.t3.micro) | ~$0.018/hr | Single-AZ |
| RDS (production: db.t3.small) | ~$0.036/hr | Single-AZ |
| ElastiCache cache.t3.micro | ~$0.017/hr | Single-node |

**Combined totals:**
| Scenario | Hourly Cost |
|----------|-------------|
| **Both environments running** | ~$0.70/hr |
| **Only production running** | ~$0.45/hr |
| **Only staging running** | ~$0.35/hr |
| **Both control planes alive, nodes at 0** | ~$0.29/hr |
| **Everything destroyed** | $0.00/hr |

### Scenario Estimates

| Scenario | Monthly Cost |
|----------|-------------|
| CD pipeline workflow (staging up ~30min per deploy, 3×/week) | ~$8/month |
| Production running 4hrs/day, staging transient | ~$55/month (prod) + ~$4 (staging bursts) ≈ $59/month |
| Both environments running 24/7 | ~$504/month |
| Only production 24/7, control plane + NAT | ~$324/month |
| Both fully destroyed between demos | ~$0.70 per 1-hour demo (both up) |

### Why These Instance Sizes?

| Resource | Size Chosen | Why |
|----------|-------------|-----|
| EKS nodes | **t3.medium** (2 vCPU, 4GB RAM) | Each of the 12 microservices requests ~128MB RAM. 12 services × 128MB = 1.5GB. With 2 nodes × 4GB = 8GB total, there's headroom for system pods (CoreDNS, kube-proxy, ArgoCD). t3.small (2GB) would be too tight. |
| RDS | **db.t3.micro** (2 vCPU, 1GB RAM) | The database workload is light — a handful of tables, no complex reporting queries. Micro is the smallest instance class that supports PostgreSQL 15 features we need. Can upgrade to db.t3.small if queries become slow. |
| ElastiCache | **cache.t3.micro** (2 vCPU, 0.5GB RAM) | Redis is used as a session store and cache, not as a primary data store. The dataset is small (session tokens, cached responses). Micro is sufficient. |
| VPC | **2 AZs** (not 3) | 3 AZs is recommended for production HA, but each AZ adds a subnet and potential NAT gateway cost. 2 AZs provides basic redundancy at lower cost. |
| NAT Gateway | **1** (not per-AZ) | A single NAT gateway means if that AZ goes down, private instances lose internet access. For a college project, this is an acceptable risk vs. doubling NAT costs (~$32/month per gateway). |

---

## CI/CD Variables Required

Set these in **GitLab > Settings > CI/CD > Variables** (masked + protected):

| Variable | Description | Where |
|----------|-------------|-------|
| `AWS_ACCESS_KEY_ID` | AWS IAM access key for the Terraform CI user | Infra repo |
| `AWS_SECRET_ACCESS_KEY` | AWS IAM secret key for the Terraform CI user | Infra repo |
| `TF_VAR_rds_username` | PostgreSQL master username (e.g. `dbadmin`) | Infra repo |
| `TF_VAR_rds_password` | PostgreSQL master password (strong, 16+ chars) | Infra repo |
| `INFRACOST_API_KEY` | Free API key from [infracost.io](https://www.infracost.io/) (cost estimation) | Infra repo |

The CD repo also needs AWS credentials (to run `kubectl` against EKS):
| Variable | Description | Where |
|----------|-------------|-------|
| `AWS_ACCESS_KEY_ID` | Same or separate IAM user with EKS access | CD repo |
| `AWS_SECRET_ACCESS_KEY` | Corresponding secret key | CD repo |
| `INFRA_TRIGGER_TOKEN` | GitLab trigger token for cross-project pipeline | CD repo |

The Dev repo needs Docker Hub credentials (for image push):
| Variable | Description | Where |
|----------|-------------|-------|
| `DOCKER_HUB_USERNAME` | Docker Hub username (`bencev04`) | Dev repo |
| `DOCKER_HUB_TOKEN` | Docker Hub access token | Dev repo |
| `CD_TRIGGER_TOKEN` | GitLab trigger token to kick off CD pipeline | Dev repo |

---

## How to Go Forward

### Immediate Next Steps

1. **Push this repo to GitLab** — create the `yr4-projectinfrarepo` repository on your DKit GitLab instance, push all the Terraform code.

2. **Create the AWS IAM user** — follow Step 1 in the [First-Time Setup](#first-time-setup-from-scratch) section. Store the credentials securely.

3. **Set GitLab CI/CD variables** — add `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `TF_VAR_rds_username`, and `TF_VAR_rds_password` to the infra repo's CI/CD settings.

4. **Bootstrap the state backend** — run the bootstrap once from your local machine. This creates the S3 bucket and DynamoDB table.

5. **Run your first `make plan`** — review the plan output to verify everything looks correct before applying.

6. **Run `make apply`** — provision the full infrastructure. This is the big moment.

7. **Connect kubectl and install ArgoCD** — follow Steps 4-6 in the [First-Time Setup](#first-time-setup-from-scratch) section.

8. **Wire up the CD repo** — add the `ensure-infra` trigger stage to the CD pipeline so it can automatically bring the cluster up when deploying.

### After Initial Setup

Once the infrastructure is running and ArgoCD is deployed:

- **Test the full pipeline** — push a change to the dev repo, watch it flow through CI → build → CD trigger → infra ensure → ArgoCD sync → staging deployment
- **Run a manual scale-down/scale-up cycle** — verify you can take the cluster down and bring it back without losing anything
- **Run a full destroy/rebuild cycle** — verify the entire platform can be recreated from scratch
- **Document the RDS connection strings** — after each `make apply`, run `terraform output` and note the RDS/Redis endpoints. These go into Kubernetes secrets.

### Things to Watch Out For

- **RDS auto-restart** — AWS automatically restarts stopped RDS instances after 7 days. If you scale down but leave RDS alive, it may incur charges on its own. Consider including RDS stop/start in the scale-down/scale-up scripts.
- **Terraform version drift** — the `.gitlab-ci.yml` uses `hashicorp/terraform:1.7`. If you upgrade locally, ensure the CI image matches or you'll get state compatibility issues.
- **NAT Gateway cost** — the NAT gateway charges even when no traffic flows through it (~$32/month). If cost is critical, consider destroying and recreating it as part of scale-up/scale-down.
- **EKS addon versions** — CoreDNS, kube-proxy, and VPC CNI versions should match the EKS version. When upgrading EKS (e.g. 1.29 → 1.30), check addon compatibility.


