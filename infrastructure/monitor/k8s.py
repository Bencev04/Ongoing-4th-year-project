"""Kubernetes workload fetcher for EKS clusters.

Uses boto3 STS presigned URL as a bearer token (same mechanism as `aws eks
get-token`) to authenticate against the EKS API server, then queries
deployments and pods via the kubernetes Python client.
"""
from __future__ import annotations

import asyncio
import base64
import re
import tempfile
from typing import Any

import boto3
from botocore.signers import RequestSigner
from kubernetes import client as k8s_client
from kubernetes.client import Configuration

from monitor.config import DEPLOYMENTS, ENV_CONFIG

# ─── EKS token generation ────────────────────────────────────────────────────
# Mirrors `aws eks get-token` using STS GetCallerIdentity presigned URL.

_STS_TOKEN_EXPIRES_IN = 60  # seconds


def _get_bearer_token(cluster_name: str, region: str, profile: str | None) -> str:
    """Generate a Kubernetes-compatible bearer token for an EKS cluster."""
    session = boto3.Session(profile_name=profile, region_name=region)
    sts = session.client("sts", region_name=region)
    service_id = sts.meta.service_model.service_id

    signer = RequestSigner(service_id, region, "sts",
                           "v4", session.get_credentials(), session.events)

    params = {
        "method": "GET",
        "url": f"https://sts.{region}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15",
        "body": {},
        "headers": {"x-k8s-aws-id": cluster_name},
        "context": {},
    }

    signed_url = signer.generate_presigned_url(
        params, region_name=region, expires_in=_STS_TOKEN_EXPIRES_IN,
        operation_name="",
    )
    # The token is "k8s-aws-v1." + base64url-encoded presigned URL
    encoded = base64.urlsafe_b64encode(signed_url.encode("utf-8")).decode("utf-8")
    return "k8s-aws-v1." + re.sub(r"=+$", "", encoded)


# ─── K8s client factory ──────────────────────────────────────────────────────

def _make_k8s_clients(
    cluster_name: str, region: str, profile: str | None,
) -> tuple[k8s_client.AppsV1Api, k8s_client.CoreV1Api]:
    """Create authenticated K8s API clients for the given EKS cluster."""
    session = boto3.Session(profile_name=profile, region_name=region)
    eks = session.client("eks", region_name=region)
    cluster_info = eks.describe_cluster(name=cluster_name)["cluster"]

    status = cluster_info.get("status", "UNKNOWN")
    if status != "ACTIVE":
        raise RuntimeError(f"Cluster {cluster_name} is {status}; Kubernetes API not ready yet")

    endpoint = cluster_info["endpoint"]
    ca_data = (cluster_info.get("certificateAuthority") or {}).get("data")
    if not ca_data:
        raise RuntimeError(
            f"Cluster {cluster_name} certificate authority not available yet; retry when cluster is ACTIVE"
        )

    # Write CA cert to a temp file (kubernetes client needs a file path)
    ca_file = tempfile.NamedTemporaryFile(delete=False, suffix=".crt")
    ca_file.write(base64.b64decode(ca_data))
    ca_file.close()

    token = _get_bearer_token(cluster_name, region, profile)

    config = Configuration()
    config.host = endpoint
    config.ssl_ca_cert = ca_file.name
    config.api_key = {"authorization": f"Bearer {token}"}

    api_client = k8s_client.ApiClient(config)
    return k8s_client.AppsV1Api(api_client), k8s_client.CoreV1Api(api_client)


# ─── Deployment & pod fetchers ────────────────────────────────────────────────

def _pod_phase_icon(phase: str) -> str:
    return {
        "Running": "[green]●[/green]",
        "Succeeded": "[green]✓[/green]",
        "Pending": "[yellow]◌[/yellow]",
        "Failed": "[red]✗[/red]",
        "Unknown": "[dim]?[/dim]",
    }.get(phase, "[dim]?[/dim]")


def fetch_k8s_workloads(
    env_key: str, profile: str | None, region: str,
) -> dict[str, Any]:
    """Fetch deployment status for all microservices in the environment.

    Returns a dict with:
        status:      overall health (ACTIVE / PARTIAL / ERROR / NOT FOUND)
        deployments: list of per-deployment dicts
        summary:     "8/12 ready"
        pods_total:  total pod count
        pods_ready:  ready pod count
        recent_events: list of warning events (last 10)
    """
    cfg = ENV_CONFIG[env_key]
    cluster_name = cfg["eks_cluster"]
    namespace = cfg["namespace"]

    try:
        apps_api, core_api = _make_k8s_clients(cluster_name, region, profile)
    except Exception as exc:
        return {
            "status": "ERROR",
            "_detail": f"Cannot connect to cluster: {str(exc)[:100]}",
            "deployments": [],
            "summary": "-",
            "pods_total": 0,
            "pods_ready": 0,
            "recent_events": [],
        }

    # -- Fetch deployments --
    deploy_results: list[dict] = []
    try:
        dep_list = apps_api.list_namespaced_deployment(namespace=namespace)
        dep_by_name = {d.metadata.name: d for d in dep_list.items}
    except Exception as exc:
        return {
            "status": "ERROR",
            "_detail": f"Failed listing deployments: {str(exc)[:100]}",
            "deployments": [],
            "summary": "-",
            "pods_total": 0,
            "pods_ready": 0,
            "recent_events": [],
        }

    for svc_name in DEPLOYMENTS:
        dep = dep_by_name.get(svc_name)
        if dep is None:
            deploy_results.append({
                "name": svc_name,
                "status": "NOT FOUND",
                "ready": 0,
                "desired": 0,
                "available": 0,
                "image": "-",
            })
            continue

        desired = dep.spec.replicas or 0
        ready = dep.status.ready_replicas or 0
        available = dep.status.available_replicas or 0

        if ready >= desired and desired > 0:
            status = "ACTIVE"
        elif ready > 0:
            status = "PARTIAL"
        elif desired == 0:
            status = "SCALED_DOWN"
        else:
            status = "FAILED"

        # Extract first container image tag
        image = "-"
        containers = dep.spec.template.spec.containers
        if containers:
            full_image = containers[0].image or "-"
            # Show only tag portion if it's long
            image = full_image.rsplit(":", 1)[-1] if ":" in full_image else full_image

        deploy_results.append({
            "name": svc_name,
            "status": status,
            "ready": ready,
            "desired": desired,
            "available": available,
            "image": image,
        })

    # -- Fetch pods for aggregate counts --
    pods_total = 0
    pods_ready = 0
    pod_details: list[dict] = []
    try:
        pod_list = core_api.list_namespaced_pod(namespace=namespace)
        for pod in pod_list.items:
            pods_total += 1
            phase = pod.status.phase or "Unknown"
            container_ready = 0
            container_total = 0
            restarts = 0
            if pod.status.container_statuses:
                for cs in pod.status.container_statuses:
                    container_total += 1
                    if cs.ready:
                        container_ready += 1
                    restarts += cs.restart_count or 0
            if phase == "Running" and container_ready == container_total and container_total > 0:
                pods_ready += 1
            pod_details.append({
                "name": pod.metadata.name,
                "phase": phase,
                "containers": f"{container_ready}/{container_total}",
                "restarts": restarts,
            })
    except Exception:
        pass  # pod info is supplementary

    # -- Fetch warning events --
    recent_events: list[str] = []
    try:
        events = core_api.list_namespaced_event(
            namespace=namespace,
            field_selector="type=Warning",
        )
        # Take the last 10 by last timestamp
        sorted_events = sorted(
            events.items,
            key=lambda e: e.last_timestamp or e.event_time or e.metadata.creation_timestamp,
            reverse=True,
        )[:10]
        for ev in sorted_events:
            ts = ev.last_timestamp or ev.event_time or ev.metadata.creation_timestamp
            ts_str = ts.strftime("%H:%M:%S") if ts else "?"
            recent_events.append(f"{ts_str} [{ev.involved_object.name}] {ev.message[:80]}")
    except Exception:
        pass  # events are supplementary

    # -- Overall status --
    statuses = [d["status"] for d in deploy_results]
    ready_count = sum(1 for s in statuses if s == "ACTIVE")
    total_count = len(deploy_results)

    if ready_count == total_count:
        overall = "ACTIVE"
    elif ready_count == 0:
        if all(s == "NOT FOUND" for s in statuses):
            overall = "NOT FOUND"
        else:
            overall = "FAILED"
    else:
        overall = "PARTIAL"

    # -- Check data-layer connectivity (db-access pods as a proxy) --
    connectivity: dict[str, dict] = {}
    db_pods = ["user-db-access-service", "job-db-access-service-deployment", "customer-db-access-service"]
    for svc in db_pods:
        dep = dep_by_name.get(svc)
        if dep is None:
            connectivity[svc] = {"status": "NOT FOUND", "detail": "deployment missing"}
        else:
            ready = dep.status.ready_replicas or 0
            desired = dep.spec.replicas or 0
            # If db-access pods are running and ready, RDS connection is working
            if ready >= desired and desired > 0:
                connectivity[svc] = {"status": "ACTIVE", "detail": f"{ready}/{desired} ready → RDS reachable"}
            elif ready > 0:
                connectivity[svc] = {"status": "PARTIAL", "detail": f"{ready}/{desired} ready → some pods failing"}
            else:
                connectivity[svc] = {"status": "FAILED", "detail": "0 pods ready → RDS unreachable"}

    # Notification service uses Redis
    notif_dep = dep_by_name.get("notification-service")
    if notif_dep is None:
        connectivity["notification-service"] = {"status": "NOT FOUND", "detail": "deployment missing"}
    else:
        ready = notif_dep.status.ready_replicas or 0
        desired = notif_dep.spec.replicas or 0
        if ready >= desired and desired > 0:
            connectivity["notification-service"] = {"status": "ACTIVE", "detail": f"{ready}/{desired} ready → Redis reachable"}
        elif ready > 0:
            connectivity["notification-service"] = {"status": "PARTIAL", "detail": f"{ready}/{desired} ready → some pods failing"}
        else:
            connectivity["notification-service"] = {"status": "FAILED", "detail": "0 pods ready → Redis unreachable"}

    # -- Fetch access URLs (Ingress + LoadBalancer services) --
    access_urls: list[dict] = []
    try:
        ingress_list = k8s_client.NetworkingV1Api(
            apps_api.api_client
        ).list_namespaced_ingress(namespace=namespace)
        for ing in ingress_list.items:
            name = ing.metadata.name
            host = "-"
            if ing.spec.rules:
                host = ing.spec.rules[0].host or "-"
            address = "-"
            if ing.status and ing.status.load_balancer and ing.status.load_balancer.ingress:
                lb = ing.status.load_balancer.ingress[0]
                address = lb.hostname or lb.ip or "-"
            access_urls.append({"type": "Ingress", "name": name, "host": host, "address": address})
    except Exception:
        pass

    try:
        svc_list = core_api.list_namespaced_service(namespace=namespace)
        for svc in svc_list.items:
            if svc.spec.type == "LoadBalancer":
                address = "-"
                if svc.status and svc.status.load_balancer and svc.status.load_balancer.ingress:
                    lb = svc.status.load_balancer.ingress[0]
                    address = lb.hostname or lb.ip or "-"
                access_urls.append({
                    "type": "LoadBalancer",
                    "name": svc.metadata.name,
                    "host": "-",
                    "address": address,
                })
    except Exception:
        pass

    # Also check ingress-nginx namespace for the controller LB
    try:
        nginx_svcs = core_api.list_namespaced_service(namespace="ingress-nginx")
        for svc in nginx_svcs.items:
            if svc.spec.type == "LoadBalancer":
                address = "-"
                if svc.status and svc.status.load_balancer and svc.status.load_balancer.ingress:
                    lb = svc.status.load_balancer.ingress[0]
                    address = lb.hostname or lb.ip or "-"
                access_urls.append({
                    "type": "Ingress-NGINX",
                    "name": svc.metadata.name,
                    "host": "-",
                    "address": address,
                })
    except Exception:
        pass

    return {
        "status": overall,
        "deployments": deploy_results,
        "pod_details": pod_details,
        "summary": f"{ready_count}/{total_count} deployments ready",
        "pods_total": pods_total,
        "pods_ready": pods_ready,
        "recent_events": recent_events,
        "connectivity": connectivity,
        "access_urls": access_urls,
    }


# ─── Async wrapper ────────────────────────────────────────────────────────────

async def fetch_k8s_for_env(
    env_key: str, profile: str | None, region: str,
) -> dict[str, Any]:
    """Async wrapper that runs the blocking K8s calls in a thread."""
    return await asyncio.to_thread(fetch_k8s_workloads, env_key, profile, region)
