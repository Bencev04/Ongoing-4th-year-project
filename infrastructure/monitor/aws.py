"""Blocking AWS boto3 fetch functions (run via asyncio.to_thread)."""
from __future__ import annotations

import asyncio

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from monitor.config import BOOTSTRAP_CONFIG, ENV_CONFIG


# ─── Session cache ────────────────────────────────────────────────────────────
# Reuse sessions/clients across refreshes to avoid repeated STS calls.

_sessions: dict[tuple[str | None, str], boto3.Session] = {}
_clients: dict[tuple[str | None, str, str], object] = {}


def _session(profile: str | None, region: str) -> boto3.Session:
    key = (profile, region)
    if key not in _sessions:
        _sessions[key] = boto3.Session(profile_name=profile, region_name=region)
    return _sessions[key]


def _client(profile: str | None, region: str, service: str):
    key = (profile, region, service)
    if key not in _clients:
        _clients[key] = _session(profile, region).client(service)
    return _clients[key]


# ─── Error handling ───────────────────────────────────────────────────────────

_NOT_FOUND_CODES = {
    "ResourceNotFoundException",
    "DBInstanceNotFound",
    "DBInstanceNotFoundFault",
    "ReplicationGroupNotFoundFault",
    "CacheClusterNotFound",
}


def _classify_error(exc: Exception) -> dict:
    if isinstance(exc, NoCredentialsError):
        return {"status": "ERROR", "_detail": "No AWS credentials found"}
    if isinstance(exc, ClientError):
        code = exc.response["Error"]["Code"]
        if code in _NOT_FOUND_CODES:
            return {"status": "NOT FOUND"}
        return {"status": "ERROR", "_detail": exc.response["Error"]["Message"][:80]}
    if any(k in type(exc).__name__ for k in ("NotFound", "NotExist", "DoesNotExist")):
        return {"status": "NOT FOUND"}
    return {"status": "ERROR", "_detail": str(exc)[:80]}


# ─── Bootstrap resource fetchers ──────────────────────────────────────────────

def fetch_s3_bucket(bucket_name: str, profile: str | None, region: str) -> dict:
    """Fetch S3 bucket status and properties."""
    try:
        s3 = _client(profile, region, "s3")
        # Head bucket to check existence
        s3.head_bucket(Bucket=bucket_name)
        # Get versioning
        ver = s3.get_bucket_versioning(Bucket=bucket_name)
        versioning = ver.get("Status", "Disabled")
        # Get encryption
        try:
            enc = s3.get_bucket_encryption(Bucket=bucket_name)
            rules = enc.get("ServerSideEncryptionConfiguration", {}).get("Rules", [])
            encryption = rules[0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"] if rules else "None"
        except ClientError:
            encryption = "None"
        # Get public access block
        try:
            pab = s3.get_public_access_block(Bucket=bucket_name)
            cfg = pab.get("PublicAccessBlockConfiguration", {})
            public_blocked = all([
                cfg.get("BlockPublicAcls", False),
                cfg.get("BlockPublicPolicy", False),
                cfg.get("IgnorePublicAcls", False),
                cfg.get("RestrictPublicBuckets", False),
            ])
        except ClientError:
            public_blocked = False
        return {
            "status": "available",
            "bucket": bucket_name,
            "versioning": versioning,
            "encryption": encryption,
            "public_blocked": public_blocked,
        }
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("404", "NoSuchBucket"):
            return {"status": "NOT FOUND"}
        return _classify_error(exc)
    except Exception as exc:
        return _classify_error(exc)


def fetch_dynamodb_table(table_name: str, profile: str | None, region: str) -> dict:
    """Fetch DynamoDB table status and properties."""
    try:
        ddb = _client(profile, region, "dynamodb")
        resp = ddb.describe_table(TableName=table_name)
        table = resp["Table"]
        status = table["TableStatus"]  # ACTIVE, CREATING, DELETING, etc.
        billing = table.get("BillingModeSummary", {}).get("BillingMode", "PROVISIONED")
        item_count = table.get("ItemCount", 0)
        size_bytes = table.get("TableSizeBytes", 0)
        return {
            "status": "available" if status == "ACTIVE" else status,
            "table_name": table_name,
            "billing_mode": billing,
            "item_count": str(item_count),
            "size_bytes": f"{size_bytes} B",
            "table_status": status,
        }
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ResourceNotFoundException":
            return {"status": "NOT FOUND"}
        return _classify_error(exc)
    except Exception as exc:
        return _classify_error(exc)


async def fetch_bootstrap(profile: str | None, region: str) -> dict:
    """Fetch all bootstrap resources concurrently."""
    s3_data, ddb_data = await asyncio.gather(
        asyncio.to_thread(
            fetch_s3_bucket, BOOTSTRAP_CONFIG["s3_bucket"], profile, region,
        ),
        asyncio.to_thread(
            fetch_dynamodb_table, BOOTSTRAP_CONFIG["dynamodb_table"], profile, region,
        ),
    )
    return {"s3_bucket": s3_data, "dynamodb_table": ddb_data}


# ─── Individual resource fetchers ─────────────────────────────────────────────

def fetch_eks_cluster(cluster_name: str, profile: str | None, region: str) -> dict:
    try:
        eks = _client(profile, region, "eks")
        cluster = eks.describe_cluster(name=cluster_name)["cluster"]
        return {
            "status":           cluster["status"],
            "version":          cluster.get("version", "-"),
            "platform_version": cluster.get("platformVersion", "-"),
            "endpoint":         (cluster.get("endpoint") or "not yet assigned")[:60],
        }
    except Exception as exc:
        return _classify_error(exc)


def fetch_node_group(cluster_name: str, ng_name: str, profile: str | None, region: str) -> dict:
    try:
        eks = _client(profile, region, "eks")
        ng = eks.describe_nodegroup(
            clusterName=cluster_name, nodegroupName=ng_name,
        )["nodegroup"]
        sc = ng.get("scalingConfig", {})
        return {
            "status":        ng["status"],
            "desired":       sc.get("desiredSize", "-"),
            "min":           sc.get("minSize", "-"),
            "max":           sc.get("maxSize", "-"),
            "instance_type": (ng.get("instanceTypes") or ["-"])[0],
            "ami":           ng.get("amiType", "-"),
        }
    except Exception as exc:
        return _classify_error(exc)


def fetch_rds(identifier: str, profile: str | None, region: str) -> dict:
    try:
        rds = _client(profile, region, "rds")
        db = rds.describe_db_instances(
            DBInstanceIdentifier=identifier,
        )["DBInstances"][0]
        return {
            "status":         db["DBInstanceStatus"],
            "engine":         f"{db.get('Engine', '-')} {db.get('EngineVersion', '')}".strip(),
            "instance_class": db.get("DBInstanceClass", "-"),
            "storage":        f"{db.get('AllocatedStorage', '-')} GB",
            "multi_az":       db.get("MultiAZ", False),
            "db_name":        db.get("DBName", "-"),
        }
    except Exception as exc:
        return _classify_error(exc)


def fetch_redis(redis_id: str, profile: str | None, region: str) -> dict:
    try:
        ec = _client(profile, region, "elasticache")
        rg = ec.describe_replication_groups(
            ReplicationGroupId=redis_id,
        )["ReplicationGroups"][0]
        members = rg.get("MemberClusters", [])
        node_type = "-"
        if members:
            try:
                resp = ec.describe_cache_clusters(CacheClusterId=members[0])
                node_type = resp["CacheClusters"][0].get("CacheNodeType", "-")
            except Exception:
                pass
        return {
            "status":    rg["Status"],
            "node_type": node_type,
            "nodes":     str(len(members)),
        }
    except Exception as exc:
        return _classify_error(exc)


def fetch_vpc(vpc_tag: str, profile: str | None, region: str) -> dict:
    """Find VPC by Name tag prefix (project_name-environment)."""
    try:
        ec2 = _client(profile, region, "ec2")
        resp = ec2.describe_vpcs(
            Filters=[{"Name": "tag:Name", "Values": [f"{vpc_tag}*"]}],
        )
        vpcs = resp.get("Vpcs", [])
        if not vpcs:
            return {"status": "NOT FOUND"}
        vpc = vpcs[0]
        return {
            "status":     vpc["State"],
            "vpc_id":     vpc["VpcId"],
            "cidr":       vpc.get("CidrBlock", "-"),
        }
    except Exception as exc:
        return _classify_error(exc)


# ─── New resource fetchers ────────────────────────────────────────────────────

def fetch_iam_roles(role_names: list[str], profile: str | None, region: str) -> dict:
    """Fetch status of IAM roles used by the environment."""
    try:
        iam = _client(profile, region, "iam")
        found, missing = [], []
        for name in role_names:
            try:
                role = iam.get_role(RoleName=name)["Role"]
                short = name.rsplit("-", 1)[-1] if "-" in name else name
                found.append(short)
            except ClientError as e:
                if e.response["Error"]["Code"] == "NoSuchEntity":
                    missing.append(name.rsplit("-", 1)[-1])
                else:
                    raise
        status = "available" if not missing else ("PARTIAL" if found else "NOT FOUND")
        return {
            "status": status,
            "found": ", ".join(found) if found else "-",
            "missing": ", ".join(missing) if missing else "-",
            "total": f"{len(found)}/{len(role_names)}",
        }
    except Exception as exc:
        return _classify_error(exc)


def fetch_secrets(secret_names: list[str], profile: str | None, region: str) -> dict:
    """Fetch status of Secrets Manager secrets."""
    try:
        sm = _client(profile, region, "secretsmanager")
        results = []
        for name in secret_names:
            short = name.rsplit("/", 1)[-1]
            try:
                s = sm.describe_secret(SecretId=name)
                if s.get("DeletedDate"):
                    results.append((short, "DELETING"))
                else:
                    results.append((short, "available"))
            except ClientError as e:
                if e.response["Error"]["Code"] == "ResourceNotFoundException":
                    results.append((short, "NOT FOUND"))
                else:
                    raise

        statuses = [s for _, s in results]
        if all(s == "available" for s in statuses):
            overall = "available"
        elif all(s == "NOT FOUND" for s in statuses):
            overall = "NOT FOUND"
        else:
            overall = "PARTIAL"

        detail_parts = []
        for name, st in results:
            icon = "●" if st == "available" else ("◍" if st == "DELETING" else "✗")
            detail_parts.append(f"{icon} {name}")

        return {
            "status": overall,
            "detail": "  ".join(detail_parts),
            "total": f"{sum(1 for s in statuses if s == 'available')}/{len(secret_names)}",
        }
    except Exception as exc:
        return _classify_error(exc)


def fetch_nat_gateway(vpc_tag: str, profile: str | None, region: str) -> dict:
    """Find NAT Gateway associated with the environment VPC."""
    try:
        ec2 = _client(profile, region, "ec2")
        # First find the VPC
        vpcs = ec2.describe_vpcs(
            Filters=[{"Name": "tag:Name", "Values": [f"{vpc_tag}*"]}],
        ).get("Vpcs", [])
        if not vpcs:
            return {"status": "NOT FOUND", "_detail": "VPC not found"}
        vpc_id = vpcs[0]["VpcId"]

        nats = ec2.describe_nat_gateways(
            Filters=[
                {"Name": "vpc-id", "Values": [vpc_id]},
                {"Name": "state", "Values": ["pending", "available", "deleting", "failed"]},
            ],
        ).get("NatGateways", [])
        if not nats:
            return {"status": "NOT FOUND"}
        nat = nats[0]
        public_ip = "-"
        for addr in nat.get("NatGatewayAddresses", []):
            if addr.get("PublicIp"):
                public_ip = addr["PublicIp"]
                break
        return {
            "status":    nat["State"],
            "nat_id":    nat["NatGatewayId"],
            "public_ip": public_ip,
            "subnet":    nat.get("SubnetId", "-"),
        }
    except Exception as exc:
        return _classify_error(exc)


def fetch_eks_addons(cluster_name: str, addon_names: list[str], profile: str | None, region: str) -> dict:
    """Fetch status of EKS managed addons."""
    try:
        eks = _client(profile, region, "eks")
        results = []
        for name in addon_names:
            try:
                addon = eks.describe_addon(
                    clusterName=cluster_name, addonName=name,
                )["addon"]
                results.append((name, addon["status"], addon.get("addonVersion", "-")))
            except ClientError as e:
                code = e.response["Error"]["Code"]
                if code == "ResourceNotFoundException":
                    results.append((name, "NOT FOUND", "-"))
                else:
                    raise

        statuses = [s for _, s, _ in results]
        if all(s == "ACTIVE" for s in statuses):
            overall = "ACTIVE"
        elif all(s == "NOT FOUND" for s in statuses):
            overall = "NOT FOUND"
        else:
            overall = "PARTIAL"

        detail_parts = []
        for name, st, ver in results:
            icon = "●" if st == "ACTIVE" else ("◌" if st in ("CREATING", "UPDATING") else "✗")
            detail_parts.append(f"{icon} {name} ({ver})")

        return {
            "status": overall,
            "detail": "  ".join(detail_parts),
            "total":  f"{sum(1 for s in statuses if s == 'ACTIVE')}/{len(addon_names)}",
        }
    except Exception as exc:
        return _classify_error(exc)


def fetch_security_groups(vpc_tag: str, profile: str | None, region: str) -> dict:
    """Fetch security groups in the environment VPC."""
    try:
        ec2 = _client(profile, region, "ec2")
        vpcs = ec2.describe_vpcs(
            Filters=[{"Name": "tag:Name", "Values": [f"{vpc_tag}*"]}],
        ).get("Vpcs", [])
        if not vpcs:
            return {"status": "NOT FOUND", "_detail": "VPC not found"}
        vpc_id = vpcs[0]["VpcId"]

        sgs = ec2.describe_security_groups(
            Filters=[{"Name": "vpc-id", "Values": [vpc_id]}],
        ).get("SecurityGroups", [])
        # Filter out the default SG
        custom_sgs = [sg for sg in sgs if sg["GroupName"] != "default"]
        if not custom_sgs:
            return {"status": "NOT FOUND"}

        detail_parts = []
        for sg in custom_sgs:
            name = sg.get("GroupName", sg["GroupId"])
            rules_in = len(sg.get("IpPermissions", []))
            rules_out = len(sg.get("IpPermissionsEgress", []))
            detail_parts.append(f"{name} (in:{rules_in} out:{rules_out})")

        return {
            "status": "available",
            "count":  str(len(custom_sgs)),
            "detail": "\n".join(detail_parts),
        }
    except Exception as exc:
        return _classify_error(exc)


# ─── Aggregate fetcher ────────────────────────────────────────────────────────

async def fetch_environment(env_key: str, profile: str | None, region: str) -> dict:
    """Fetch all resources for one environment concurrently."""
    cfg = ENV_CONFIG[env_key]
    eks, ng, rds, redis, vpc, iam, secrets, nat, addons, sgs = await asyncio.gather(
        asyncio.to_thread(fetch_eks_cluster, cfg["eks_cluster"], profile, region),
        asyncio.to_thread(fetch_node_group, cfg["eks_cluster"], cfg["node_group"], profile, region),
        asyncio.to_thread(fetch_rds, cfg["rds_id"], profile, region),
        asyncio.to_thread(fetch_redis, cfg["redis_id"], profile, region),
        asyncio.to_thread(fetch_vpc, cfg["vpc_tag"], profile, region),
        asyncio.to_thread(fetch_iam_roles, cfg["iam_roles"], profile, region),
        asyncio.to_thread(fetch_secrets, cfg["secrets"], profile, region),
        asyncio.to_thread(fetch_nat_gateway, cfg["vpc_tag"], profile, region),
        asyncio.to_thread(fetch_eks_addons, cfg["eks_cluster"], cfg["eks_addons"], profile, region),
        asyncio.to_thread(fetch_security_groups, cfg["vpc_tag"], profile, region),
    )
    return {
        "eks": eks, "nodegroup": ng, "rds": rds, "redis": redis, "vpc": vpc,
        "iam": iam, "secrets": secrets, "nat": nat, "addons": addons, "security_groups": sgs,
    }
