"""
AWS Infrastructure Monitor - Textual App
-----------------------------------------
Real-time TUI dashboard for watching staging and production AWS resources.

Key bindings:
    s       Switch to Staging tab
    p       Switch to Production tab
    l       Switch to Event Log tab
    r       Force-refresh now
    q       Quit
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer
from textual.widgets import Footer, Header, Label, TabbedContent, TabPane

from monitor.aws import fetch_bootstrap, fetch_environment
from monitor.config import BOOTSTRAP_CONFIG, ENV_CONFIG, REFRESH_SECONDS, REGION
from monitor.k8s import fetch_k8s_for_env
from monitor.widgets import BootstrapPanel, EnvPanel, EventLog, ResourceCard, WorkloadPanel


class InfraMonitor(App[None]):
    """yr4-project AWS Infrastructure Monitor."""

    TITLE = "yr4-project  |  AWS Infrastructure Monitor"

    CSS = """
    Screen {
        background: #0b1220;
        color: #f5f7ff;
    }

    Header {
        background: #1e3a8a;
        color: #ffffff;
    }

    HeaderTitle {
        color: #ffffff;
        text-style: bold;
    }

    Footer {
        background: #111827;
        color: #dbeafe;
    }

    #statusbar {
        height: 1;
        background: #1f2a44;
        color: #dce6ff;
        padding: 0 2;
    }

    TabbedContent {
        height: 1fr;
        background: #0b1220;
        color: #f5f7ff;
    }

    Tabs {
        background: #101827;
        color: #dbeafe;
    }

    Tab {
        color: #dbeafe;
    }

    Tab.-active {
        background: #2563eb;
        color: #ffffff;
        text-style: bold;
    }

    TabPane {
        padding: 0;
    }

    #log-container {
        padding: 1;
    }

    #detail-panel {
        display: none;
        dock: bottom;
        height: 12;
        border-top: solid #5da8ff;
        background: #111a2e;
        padding: 1 2;
        overflow-y: auto;
    }

    #detail-panel.visible {
        display: block;
    }
    """

    BINDINGS = [
        Binding("s", "goto_staging",    "Staging",    show=True),
        Binding("p", "goto_production", "Production", show=True),
        Binding("w", "goto_workloads",  "Workloads",  show=True),
        Binding("b", "goto_bootstrap",  "Bootstrap",  show=True),
        Binding("l", "goto_log",        "Log",        show=True),
        Binding("r", "force_refresh",   "Refresh",    show=True),
        Binding("escape", "close_detail", "Close",    show=False),
        Binding("q", "quit",            "Quit",       show=True),
    ]

    def __init__(
        self,
        profile: str | None = None,
        region: str = REGION,
        refresh: int = REFRESH_SECONDS,
    ) -> None:
        super().__init__()
        self._profile = profile
        self._region = region
        self._refresh_seconds = refresh
        self._last_updated: str = "-"
        self._countdown: int = refresh
        self._refresh_timer = None
        self._refresh_lock = asyncio.Lock()
        self.sub_title = f"Region: {region}"

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("", id="statusbar")
        with TabbedContent(id="tabs"):
            with TabPane("  Staging  ", id="tab-staging"):
                with ScrollableContainer():
                    yield EnvPanel("staging", "panel-staging")
            with TabPane("  Production  ", id="tab-production"):
                with ScrollableContainer():
                    yield EnvPanel("production", "panel-production")
            with TabPane("  Workloads  ", id="tab-workloads"):
                with ScrollableContainer():
                    yield WorkloadPanel("staging", "wk-staging")
                    yield WorkloadPanel("production", "wk-production")
            with TabPane("  Bootstrap  ", id="tab-bootstrap"):
                with ScrollableContainer():
                    yield BootstrapPanel("panel-bootstrap")
            with TabPane("  Event Log  ", id="tab-log"):
                with ScrollableContainer(id="log-container"):
                    yield EventLog(id="event-log")
        yield Label("", id="detail-panel")
        yield Footer()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def on_mount(self) -> None:
        self._update_statusbar()
        self._refresh_timer = self.set_interval(
            self._refresh_seconds, self._timed_refresh,
        )
        self.set_interval(1, self._tick)
        # Do not block first paint on network calls; fetch in background.
        self._schedule_refresh()

    # ── Timers ────────────────────────────────────────────────────────────────

    async def _tick(self) -> None:
        self._countdown = max(0, self._countdown - 1)
        self._update_statusbar()

    async def _timed_refresh(self) -> None:
        self._countdown = self._refresh_seconds
        self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        asyncio.create_task(self._safe_fetch_and_apply())

    async def _safe_fetch_and_apply(self) -> None:
        async with self._refresh_lock:
            try:
                await self._fetch_and_apply()
            except Exception as exc:
                self._last_updated = "error"
                event_log = self.query_one("#event-log", EventLog)
                event_log.add_note(datetime.now().strftime("%H:%M:%S"), f"Refresh failed: {exc}")
                self._update_statusbar()

    # ── Data fetching ─────────────────────────────────────────────────────────

    async def _fetch_and_apply(self) -> None:
        staging_data, prod_data, k8s_stg, k8s_prod, bootstrap_data = await asyncio.gather(
            fetch_environment("staging", self._profile, self._region),
            fetch_environment("production", self._profile, self._region),
            fetch_k8s_for_env("staging", self._profile, self._region),
            fetch_k8s_for_env("production", self._profile, self._region),
            fetch_bootstrap(self._profile, self._region),
        )
        now = datetime.now().strftime("%H:%M:%S")
        self._last_updated = now

        stg_panel = self.query_one("#panel-staging", EnvPanel)
        prd_panel = self.query_one("#panel-production", EnvPanel)
        event_log = self.query_one("#event-log", EventLog)

        stg_transitions = stg_panel.apply_data(staging_data)
        prd_transitions = prd_panel.apply_data(prod_data)

        # Apply K8s workload data
        self.query_one("#wk-staging", WorkloadPanel).apply_data(k8s_stg)
        self.query_one("#wk-production", WorkloadPanel).apply_data(k8s_prod)

        # Apply bootstrap data
        boot_transitions = self.query_one("#panel-bootstrap", BootstrapPanel).apply_data(bootstrap_data)

        for resource, (old, new) in stg_transitions.items():
            event_log.add_event(now, "staging", resource, old, new)
        for resource, (old, new) in prd_transitions.items():
            event_log.add_event(now, "production", resource, old, new)

        for resource, (old, new) in boot_transitions.items():
            event_log.add_event(now, "bootstrap", resource, old, new)

        if not stg_transitions and not prd_transitions and not boot_transitions:
            event_log.mark_poll(now)

        self._update_statusbar()

    # ── Status bar ────────────────────────────────────────────────────────────

    def _update_statusbar(self) -> None:
        profile_str = self._profile or "default"
        self.query_one("#statusbar", Label).update(
            f"  [dim]Region:[/dim] {self._region}   "
            f"[dim]Profile:[/dim] {profile_str}   "
            f"[dim]Updated:[/dim] {self._last_updated}   "
            f"[dim]Next refresh:[/dim] [bold]{self._countdown}s[/bold]"
        )

    # ── Key actions ───────────────────────────────────────────────────────────

    def action_goto_staging(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-staging"

    def action_goto_production(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-production"

    def action_goto_workloads(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-workloads"

    def action_goto_bootstrap(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-bootstrap"

    def action_goto_log(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-log"

    async def action_force_refresh(self) -> None:
        self._countdown = self._refresh_seconds
        if self._refresh_timer is not None:
            self._refresh_timer.stop()
            self._refresh_timer = self.set_interval(
                self._refresh_seconds, self._timed_refresh,
            )
        self._schedule_refresh()

    def action_close_detail(self) -> None:
        panel = self.query_one("#detail-panel", Label)
        panel.remove_class("visible")

    # ── Card click handler ────────────────────────────────────────────────────

    def on_resource_card_selected(self, event: ResourceCard.Selected) -> None:
        """Show a detail panel when a resource card is clicked."""
        data = event.data
        lines = [
            f"[bold underline]{event.card_title}[/bold underline]  ({event.card_id})",
            "",
        ]
        if not data:
            lines.append("[dim]No data available yet[/dim]")
        else:
            for key, value in data.items():
                if key.startswith("_"):
                    continue
                lines.append(f"  [bold]{key:<18}[/bold] {value}")

        lines.append("")
        lines.append("[dim]Press Escape to close[/dim]")

        panel = self.query_one("#detail-panel", Label)
        panel.update("\n".join(lines))
        panel.add_class("visible")


# ─── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Real-time AWS infrastructure monitor for yr4-project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m monitor\n"
            "  python -m monitor --profile my-aws-profile\n"
            "  python -m monitor --refresh 5\n"
        ),
    )
    parser.add_argument(
        "--profile", metavar="NAME", default=None,
        help="AWS CLI profile name (default: env credentials / default profile)",
    )
    parser.add_argument(
        "--region", metavar="REGION", default=REGION,
        help=f"AWS region (default: {REGION})",
    )
    parser.add_argument(
        "--refresh", metavar="SECS", type=int, default=REFRESH_SECONDS,
        help=f"Auto-refresh interval in seconds (default: {REFRESH_SECONDS})",
    )
    parser.add_argument(
        "--alt-screen", action="store_true",
        help="Use alternate-screen mode (default is inline mode for terminal compatibility)",
    )
    parser.add_argument(
        "--plain", action="store_true",
        help="Print a one-shot plain-text status snapshot (no TUI)",
    )
    args = parser.parse_args()

    if args.plain:
        asyncio.run(_print_plain_snapshot(args.profile, args.region))
        return

    InfraMonitor(
        profile=args.profile,
        region=args.region,
        refresh=args.refresh,
    ).run(inline=not args.alt_screen)


async def _print_plain_snapshot(profile: str | None, region: str) -> None:
    staging_data, prod_data, k8s_stg, k8s_prod, bootstrap_data = await asyncio.gather(
        fetch_environment("staging", profile, region),
        fetch_environment("production", profile, region),
        fetch_k8s_for_env("staging", profile, region),
        fetch_k8s_for_env("production", profile, region),
        fetch_bootstrap(profile, region),
    )

    def _status(d: dict, key: str) -> str:
        v = d.get(key, {})
        if isinstance(v, dict):
            return str(v.get("status", "UNKNOWN"))
        return "UNKNOWN"

    def _print_env(name: str, data: dict, k8s: dict) -> None:
        print(f"\n{name.upper()}:")
        for key in (
            "eks", "nodegroup", "rds", "redis", "vpc", "nat", "security_groups", "iam", "secrets", "addons"
        ):
            print(f"  {key:<16} {_status(data, key)}")
        print(f"  {'k8s_workloads':<16} {k8s.get('status', 'UNKNOWN')}")
        if k8s.get("_detail"):
            print(f"    detail: {k8s['_detail']}")

    print(f"yr4-project monitor snapshot  |  region={region}  |  profile={profile or 'default'}")
    print("\nBOOTSTRAP:")
    print(f"  {'s3_bucket':<16} {_status(bootstrap_data, 's3_bucket')}")
    print(f"  {'dynamodb_table':<16} {_status(bootstrap_data, 'dynamodb_table')}")

    _print_env("staging", staging_data, k8s_stg)
    _print_env("production", prod_data, k8s_prod)


if __name__ == "__main__":
    main()
