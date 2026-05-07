# Staging Environment — Step-by-Step Setup Guide

This guide covers two approaches to bringing up the staging environment:

1. **Without AWS Secrets Manager** — manual secret creation (simpler, good for initial testing)
2. **With AWS Secrets Manager** — automated secret sync via External Secrets Operator (production-grade)

Both approaches use the same Terraform infrastructure. The only difference is how Kubernetes secrets (database credentials, Redis endpoint) get into the cluster.

---

## Prerequisites (Both Approaches)

Before starting, ensure you have:

- [ ] **AWS CLI** installed and configured (`aws --version`)
- [ ] **Terraform** >= 1.9 installed (`terraform --version`)
- [ ] **kubectl** installed (`kubectl version --client`)
- [ ] **AWS IAM credentials** with permissions for EKS, RDS, ElastiCache, VPC, IAM, S3, DynamoDB
- [ ] **S3 backend** already bootstrapped:
  - S3 bucket: `yr4-project-tf-state`
  - DynamoDB table: `yr4-project-terraform-locks`
  - (Created by the `bootstrap/` module — see main README)

---

## Approach 1: Without AWS Secrets Manager (Manual)

This is the simplest approach. You create Kubernetes secrets manually using `kubectl`. No extra AWS services needed.

### Step 1 — Set Environment Variables

Open a terminal and set your AWS credentials and RDS credentials. Use your local AWS profile, AWS SSO, or masked CI/CD variables; do not commit real values.

**PowerShell:**
```powershell
$env:AWS_DEFAULT_REGION = "eu-west-1"
$env:TF_VAR_rds_username = "staging_admin"
$env:TF_VAR_rds_password = "<choose-a-strong-password>"
```

**Bash / GitLab CI:**
```bash
export AWS_DEFAULT_REGION="eu-west-1"
export TF_VAR_rds_username="staging_admin"
export TF_VAR_rds_password="<choose-a-strong-password>"
```

> **IMPORTANT:** Never commit these values to Git. In CI/CD, set them as masked + protected variables in GitLab Settings > CI/CD > Variables.

### Step 2 — Initialize Terraform

```bash
cd terraform/environments/staging
terraform init
```

This connects to the S3 backend, downloads providers (AWS ~5.x, TLS ~4.x), and resolves all 5 modules (VPC, IAM, EKS, RDS, ElastiCache).

### Step 3 — Review the Plan

```bash
terraform plan
```

Review the output. You should see approximately **30–40 resources** to be created:

| Module      | Key Resources                                          |
|-------------|--------------------------------------------------------|
| VPC         | VPC, 2 public subnets, 2 private subnets, NAT gateway, route tables |
| IAM         | EKS cluster role, node role, ALB controller role (IRSA) |
| EKS         | EKS cluster, KMS key, OIDC provider, managed node group, security group |
| RDS         | DB subnet group, security group, PostgreSQL instance   |
| ElastiCache | Subnet group, security group, Redis replication group  |

### Step 4 — Apply (Create Infrastructure)

```bash
terraform apply
```

Type `yes` when prompted. This takes **~15–20 minutes** (EKS cluster creation is the slowest part).

**What gets created:**
- EKS cluster: `yr4-project-staging-eks` (2× `t3.medium` nodes)
- RDS: `yr4-project-staging-postgres` (PostgreSQL 15, `db.t3.micro`, database: `crm_calendar_staging`)
- Redis: `yr4-project-staging-redis` (`cache.t3.micro`)
- Full VPC with public/private subnets in 2 AZs

### Step 5 — Configure kubectl

```bash
aws eks update-kubeconfig --name yr4-project-staging-eks --region eu-west-1
```

### Step 6 — Verify the Cluster

```bash
# Check nodes are ready
kubectl get nodes

# Expected output (2 nodes):
# NAME                                       STATUS   ROLES    AGE   VERSION
# ip-10-0-x-x.eu-west-1.compute.internal     Ready    <none>   5m    v1.29.x
# ip-10-0-x-x.eu-west-1.compute.internal     Ready    <none>   5m    v1.29.x
```

### Step 7 — Get the RDS and Redis Endpoints

```bash
terraform output rds_address
# e.g. yr4-project-staging-postgres.xxxx.eu-west-1.rds.amazonaws.com

terraform output redis_endpoint
# e.g. yr4-project-staging-redis.xxxx.cache.amazonaws.com
```

### Step 8 — Create the Kubernetes Namespace

```bash
kubectl create namespace year4-project-staging
```

### Step 9 — Create the `db-credentials` Secret Manually

```bash
kubectl -n year4-project-staging create secret generic db-credentials \
  --from-literal=host=$(terraform output -raw rds_address) \
  --from-literal=port=5432 \
  --from-literal=username="staging_admin" \
  --from-literal=password="<same-password-from-step-1>" \
  --from-literal=database="crm_calendar_staging"
```

### Step 10 — Verify the Secret

```bash
kubectl -n year4-project-staging get secret db-credentials -o yaml
```

You should see base64-encoded values for host, port, username, password, and database.

### Step 11 — (Optional) Create Redis Secret

```bash
kubectl -n year4-project-staging create secret generic redis-credentials \
  --from-literal=host=$(terraform output -raw redis_endpoint) \
  --from-literal=port=6379
```

### Step 12 — Deploy the Application

Use the CD pipeline or deploy manually:

```bash
# From the deployment repo
kubectl apply -k kubernetes/overlays/staging
```

### Tearing Down

When done testing:

```bash
# Scale nodes to zero (keeps cluster, saves ~$3/day on nodes)
aws eks update-nodegroup-config \
  --cluster-name yr4-project-staging-eks \
  --nodegroup-name yr4-project-staging-eks-nodes \
  --scaling-config minSize=0,maxSize=3,desiredSize=0

# OR destroy everything (~15 min)
cd terraform/environments/staging
terraform destroy
```

> **Note:** After `terraform destroy`, you'll need to redo Steps 4–11 to recreate everything.

---

## Approach 2: With AWS Secrets Manager (Fully Automated — Production-Grade)

This approach is fully automated. Terraform creates AWS Secrets Manager entries with dynamic RDS/Redis endpoints, the IAM module creates the ESO IRSA role, and the CD pipeline installs ESO and applies the Kustomize overlay (which includes ExternalSecret CRDs). No manual AWS CLI commands needed.

**What's automated by Terraform (`terraform apply`):**
- AWS Secrets Manager entries (`yr4-project/staging/db-credentials`, `redis-credentials`, `app-secrets`, `api-keys`) — populated with real RDS/Redis endpoints
- IAM IRSA role (`yr4-project-staging-eso-role`) — trust policy for ESO service account via OIDC
- IAM policy for Secrets Manager read access — scoped to `yr4-project/*`

**What's automated by the CD pipeline:**
- ESO Helm installation (with IRSA annotation)
- cert-manager Helm installation
- Kustomize overlay application (includes ExternalSecret CRDs, ClusterSecretStore, migration Job)
- ExternalSecret sync verification (waits for secrets before pod rollout)

### Step 1 — Set GitLab CI/CD Variables (One-Time)

In **each repo** (infra, deployment, dev), go to **Settings > CI/CD > Variables** and set:

| Variable | Scope | Masked | Protected | Notes |
|----------|-------|--------|-----------|-------|
| `AWS_ACCESS_KEY_ID` | All | Yes | Yes | IAM user with EKS/RDS/etc permissions |
| `AWS_SECRET_ACCESS_KEY` | All | Yes | Yes | |
| `AWS_DEFAULT_REGION` | All | No | No | `eu-west-1` |
| `TF_VAR_rds_username` | Infra | Yes | Yes | e.g. `staging_admin` |
| `TF_VAR_rds_password` | Infra | Yes | Yes | Strong password |
| `TF_VAR_secret_key` | Infra | Yes | Yes | `openssl rand -hex 64` |
| `TF_VAR_notification_encryption_key` | Infra | Yes | Yes | Fernet key |
| `TF_VAR_google_maps_server_key` | Infra | Yes | Yes | Google Maps API key |
| `TF_VAR_google_maps_browser_key` | Infra | Yes | Yes | Google Maps API key |

### Step 2 — Apply Terraform (Creates Everything)

```bash
cd terraform/environments/staging
terraform init
terraform plan
terraform apply    # ~15-20 min
```

This creates the EKS cluster, RDS, ElastiCache, VPC, IAM roles (including ESO IRSA), **and** populates AWS Secrets Manager with the real RDS/Redis endpoints automatically. No manual `aws secretsmanager create-secret` needed.

### Step 3 — Configure kubectl

```bash
aws eks update-kubeconfig --name yr4-project-staging-eks --region eu-west-1
```

### Step 4 — Deploy (CD Pipeline or Manual)

**Via pipeline (fully automatic):** Push to dev repo main → CI builds → triggers CD → CD triggers infra ensure → installs addons (cert-manager + ESO) → applies Kustomize overlay → waits for ExternalSecret sync → verifies rollout → smoke tests.

**Manual (for testing):**
```bash
# Install ESO (the CD pipeline does this automatically)
helm repo add external-secrets https://charts.external-secrets.io
ESO_ROLE_ARN=$(aws iam get-role --role-name yr4-project-staging-eso-role --query 'Role.Arn' --output text)
helm upgrade --install external-secrets external-secrets/external-secrets \
  --namespace external-secrets --create-namespace \
  --set serviceAccount.create=true \
  --set serviceAccount.name=external-secrets-sa \
  --set "serviceAccount.annotations.eks\.amazonaws\.com/role-arn=$ESO_ROLE_ARN" \
  --wait --timeout 300s

# Deploy the application
kubectl apply -k kubernetes/overlays/staging

# Verify secrets synced
kubectl -n year4-project-staging get externalsecrets
# Should show SecretSynced for all entries
```

### Step 5 — Verify

```bash
# Check ExternalSecrets synced
kubectl -n year4-project-staging get externalsecrets

# Check pods running
kubectl -n year4-project-staging get pods

# Check LoadBalancer URL
kubectl -n year4-project-staging get svc nginx-gateway
```

### Tearing Down

```bash
# Scale nodes to zero (keeps cluster, saves ~$3/day on nodes)
aws eks update-nodegroup-config \
  --cluster-name yr4-project-staging-eks \
  --nodegroup-name yr4-project-staging-eks-nodes \
  --scaling-config minSize=0,maxSize=3,desiredSize=0

# OR destroy everything (~15 min)
cd terraform/environments/staging
terraform destroy
```

> **Note:** Secrets Manager entries are destroyed with `terraform destroy`. On next `terraform apply`, they are recreated with fresh endpoints. ESO auto-syncs them into K8s on next deploy.

---

## Comparison: Which Approach to Use?

| Factor | Manual (Approach 1) | Automated (Approach 2) |
|--------|---------------------|------------------------|
| **Setup complexity** | Low — kubectl commands | One-time CI/CD variable setup |
| **AWS cost** | $0 extra | ~$0.40/secret/month |
| **Secret rotation** | Manual `kubectl` re-create | Auto-sync hourly via ESO |
| **After `terraform destroy`** | Must re-create secret manually | Terraform recreates secrets; ESO syncs on redeploy |
| **Security** | Creds in kubectl history | Creds only in AWS Secrets Manager + Terraform state |
| **CI/CD integration** | None — manual steps | Fully automated end-to-end |
| **Best for** | Quick testing, initial verification | Production, CI/CD automation |

**Recommendation:** Start with Approach 1 to verify connectivity, then use Approach 2 for all CI/CD deployments (it's the default pipeline path).

---

## Troubleshooting

### Cluster nodes not coming up
```bash
aws eks describe-nodegroup \
  --cluster-name yr4-project-staging-eks \
  --nodegroup-name yr4-project-staging-eks-nodes \
  --query 'nodegroup.{status:status,desiredSize:scalingConfig.desiredSize,health:health}'
```

### Pods can't connect to RDS
1. Verify the secret exists: `kubectl -n year4-project-staging get secret db-credentials`
2. Verify deployments reference the secret (check for `secretKeyRef` or `envFrom` in the deployment YAML)
3. Check security groups: RDS SG must allow ingress from EKS cluster SG on port 5432
4. Test connectivity from a pod:
   ```bash
   kubectl -n year4-project-staging run pg-test --rm -it --image=postgres:15-alpine -- \
     psql "postgresql://staging_admin:<password>@<rds-address>:5432/crm_calendar_staging"
   ```

### Terraform state lock
If a previous apply was interrupted:
```bash
terraform force-unlock <LOCK_ID>
```

### ESO not syncing secrets (Approach 2)
```bash
kubectl -n year4-project-staging describe externalsecret db-credentials
# Check Events section for error messages
```
