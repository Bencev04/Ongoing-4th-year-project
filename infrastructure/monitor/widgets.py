"""Textual widgets for the infrastructure monitor."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Static

from monitor.config import BOOTSTRAP_CONFIG, DEPLOYMENTS, ENV_CONFIG
from monitor.status import classify, status_markup


# ─── ResourceCard ─────────────────────────────────────────────────────────────

class ResourceCard(Static):
    """Bordered panel for a single AWS resource. Click to expand details."""

    DEFAULT_CSS = """
    ResourceCard {
        border: round $primary;
        padding: 0 1;
        margin: 0 1 1 0;
        width: 1fr;
        min-height: 7;
    }
    ResourceCard:hover {
        border: round $accent;
    }
    """

    class Selected(Message):
        """Posted when a card is clicked."""
        def __init__(self, card_id: str, title: str, data: dict) -> None:
            super().__init__()
            self.card_id = card_id
            self.card_title = title
            self.data = data

    def __init__(self, title: str, resource_name: str, card_id: str) -> None:
        super().__init__(id=card_id)
        self._title = title
        self._resource_name = resource_name
        self._prev_status: str | None = None
        self._last_data: dict = {}

    @property
    def prev_status(self) -> str | None:
        return self._prev_status

    def on_mount(self) -> None:
        self._refresh_card("LOADING", [])

    def on_click(self) -> None:
        self.post_message(self.Selected(self.id or "", self._title, self._last_data))

    def _refresh_card(self, status: str, rows: list[tuple[str, str]], detail: str = "") -> None:
        cat = classify(status)
        border_map = {
            "healthy": "green", "transitioning": "yellow",
            "winding_down": "orange", "error": "red", "absent": "gray",
        }
        self.styles.border = ("round", border_map.get(cat, "gray"))

        lines = [
            f"[bold white]{self._title}[/bold white]",
            f"[dim]{self._resource_name}[/dim]",
            "",
            f"  Status   {status_markup(status)}",
        ]
        for label, value in rows:
            lines.append(f"  [dim]{label:<13}[/dim] {value}")
        if detail:
            lines.append(f"  [red]> {detail}[/red]")

        self._prev_status = status
        self.update("\n".join(lines))

    # ── Typed updaters ────────────────────────────────────────────────────────

    def apply_eks(self, d: dict) -> None:
        self._last_data = d
        s = d.get("status", "UNKNOWN")
        rows: list[tuple[str, str]] = []
        if s not in ("NOT FOUND", "ERROR", "LOADING", "UNKNOWN"):
            rows = [
                ("K8s version",   d.get("version", "-")),
                ("Platform ver",  d.get("platform_version", "-")),
                ("Endpoint",      d.get("endpoint", "-")),
            ]
        self._refresh_card(s, rows, d.get("_detail", ""))

    def apply_nodegroup(self, d: dict) -> None:
        self._last_data = d
        s = d.get("status", "UNKNOWN")
        rows: list[tuple[str, str]] = []
        if s not in ("NOT FOUND", "ERROR", "LOADING", "UNKNOWN"):
            desired = d.get("desired", "-")
            mn, mx = d.get("min", "-"), d.get("max", "-")
            rows = [
                ("Nodes",         f"[bold]{desired}[/bold]  (min {mn} / max {mx})"),
                ("Instance type", d.get("instance_type", "-")),
                ("AMI type",      d.get("ami", "-")),
            ]
        self._refresh_card(s, rows, d.get("_detail", ""))

    def apply_rds(self, d: dict) -> None:
        self._last_data = d
        s = d.get("status", "UNKNOWN")
        rows: list[tuple[str, str]] = []
        if s not in ("NOT FOUND", "ERROR", "LOADING", "UNKNOWN"):
            multi_az = "[green]Yes[/green]" if d.get("multi_az") else "[dim]No[/dim]"
            rows = [
                ("Engine",        d.get("engine", "-")),
                ("Class",         d.get("instance_class", "-")),
                ("Storage",       d.get("storage", "-")),
                ("Multi-AZ",      multi_az),
                ("Database",      d.get("db_name", "-")),
            ]
        self._refresh_card(s, rows, d.get("_detail", ""))

    def apply_redis(self, d: dict) -> None:
        self._last_data = d
        s = d.get("status", "UNKNOWN")
        rows: list[tuple[str, str]] = []
        if s not in ("NOT FOUND", "ERROR", "LOADING", "UNKNOWN"):
            rows = [
                ("Node type",     d.get("node_type", "-")),
                ("Cluster nodes", d.get("nodes", "-")),
            ]
        self._refresh_card(s, rows, d.get("_detail", ""))

    def apply_vpc(self, d: dict) -> None:
        self._last_data = d
        s = d.get("status", "UNKNOWN")
        rows: list[tuple[str, str]] = []
        if s not in ("NOT FOUND", "ERROR", "LOADING", "UNKNOWN"):
            rows = [
                ("VPC ID",   d.get("vpc_id", "-")),
                ("CIDR",     d.get("cidr", "-")),
            ]
        self._refresh_card(s, rows, d.get("_detail", ""))

    def apply_iam(self, d: dict) -> None:
        self._last_data = d
        s = d.get("status", "UNKNOWN")
        rows: list[tuple[str, str]] = []
        if s not in ("NOT FOUND", "ERROR", "LOADING", "UNKNOWN"):
            rows = [
                ("Roles found", d.get("total", "-")),
                ("Present",     d.get("found", "-")),
            ]
            if d.get("missing") and d["missing"] != "-":
                rows.append(("Missing", f"[red]{d['missing']}[/red]"))
        self._refresh_card(s, rows, d.get("_detail", ""))

    def apply_secrets(self, d: dict) -> None:
        self._last_data = d
        s = d.get("status", "UNKNOWN")
        rows: list[tuple[str, str]] = []
        if s not in ("NOT FOUND", "ERROR", "LOADING", "UNKNOWN"):
            rows = [
                ("Secrets", d.get("total", "-")),
                ("Detail",  d.get("detail", "-")),
            ]
        self._refresh_card(s, rows, d.get("_detail", ""))

    def apply_nat(self, d: dict) -> None:
        self._last_data = d
        s = d.get("status", "UNKNOWN")
        rows: list[tuple[str, str]] = []
        if s not in ("NOT FOUND", "ERROR", "LOADING", "UNKNOWN"):
            rows = [
                ("NAT ID",    d.get("nat_id", "-")),
                ("Public IP", d.get("public_ip", "-")),
                ("Subnet",    d.get("subnet", "-")),
            ]
        self._refresh_card(s, rows, d.get("_detail", ""))

    def apply_addons(self, d: dict) -> None:
        self._last_data = d
        s = d.get("status", "UNKNOWN")
        rows: list[tuple[str, str]] = []
        if s not in ("NOT FOUND", "ERROR", "LOADING", "UNKNOWN"):
            rows = [
                ("Addons", d.get("total", "-")),
                ("Detail", d.get("detail", "-")),
            ]
        self._refresh_card(s, rows, d.get("_detail", ""))

    def apply_security_groups(self, d: dict) -> None:
        self._last_data = d
        s = d.get("status", "UNKNOWN")
        rows: list[tuple[str, str]] = []
        if s not in ("NOT FOUND", "ERROR", "LOADING", "UNKNOWN"):
            rows = [("Count", d.get("count", "-"))]
            for line in (d.get("detail") or "").split("\n"):
                if line.strip():
                    rows.append(("", f"[dim]{line.strip()}[/dim]"))
        self._refresh_card(s, rows, d.get("_detail", ""))

    def apply_s3(self, d: dict) -> None:
        self._last_data = d
        s = d.get("status", "UNKNOWN")
        rows: list[tuple[str, str]] = []
        if s not in ("NOT FOUND", "ERROR", "LOADING", "UNKNOWN"):
            rows = [
                ("Bucket",      d.get("bucket", "-")),
                ("Versioning",  d.get("versioning", "-")),
                ("Encryption",  d.get("encryption", "-")),
                ("Public Blocked", "Yes" if d.get("public_blocked") else "No"),
            ]
        self._refresh_card(s, rows, d.get("_detail", ""))

    def apply_dynamodb(self, d: dict) -> None:
        self._last_data = d
        s = d.get("status", "UNKNOWN")
        rows: list[tuple[str, str]] = []
        if s not in ("NOT FOUND", "ERROR", "LOADING", "UNKNOWN"):
            rows = [
                ("Table",       d.get("table_name", "-")),
                ("Status",      d.get("table_status", "-")),
                ("Billing",     d.get("billing_mode", "-")),
                ("Items",       d.get("item_count", "-")),
                ("Size",        d.get("size_bytes", "-")),
            ]
        self._refresh_card(s, rows, d.get("_detail", ""))


# ─── EnvSummary ───────────────────────────────────────────────────────────────

class EnvSummary(Static):
    """One-line health summary above the cards."""

    DEFAULT_CSS = """
    EnvSummary {
        height: 1;
        padding: 0 1;
        margin: 0 0 0 1;
        color: $text;
    }
    """

    def apply_data(self, data: dict) -> None:
        counts: dict[str, int] = {}
        for resource_data in data.values():
            cat = classify(resource_data.get("status", "UNKNOWN"))
            counts[cat] = counts.get(cat, 0) + 1

        parts: list[str] = []
        if counts.get("healthy"):
            parts.append(f"[green]{counts['healthy']} healthy[/green]")
        if counts.get("transitioning"):
            parts.append(f"[yellow]{counts['transitioning']} transitioning[/yellow]")
        if counts.get("winding_down"):
            parts.append(f"[orange3]{counts['winding_down']} winding down[/orange3]")
        if counts.get("error"):
            parts.append(f"[red]{counts['error']} error[/red]")
        if counts.get("absent"):
            parts.append(f"[dim]{counts['absent']} absent[/dim]")

        total = sum(counts.values())
        self.update(f"  [bold]Resources:[/bold] {total}   |   " + "   ".join(parts))


# ─── EnvPanel ─────────────────────────────────────────────────────────────────

class EnvPanel(Vertical):
    """All cards for a single environment."""

    DEFAULT_CSS = """
    EnvPanel {
        padding: 1 0 0 1;
    }
    """

    def __init__(self, env_key: str, panel_id: str) -> None:
        super().__init__(id=panel_id)
        self._env_key = env_key

    def compose(self) -> ComposeResult:
        cfg = ENV_CONFIG[self._env_key]
        ek = self._env_key
        yield EnvSummary(id=f"{ek}-summary")
        # Row 1: Core compute
        with Horizontal():
            yield ResourceCard("EKS Cluster",      cfg["eks_cluster"], f"{ek}-eks")
            yield ResourceCard("Node Group",        cfg["node_group"],  f"{ek}-ng")
        # Row 2: Data stores
        with Horizontal():
            yield ResourceCard("RDS PostgreSQL",    cfg["rds_id"],      f"{ek}-rds")
            yield ResourceCard("ElastiCache Redis", cfg["redis_id"],    f"{ek}-redis")
        # Row 3: Networking
        with Horizontal():
            yield ResourceCard("VPC",               cfg["vpc_tag"],     f"{ek}-vpc")
            yield ResourceCard("NAT Gateway",       cfg["vpc_tag"],     f"{ek}-nat")
            yield ResourceCard("Security Groups",   cfg["vpc_tag"],     f"{ek}-sgs")
        # Row 4: Platform services
        with Horizontal():
            yield ResourceCard("IAM Roles",         "cluster / node / eso", f"{ek}-iam")
            yield ResourceCard("Secrets Manager",   f"{cfg['secrets'][0].rsplit('/', 1)[0]}/*", f"{ek}-secrets")
            yield ResourceCard("EKS Addons",        "vpc-cni / coredns / kube-proxy", f"{ek}-addons")

    def apply_data(self, data: dict) -> dict[str, tuple[str | None, str]]:
        """Push data into cards and return {resource: (old_status, new_status)} transitions."""
        ek = self._env_key
        cards = {
            "eks":             (self.query_one(f"#{ek}-eks",     ResourceCard), "apply_eks"),
            "nodegroup":       (self.query_one(f"#{ek}-ng",      ResourceCard), "apply_nodegroup"),
            "rds":             (self.query_one(f"#{ek}-rds",     ResourceCard), "apply_rds"),
            "redis":           (self.query_one(f"#{ek}-redis",   ResourceCard), "apply_redis"),
            "vpc":             (self.query_one(f"#{ek}-vpc",     ResourceCard), "apply_vpc"),
            "nat":             (self.query_one(f"#{ek}-nat",     ResourceCard), "apply_nat"),
            "security_groups": (self.query_one(f"#{ek}-sgs",     ResourceCard), "apply_security_groups"),
            "iam":             (self.query_one(f"#{ek}-iam",     ResourceCard), "apply_iam"),
            "secrets":         (self.query_one(f"#{ek}-secrets", ResourceCard), "apply_secrets"),
            "addons":          (self.query_one(f"#{ek}-addons",  ResourceCard), "apply_addons"),
        }
        transitions: dict[str, tuple[str | None, str]] = {}
        for resource_key, (card, method_name) in cards.items():
            d = data.get(resource_key, {})
            old = card.prev_status
            getattr(card, method_name)(d)
            new = d.get("status", "UNKNOWN")
            if old is not None and old != new:
                transitions[resource_key] = (old, new)

        self.query_one(f"#{ek}-summary", EnvSummary).apply_data(data)
        return transitions


# ─── BootstrapPanel ───────────────────────────────────────────────────────────

class BootstrapPanel(Vertical):
    """Cards for Terraform bootstrap resources (S3 + DynamoDB)."""

    DEFAULT_CSS = """
    BootstrapPanel {
        padding: 1 0 0 1;
    }
    """

    def __init__(self, panel_id: str) -> None:
        super().__init__(id=panel_id)

    def compose(self) -> ComposeResult:
        yield EnvSummary(id="boot-summary")
        with Horizontal():
            yield ResourceCard("S3 State Bucket", BOOTSTRAP_CONFIG["s3_bucket"], "boot-s3")
            yield ResourceCard("DynamoDB Lock Table", BOOTSTRAP_CONFIG["dynamodb_table"], "boot-ddb")

    def apply_data(self, data: dict) -> dict[str, tuple[str | None, str]]:
        cards = {
            "s3_bucket":      (self.query_one("#boot-s3",  ResourceCard), "apply_s3"),
            "dynamodb_table": (self.query_one("#boot-ddb", ResourceCard), "apply_dynamodb"),
        }
        transitions: dict[str, tuple[str | None, str]] = {}
        for resource_key, (card, method_name) in cards.items():
            d = data.get(resource_key, {})
            old = card.prev_status
            getattr(card, method_name)(d)
            new = d.get("status", "UNKNOWN")
            if old is not None and old != new:
                transitions[resource_key] = (old, new)

        self.query_one("#boot-summary", EnvSummary).apply_data(data)
        return transitions


# ─── EventLog ─────────────────────────────────────────────────────────────────

class EventLog(Static):
    """Scrollable log of status transitions."""

    DEFAULT_CSS = """
    EventLog {
        height: 100%;
        padding: 0 1;
        overflow-y: auto;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._lines: list[str] = ["[dim]Waiting for first poll...[/dim]"]

    def add_event(self, timestamp: str, env: str, resource: str, old: str, new: str) -> None:
        env_colour = "cyan" if env == "staging" else "magenta"
        line = (
            f"[dim]{timestamp}[/dim]  "
            f"[{env_colour}]{env:<11}[/{env_colour}]  "
            f"[bold]{resource:<10}[/bold]  "
            f"{status_markup(old)} -> {status_markup(new)}"
        )
        self._lines.append(line)
        # Keep last 100 entries
        if len(self._lines) > 100:
            self._lines = self._lines[-100:]
        self.update("\n".join(self._lines))

    def add_note(self, timestamp: str, message: str) -> None:
        line = f"[dim]{timestamp}[/dim]  [yellow]system[/yellow]       [dim]{message}[/dim]"
        self._lines.append(line)
        if len(self._lines) > 100:
            self._lines = self._lines[-100:]
        self.update("\n".join(self._lines))

    def mark_poll(self, timestamp: str) -> None:
        """Add a quiet poll marker only on first load."""
        if self._lines == ["[dim]Waiting for first poll...[/dim]"]:
            self._lines = [f"[dim]{timestamp}  First poll complete. Watching for changes...[/dim]"]
            self.update("\n".join(self._lines))


# ─── K8s workload widgets ────────────────────────────────────────────────────

class DeploymentRow(Static):
    """A single deployment row in the workload table."""

    DEFAULT_CSS = """
    DeploymentRow {
        height: 1;
        padding: 0 1;
    }
    """

    def apply(self, d: dict) -> None:
        name = d.get("name", "?")
        status = d.get("status", "UNKNOWN")
        ready = d.get("ready", 0)
        desired = d.get("desired", 0)
        image = d.get("image", "-")

        status_col = status_markup(status)
        replica_str = f"{ready}/{desired}"
        if ready == desired and desired > 0:
            replica_col = f"[green]{replica_str}[/green]"
        elif ready > 0:
            replica_col = f"[yellow]{replica_str}[/yellow]"
        elif desired == 0:
            replica_col = f"[dim]{replica_str}[/dim]"
        else:
            replica_col = f"[red]{replica_str}[/red]"

        self.update(
            f"  {status_col}  [bold]{name:<28}[/bold]  "
            f"Replicas: {replica_col:<16}  "
            f"Image: [dim]{image}[/dim]"
        )


class WorkloadPanel(Vertical):
    """All K8s workload info for a single environment."""

    DEFAULT_CSS = """
    WorkloadPanel {
        padding: 1 0 0 1;
    }
    """

    def __init__(self, env_key: str, panel_id: str) -> None:
        super().__init__(id=panel_id)
        self._env_key = env_key

    def compose(self) -> ComposeResult:
        ek = self._env_key
        cfg = ENV_CONFIG[ek]
        # Summary header
        yield Static(
            f"[bold]Namespace:[/bold] {cfg['namespace']}   "
            f"[bold]Cluster:[/bold] {cfg['eks_cluster']}",
            id=f"{ek}-k8s-header",
        )
        yield Static("", id=f"{ek}-k8s-summary")
        # Access URLs section
        yield Static(
            "\n[bold]Access URLs[/bold]  "
            "[dim](from Ingress / LoadBalancer services)[/dim]",
            id=f"{ek}-urls-header",
        )
        yield Static("[dim]  Loading...[/dim]", id=f"{ek}-urls")
        # Table header
        yield Static(
            "\n[bold dim]  ──  SERVICE                          "
            "REPLICAS          IMAGE[/bold dim]",
        )
        # One row per expected deployment
        for svc_name in DEPLOYMENTS:
            yield DeploymentRow(id=f"{ek}-dep-{svc_name}")
        # Connectivity section
        yield Static(
            "\n[bold]Data-Layer Connectivity[/bold]  "
            "[dim](inferred from db-access / notification pod health)[/dim]",
            id=f"{ek}-conn-header",
        )
        yield Static("", id=f"{ek}-conn-rds")
        yield Static("", id=f"{ek}-conn-redis")
        # Warning events section
        yield Static("", id=f"{ek}-k8s-events")

    def apply_data(self, data: dict) -> None:
        """Push K8s workload data into widgets."""
        ek = self._env_key

        # Update summary
        summary = data.get("summary", "-")
        pods_total = data.get("pods_total", 0)
        pods_ready = data.get("pods_ready", 0)
        status = data.get("status", "UNKNOWN")

        summary_parts = [f"  {status_markup(status)}  [bold]{summary}[/bold]"]
        if pods_total > 0:
            if pods_ready == pods_total:
                summary_parts.append(f"   Pods: [green]{pods_ready}/{pods_total}[/green]")
            else:
                summary_parts.append(f"   Pods: [yellow]{pods_ready}/{pods_total}[/yellow]")
        self.query_one(f"#{ek}-k8s-summary", Static).update("".join(summary_parts))

        # Update each deployment row
        dep_by_name = {d["name"]: d for d in data.get("deployments", [])}
        for svc_name in DEPLOYMENTS:
            row = self.query_one(f"#{ek}-dep-{svc_name}", DeploymentRow)
            dep_data = dep_by_name.get(svc_name, {
                "name": svc_name, "status": "UNKNOWN",
                "ready": 0, "desired": 0, "image": "-",
            })
            row.apply(dep_data)

        # Update warning events
        events = data.get("recent_events", [])
        if events:
            event_lines = ["\n[bold yellow]⚠  Recent Warnings:[/bold yellow]"]
            for ev in events[:8]:
                event_lines.append(f"  [dim]{ev}[/dim]")
            self.query_one(f"#{ek}-k8s-events", Static).update("\n".join(event_lines))
        else:
            self.query_one(f"#{ek}-k8s-events", Static).update(
                "\n[dim]No warning events[/dim]"
            )

        # Update connectivity section
        conn = data.get("connectivity", {})
        # RDS connectivity (aggregate from all db-access services)
        rds_svcs = ["user-db-access-service", "job-db-access-service-deployment", "customer-db-access-service"]
        rds_lines = ["  [bold]RDS (PostgreSQL):[/bold]"]
        for svc in rds_svcs:
            c = conn.get(svc, {"status": "UNKNOWN", "detail": "-"})
            rds_lines.append(f"    {status_markup(c['status'])}  {svc}: {c['detail']}")
        self.query_one(f"#{ek}-conn-rds", Static).update("\n".join(rds_lines))

        # Redis connectivity (from notification-service)
        redis_c = conn.get("notification-service", {"status": "UNKNOWN", "detail": "-"})
        self.query_one(f"#{ek}-conn-redis", Static).update(
            f"  [bold]ElastiCache (Redis):[/bold]\n"
            f"    {status_markup(redis_c['status'])}  notification-service: {redis_c['detail']}"
        )

        # Update access URLs
        urls = data.get("access_urls", [])
        if urls:
            url_lines = []
            for u in urls:
                addr = u.get("address", "-")
                name = u.get("name", "?")
                utype = u.get("type", "?")
                host = u.get("host", "-")
                if addr and addr != "-":
                    url_display = f"http://{addr}"
                    if host and host != "-":
                        url_display += f"  (Host: {host})"
                    url_lines.append(
                        f"  [green]●[/green]  [{utype}] [bold]{name}[/bold]  →  [cyan underline]{url_display}[/cyan underline]"
                    )
                else:
                    url_lines.append(
                        f"  [yellow]◌[/yellow]  [{utype}] [bold]{name}[/bold]  →  [dim]<pending>[/dim]"
                    )
            self.query_one(f"#{ek}-urls", Static).update("\n".join(url_lines))
        else:
            self.query_one(f"#{ek}-urls", Static).update(
                "  [dim]No Ingress or LoadBalancer services found[/dim]"
            )
