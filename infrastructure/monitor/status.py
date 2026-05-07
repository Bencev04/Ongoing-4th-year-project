"""Status styling helpers for Rich / Textual markup."""
from __future__ import annotations

# ─── Colour mapping ───────────────────────────────────────────────────────────

_COLOURS: dict[str, str] = {
    # Healthy
    "ACTIVE":        "bold green",
    "available":     "bold green",
    # Transitioning
    "CREATING":      "bold yellow",
    "UPDATING":      "bold yellow",
    "PENDING":       "bold yellow",
    "creating":      "bold yellow",
    "modifying":     "bold yellow",
    "backing-up":    "bold yellow",
    "rebooting":     "bold yellow",
    "maintenance":   "bold yellow",
    "snapshotting":  "bold yellow",
    # Partial
    "PARTIAL":       "bold yellow",
    # Winding down / scaled
    "DELETING":      "bold dark_orange",
    "deleting":      "bold dark_orange",
    "stopping":      "bold dark_orange",
    "SCALED_DOWN":   "bold dark_orange",
    # Error / down
    "FAILED":        "bold red",
    "failed":        "bold red",
    "stopped":       "bold red",
    "DEGRADED":      "bold red",
    "DELETE_FAILED": "bold red",
    "CREATE_FAILED": "bold red",
    "ERROR":         "bold red",
    # Absent / loading
    "NOT FOUND":     "dim",
    "LOADING":       "italic dim",
    "UNKNOWN":       "dim",
}

_ICONS: dict[str, str] = {
    "ACTIVE":        "●",
    "available":     "●",
    "CREATING":      "◌",
    "creating":      "◌",
    "UPDATING":      "◌",
    "modifying":     "◌",
    "backing-up":    "◌",
    "rebooting":     "◌",
    "maintenance":   "◌",
    "snapshotting":  "◌",
    "PARTIAL":       "◐",
    "DELETING":      "◍",
    "deleting":      "◍",
    "stopping":      "◍",
    "SCALED_DOWN":   "▽",
    "PENDING":       "◍",
    "FAILED":        "X",
    "failed":        "X",
    "stopped":       "X",
    "DEGRADED":      "X",
    "DELETE_FAILED": "X",
    "CREATE_FAILED": "X",
    "ERROR":         "!",
    "NOT FOUND":     "-",
    "LOADING":       "...",
    "UNKNOWN":       "?",
}


def status_markup(status: str) -> str:
    """Return Rich-markup string with coloured icon + status text."""
    colour = _COLOURS.get(status, "white")
    icon = _ICONS.get(status, "?")
    return f"[{colour}]{icon} {status}[/{colour}]"


# ─── Health classification ────────────────────────────────────────────────────

_HEALTHY = {"ACTIVE", "available"}
_TRANSITIONING = {
    "CREATING", "UPDATING", "PENDING",
    "creating", "modifying", "backing-up", "rebooting",
    "maintenance", "snapshotting",
}
_WINDING_DOWN = {"DELETING", "deleting", "stopping", "SCALED_DOWN"}
_PARTIAL = {"PARTIAL"}
_ERROR = {
    "FAILED", "failed", "stopped", "DEGRADED",
    "DELETE_FAILED", "CREATE_FAILED", "ERROR",
}
_ABSENT = {"NOT FOUND", "LOADING", "UNKNOWN"}


def classify(status: str) -> str:
    """Return one of: healthy, transitioning, winding_down, error, absent."""
    if status in _HEALTHY:
        return "healthy"
    if status in _TRANSITIONING or status in _PARTIAL:
        return "transitioning"
    if status in _WINDING_DOWN:
        return "winding_down"
    if status in _ERROR:
        return "error"
    return "absent"
