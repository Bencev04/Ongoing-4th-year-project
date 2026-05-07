"""Calendar page routes.

Serves the full-page calendar view and HTMX partial templates used
for month navigation, day details, the job queue sidebar, and the
job create/edit modal.

Supports three calendar views:

- **Month view** — 42-cell grid (6 weeks × 7 days) with events
  populated server-side from job-bl-service.
- **Week view**  — 7-column × 17-row (06:00–22:00) time-slot grid.
- **Day view**   — single-column timeline for one date.

Events that span multiple days are expanded across every day cell
they touch, with ``is_first_day`` / ``is_last_day`` /
``is_continuation`` flags for template styling.

Routes
------
GET /calendar                – Full calendar page (month view).
GET /calendar/container      – HTMX partial: header + grid (month).
GET /calendar/grid           – HTMX partial: bare grid only.
GET /calendar/week           – HTMX partial: week view.
GET /calendar/day-view/{d}   – HTMX partial: day timeline view.
GET /calendar/day/{date}     – Day-detail modal partial.
GET /calendar/job-queue      – Unscheduled-job sidebar partial.
GET /calendar/job-modal      – Job create / edit modal partial.
GET /calendar/quick-schedule-modal – Quick-schedule drag-and-drop modal.
GET /calendar/prev           – Redirect → previous month.
GET /calendar/next           – Redirect → next month.
GET /calendar/{year}/{month} – Full page for a specific month.
"""

from __future__ import annotations

import asyncio
import calendar as cal
import json
import logging
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import service_client
from ..template_config import get_templates

logger = logging.getLogger(__name__)

# ── Template engine ──────────────────────────────────────────────────────────
templates = get_templates()

router = APIRouter(tags=["calendar"])

# Type alias for a single calendar-day cell passed to the Jinja template.
CalendarDay = dict[str, object]

# Weekday header labels (Monday-first ISO week).
WEEKDAYS: list[str] = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ── Helpers ──────────────────────────────────────────────────────────────────


def _build_day_cell(
    day_date: date,
    is_current_month: bool,
    today: date,
) -> CalendarDay:
    """Create the dict for a single calendar grid cell.

    Args:
        day_date:         The date this cell represents.
        is_current_month: ``True`` when the date falls in the viewed month.
        today:            Today's date (for highlighting).

    Returns:
        A dict consumed by the ``calendar_grid.html`` template.
    """
    return {
        "date": day_date,
        "day": day_date.day,
        "is_current_month": is_current_month,
        "is_today": day_date == today,
        "events": [],
    }


def get_calendar_days(year: int, month: int) -> list[CalendarDay]:
    """Generate a 6-row (42-cell) calendar grid for the given month.

    The grid is padded with trailing/leading days from the adjacent
    months so that every row is a complete week (Mon → Sun).

    Args:
        year:  Calendar year  (e.g. 2026).
        month: Calendar month (1–12).

    Returns:
        A list of 42 ``CalendarDay`` dicts.
    """
    first_day = date(year, month, 1)
    _, days_in_month = cal.monthrange(year, month)

    # Weekday of the 1st (0 = Monday in ISO)
    start_weekday: int = first_day.weekday()

    today: date = date.today()
    days: list[CalendarDay] = []

    # ── Previous-month padding ───────────────────────────────────────
    if start_weekday > 0:
        pad_start: date = first_day - timedelta(days=start_weekday)
        for i in range(start_weekday):
            days.append(_build_day_cell(pad_start + timedelta(days=i), False, today))

    # ── Current-month days ───────────────────────────────────────────
    for day_num in range(1, days_in_month + 1):
        days.append(_build_day_cell(date(year, month, day_num), True, today))

    # ── Next-month padding (fill to 42 cells) ────────────────────────
    remaining: int = 42 - len(days)
    if remaining > 0:
        next_month_start: date = date(year, month, days_in_month) + timedelta(days=1)
        for i in range(remaining):
            days.append(
                _build_day_cell(next_month_start + timedelta(days=i), False, today)
            )

    return days


def _parse_event_date(raw: str | date | datetime | None) -> date | None:
    """Coerce a date-like value from the API into a ``date`` object.

    The calendar API may return ISO strings, ``date``, or ``datetime``
    objects depending on serialisation.  This helper normalises them.

    Args:
        raw: The value to parse.

    Returns:
        A ``date`` object, or ``None`` if unparseable.
    """
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    try:
        return datetime.fromisoformat(str(raw)).date()
    except (ValueError, TypeError):
        return None


def _format_display_time(raw: str | datetime | None) -> str | None:
    """Extract an ``HH:MM`` time string from an ISO datetime value.

    The calendar API returns full ISO-8601 timestamps (e.g.
    ``2026-03-16T08:00:00Z``).  Templates only need the ``HH:MM``
    portion for compact event chips.

    Args:
        raw: ISO datetime string, ``datetime`` object, or ``None``.

    Returns:
        ``"HH:MM"`` string, or ``None`` if unparseable / absent.
    """
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.strftime("%H:%M")
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt.strftime("%H:%M")
    except (ValueError, TypeError):
        return None


def _expand_events_into_days(
    api_days: list[dict[str, Any]],
    calendar_days: list[CalendarDay],
    emp_lookup: dict[int, str] | None = None,
    cust_lookup: dict[int, str] | None = None,
) -> None:
    """Distribute API events across calendar grid cells (mutates in-place).

    For each event returned by the calendar API, the event is placed
    into **every** grid cell whose date falls within the event's
    ``start_time`` → ``end_time`` range.  Multi-day events receive
    ``is_first_day`` / ``is_last_day`` / ``is_continuation`` flags
    that templates use for visual spanning.

    Args:
        api_days:      The raw list of day-dicts from the calendar API.
        calendar_days: The 42-cell grid (mutated in-place to add events).
        emp_lookup:    Optional employee ID → name lookup for enrichment.
        cust_lookup:   Optional customer ID → name lookup for enrichment.
    """
    # Build a lookup from date → grid cell for O(1) insertion.
    date_to_cell: dict[date, CalendarDay] = {}
    for cell in calendar_days:
        cell_date = cell.get("date")
        if isinstance(cell_date, date):
            date_to_cell[cell_date] = cell

    # Collect all unique events across API days (keyed by id).
    seen_ids: set[int] = set()
    all_events: list[dict[str, Any]] = []
    for day_data in api_days:
        for job in day_data.get("jobs", []):
            job_id = job.get("id")
            if job_id is not None and job_id not in seen_ids:
                seen_ids.add(job_id)
                all_events.append(job)

    for event in all_events:
        start_dt = _parse_event_date(event.get("start_time"))
        end_dt = _parse_event_date(event.get("end_time"))

        if start_dt is None:
            continue  # Unscheduled jobs don't appear on the grid.

        # If no end_time, treat as a single-day event.
        if end_dt is None:
            end_dt = start_dt

        is_multi_day: bool = end_dt > start_dt

        # Walk each date in the event's range.
        current = start_dt
        while current <= end_dt:
            cell = date_to_cell.get(current)
            if cell is not None:
                event_copy: dict[str, Any] = {
                    **event,
                    # Override raw ISO timestamps with compact HH:MM display.
                    "start_time": _format_display_time(event.get("start_time")),
                    "end_time": _format_display_time(event.get("end_time")),
                    "is_first_day": current == start_dt,
                    "is_last_day": current == end_dt,
                    "is_continuation": current != start_dt,
                    "is_multi_day": is_multi_day,
                    "employee_name": (
                        emp_lookup.get(event.get("assigned_to", 0), "")
                        if emp_lookup
                        else ""
                    ),
                    "customer_name": (
                        cust_lookup.get(event.get("customer_id", 0), "")
                        if cust_lookup
                        else ""
                    ),
                }
                cell["events"].append(event_copy)  # type: ignore[union-attr]
            current += timedelta(days=1)


def _month_context(year: int, month: int) -> dict[str, object]:
    """Compute the shared template context for a given month.

    This is a pure function — it builds the grid **without** events.
    Events are injected afterwards by the route handler via
    :func:`_expand_events_into_days`.

    Args:
        year:  Calendar year.
        month: Calendar month (1–12).

    Returns:
        Dict containing year, month, navigation values, day grid, etc.
    """
    current_date = date(year, month, 1)
    prev_date = current_date - timedelta(days=1)

    # Jump to the 1st of the next month.
    next_date = current_date + timedelta(days=32)
    next_date = date(next_date.year, next_date.month, 1)

    return {
        "year": year,
        "month": month,
        "month_name": current_date.strftime("%B"),
        "prev_year": prev_date.year,
        "prev_month": prev_date.month,
        "next_year": next_date.year,
        "next_month": next_date.month,
        "calendar_days": get_calendar_days(year, month),
        "weekdays": WEEKDAYS,
        "current_view": "month",
    }


def _parse_ids(raw: str | None) -> list[int] | None:
    """Parse a comma-separated string of IDs into a list of ints.

    Args:
        raw: Comma-separated ID string (e.g. ``"1,3,5"``), or ``None``.

    Returns:
        List of integer IDs, or ``None`` if the input is empty/None.
    """
    if not raw:
        return None
    ids = [int(x) for x in raw.split(",") if x.strip().isdigit()]
    return ids or None


async def _inject_events(
    request: Request,
    context: dict[str, Any],
    employee_ids: list[int] | None = None,
    customer_ids: list[int] | None = None,
) -> None:
    """Fetch events from job-bl-service and inject into grid cells.

    Also fetches employee/customer lists for name enrichment and
    filter dropdowns, then builds week-grouped spanning data for
    the month template.

    Args:
        request:      The incoming browser request (auth forwarding).
        context:      The month context dict containing ``calendar_days``.
        employee_ids: Optional list of employee IDs to filter by.
        customer_ids: Optional list of customer IDs to filter by.
    """
    calendar_days: list[CalendarDay] = context["calendar_days"]  # type: ignore[assignment]
    if not calendar_days:
        return

    # Determine the date range covered by the grid (first cell → last cell).
    first_cell_date: date = calendar_days[0]["date"]  # type: ignore[assignment]
    last_cell_date: date = calendar_days[-1]["date"]  # type: ignore[assignment]

    # Fetch events, employees, and customers concurrently.
    api_days, employees, customers = await asyncio.gather(
        service_client.fetch_calendar_events(request, first_cell_date, last_cell_date),
        service_client.fetch_employees(request),
        service_client.fetch_customers(request),
    )

    # Apply filters.
    api_days = _filter_api_jobs(api_days, employee_ids, customer_ids)

    # Build name lookups for enrichment.
    emp_lookup, cust_lookup = _build_name_lookups(employees, customers)

    # Expand events into day cells with name enrichment.
    _expand_events_into_days(api_days, calendar_days, emp_lookup, cust_lookup)

    # Build week rows with spanning segments for the month template.
    context["calendar_weeks"] = _build_calendar_weeks(calendar_days)
    context["employees"] = employees
    context["customers"] = customers


def _week_dates(year: int, month: int, day: int) -> list[date]:
    """Return the Mon–Sun week containing the given date.

    Args:
        year:  Calendar year.
        month: Calendar month (1–12).
        day:   Day of the month.

    Returns:
        List of 7 ``date`` objects (Monday first).
    """
    target = date(year, month, day)
    monday = target - timedelta(days=target.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


# Time slots for week / day timeline views (06:00 → 22:00, 30-min).
HOUR_SLOTS: list[str] = []
for _h in range(6, 23):
    HOUR_SLOTS.append(f"{_h:02d}:00")
    HOUR_SLOTS.append(f"{_h:02d}:30")

# Total number of 30-min slots in the grid.
_TOTAL_SLOTS: int = len(HOUR_SLOTS)

# First hour shown on the grid (used to compute slot offsets).
_GRID_START_HOUR: int = 6


def _time_to_slot_index(time_str: str | None) -> int | None:
    """Convert an ``HH:MM`` string to a slot index.

    Slot 0 corresponds to 06:00, slot 1 to 06:30, etc.

    Args:
        time_str: Time in ``HH:MM`` format, or ``None``.

    Returns:
        A zero-based slot index clamped to the grid range, or
        ``None`` when *time_str* is absent / unparseable.
    """
    if not time_str:
        return None
    try:
        parts = time_str.split(":")
        h, m = int(parts[0]), int(parts[1])
        slot = (h - _GRID_START_HOUR) * 2 + (1 if m >= 30 else 0)
        return max(0, min(slot, _TOTAL_SLOTS - 1))
    except (ValueError, IndexError):
        return None


# ── Filtering & enrichment helpers ────────────────────────────────────────────


def _filter_api_jobs(
    api_days: list[dict[str, Any]],
    employee_ids: list[int] | None = None,
    customer_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Filter API day entries to only include jobs matching the criteria.

    Args:
        api_days:     List of day dicts from the calendar API.
        employee_ids: If given, only include jobs assigned to these employees.
        customer_ids: If given, only include jobs linked to these customers.

    Returns:
        Filtered copy of api_days.
    """
    if not employee_ids and not customer_ids:
        return api_days
    result: list[dict[str, Any]] = []
    for day_data in api_days:
        filtered_jobs = [
            job
            for job in day_data.get("jobs", [])
            if (not employee_ids or job.get("assigned_to") in employee_ids)
            and (not customer_ids or job.get("customer_id") in customer_ids)
        ]
        result.append(
            {**day_data, "jobs": filtered_jobs, "total_jobs": len(filtered_jobs)}
        )
    return result


def _build_name_lookups(
    employees: list[dict[str, Any]],
    customers: list[dict[str, Any]],
) -> tuple[dict[int, str], dict[int, str]]:
    """Build ID → display-name dicts from employee and customer lists.

    Args:
        employees: List of employee dicts from user-bl-service.
        customers: List of customer dicts from customer-bl-service.

    Returns:
        Tuple of (employee_lookup, customer_lookup).
    """
    emp_lookup: dict[int, str] = {}
    for e in employees:
        eid = e.get("id")
        name = (
            e.get("name")
            or f"{e.get('first_name', '')} {e.get('last_name', '')}".strip()
        )
        if eid and name:
            emp_lookup[int(eid)] = name

    cust_lookup: dict[int, str] = {}
    for c in customers:
        cid = c.get("id")
        name = (
            c.get("name")
            or f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
        )
        if cid and name:
            cust_lookup[int(cid)] = name

    return emp_lookup, cust_lookup


# ── Month view spanning helpers ──────────────────────────────────────────────


def _build_calendar_weeks(
    calendar_days: list[CalendarDay],
) -> list[dict[str, Any]]:
    """Group 42 calendar cells into 6 week rows with spanning event segments.

    Multi-day events are extracted from individual day cells and
    converted into horizontal spanning-bar segments positioned by
    column offset and lane.  Single-day events remain in their cells
    under the ``single_events`` key.

    Args:
        calendar_days: 42 CalendarDay dicts with events already populated.

    Returns:
        List of 6 week dicts with ``days``, ``spanning_events``,
        and ``max_lanes``.
    """
    weeks: list[dict[str, Any]] = []
    for i in range(0, 42, 7):
        weeks.append(
            {
                "cells": calendar_days[i : i + 7],
                "segments": [],
                "max_lanes": 0,
            }
        )

    # Map date → (week_index, column_index).
    date_to_pos: dict[date, tuple[int, int]] = {}
    for w_idx, week in enumerate(weeks):
        for col, day_cell in enumerate(week["cells"]):
            d = day_cell.get("date")
            if isinstance(d, date):
                date_to_pos[d] = (w_idx, col)

    # Collect unique multi-day events and track which cells they appear in.
    seen: set[int] = set()
    multi_events: list[dict[str, Any]] = []
    event_dates: dict[int, list[date]] = {}

    for day_cell in calendar_days:
        cell_date = day_cell.get("date")
        cell_events: list[dict[str, Any]] = day_cell.get("events", [])  # type: ignore[assignment]
        for ev in cell_events:
            ev_id = ev.get("id")
            if ev_id is None or not ev.get("is_multi_day"):
                continue
            if ev_id not in seen:
                seen.add(ev_id)
                multi_events.append(ev)
                event_dates[ev_id] = []
            if isinstance(cell_date, date):
                event_dates.setdefault(ev_id, []).append(cell_date)

    # Create spanning segments (split at week-row boundaries).
    for ev in multi_events:
        dates = sorted(event_dates.get(ev.get("id", 0), []))
        if not dates:
            continue
        ev_start, ev_end = dates[0], dates[-1]
        cur = ev_start
        while cur <= ev_end:
            pos = date_to_pos.get(cur)
            if pos is None:
                cur += timedelta(days=1)
                continue
            w_idx, start_col = pos
            span = min(7 - start_col, (ev_end - cur).days + 1)

            weeks[w_idx]["segments"].append(
                {
                    "id": ev.get("id"),
                    "title": ev.get("title", ""),
                    "start_time": ev.get("start_time"),
                    "end_time": ev.get("end_time"),
                    "status": ev.get("status", ""),
                    "priority": ev.get("priority", ""),
                    "color": ev.get("color"),
                    "customer_name": ev.get("customer_name", ""),
                    "employee_name": ev.get("employee_name", ""),
                    "start_col": start_col,
                    "span": span,
                    "is_start": cur == ev_start,
                    "is_end": (cur + timedelta(days=span - 1)) >= ev_end,
                    "lane": 0,
                }
            )
            cur += timedelta(days=span)

    # Greedy lane assignment per week row.
    for week in weeks:
        segs = week["segments"]
        segs.sort(key=lambda s: (s["start_col"], -s["span"]))
        lane_ends: list[int] = []
        for seg in segs:
            assigned = False
            for li, end_col in enumerate(lane_ends):
                if seg["start_col"] > end_col:
                    seg["lane"] = li
                    lane_ends[li] = seg["start_col"] + seg["span"] - 1
                    assigned = True
                    break
            if not assigned:
                seg["lane"] = len(lane_ends)
                lane_ends.append(seg["start_col"] + seg["span"] - 1)
        week["max_lanes"] = len(lane_ends)

    # Separate single-day from multi-day events in each cell.
    for day_cell in calendar_days:
        all_evs: list[dict[str, Any]] = day_cell.get("events", [])  # type: ignore[assignment]
        day_cell["single_events"] = [e for e in all_evs if not e.get("is_multi_day")]
        day_cell["event_count"] = len(all_evs)

    return weeks


# ── Day view overlap helpers ─────────────────────────────────────────────────


def _compute_overlap_columns(events: list[dict[str, Any]]) -> None:
    """Assign ``col_index`` and ``total_cols`` to timed events for side-by-side display.

    Events that overlap in time are grouped together and each group
    member gets a column index so the template can render them
    side-by-side at the appropriate width.

    Args:
        events: Timed events with ``top_slots`` and ``height_slots`` already set.
            Modified in-place to add ``col_index`` and ``total_cols``.
    """
    timed = [e for e in events if e.get("start_time") and "top_slots" in e]
    if not timed:
        return

    timed.sort(key=lambda e: (e.get("top_slots", 0), -e.get("height_slots", 1)))

    def _overlaps(a: dict[str, Any], b: dict[str, Any]) -> bool:
        a_start = a.get("top_slots", 0)
        a_end = a_start + a.get("height_slots", 1)
        b_start = b.get("top_slots", 0)
        b_end = b_start + b.get("height_slots", 1)
        return a_start < b_end and b_start < a_end

    # Build connected overlap groups.
    groups: list[list[dict[str, Any]]] = []
    for ev in timed:
        overlapping: list[int] = []
        for g_idx, group in enumerate(groups):
            if any(_overlaps(ev, g_ev) for g_ev in group):
                overlapping.append(g_idx)

        if not overlapping:
            groups.append([ev])
        elif len(overlapping) == 1:
            groups[overlapping[0]].append(ev)
        else:
            merged: list[dict[str, Any]] = [ev]
            for g_idx in sorted(overlapping, reverse=True):
                merged.extend(groups.pop(g_idx))
            groups.append(merged)

    # Assign columns within each overlap group.
    for group in groups:
        group.sort(key=lambda e: (e.get("top_slots", 0), -e.get("height_slots", 1)))
        columns: list[list[dict[str, Any]]] = []

        for ev in group:
            ev_start = ev.get("top_slots", 0)
            ev_end = ev_start + ev.get("height_slots", 1)
            placed = False
            for col_idx, col_events in enumerate(columns):
                conflict = any(
                    ev_start < (ex.get("top_slots", 0) + ex.get("height_slots", 1))
                    and ev_end > ex.get("top_slots", 0)
                    for ex in col_events
                )
                if not conflict:
                    ev["col_index"] = col_idx
                    col_events.append(ev)
                    placed = True
                    break
            if not placed:
                ev["col_index"] = len(columns)
                columns.append([ev])

        total = len(columns)
        for ev in group:
            ev["total_cols"] = total


# ── Week view all-day helpers ────────────────────────────────────────────────


def _build_week_allday_spans(
    week_data: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Extract multi-day and all-day events into horizontal spanning bars.

    Multi-day events and single-day all-day events are removed from
    individual day columns and converted into spanning segments for
    an all-day row at the top of the week view.

    Args:
        week_data: List of 7 day dicts (each with ``events``).

    Returns:
        Tuple of (spanning_segments, max_lanes).
    """
    date_to_col: dict[date, int] = {}
    for col, day in enumerate(week_data):
        d = day.get("date")
        if isinstance(d, date):
            date_to_col[d] = col

    seen: set[int] = set()
    multi_events: list[dict[str, Any]] = []
    event_cols: dict[int, list[int]] = {}

    for col, day in enumerate(week_data):
        timed_only: list[dict[str, Any]] = []
        for ev in day.get("events", []):
            ev_id = ev.get("id")
            is_allday = ev.get("is_multi_day") or ev.get("all_day")
            if is_allday and ev_id is not None:
                if ev_id not in seen:
                    seen.add(ev_id)
                    multi_events.append(ev)
                    event_cols[ev_id] = []
                event_cols.setdefault(ev_id, []).append(col)
            else:
                timed_only.append(ev)
        day["events"] = timed_only

    segments: list[dict[str, Any]] = []
    for ev in multi_events:
        cols = sorted(event_cols.get(ev.get("id", 0), []))
        if not cols:
            continue
        start_col = cols[0]
        span = cols[-1] - cols[0] + 1
        segments.append(
            {
                "id": ev.get("id"),
                "title": ev.get("title", ""),
                "start_time": ev.get("start_time"),
                "end_time": ev.get("end_time"),
                "status": ev.get("status", ""),
                "priority": ev.get("priority", ""),
                "color": ev.get("color"),
                "customer_name": ev.get("customer_name", ""),
                "employee_name": ev.get("employee_name", ""),
                "start_col": start_col,
                "span": span,
                "is_start": ev.get("is_first_day", True),
                "is_end": ev.get("is_last_day", True),
                "lane": 0,
            }
        )

    # Lane assignment.
    segments.sort(key=lambda s: (s["start_col"], -s["span"]))
    lane_ends: list[int] = []
    for seg in segments:
        assigned = False
        for li, end_col in enumerate(lane_ends):
            if seg["start_col"] > end_col:
                seg["lane"] = li
                lane_ends[li] = seg["start_col"] + seg["span"] - 1
                assigned = True
                break
        if not assigned:
            seg["lane"] = len(lane_ends)
            lane_ends.append(seg["start_col"] + seg["span"] - 1)

    return segments, len(lane_ends)


# ── Route handlers ───────────────────────────────────────────────────────────


@router.get("/calendar", response_class=HTMLResponse)
async def calendar_page(
    request: Request,
    year: int | None = None,
    month: int | None = None,
    employee_ids: str | None = Query(None),
    customer_ids: str | None = Query(None),
) -> HTMLResponse:
    """Render the full calendar page (month view).

    If *year* / *month* are omitted the current date is used.
    Events are fetched server-side and injected into the grid.

    Args:
        request: Incoming HTTP request.
        year:    Year to display (defaults to current year).
        month:   Month to display (defaults to current month).
        employee_ids: Comma-separated employee IDs to filter by.
        customer_ids: Comma-separated customer IDs to filter by.

    Returns:
        Rendered ``pages/calendar.html`` template.
    """
    now = datetime.now()
    display_year: int = year if year is not None else now.year
    display_month: int = month if month is not None else now.month

    context = _month_context(display_year, display_month)
    context["title"] = "Calendar"
    today = date.today()
    context["day"] = (
        today.day
        if (display_year == today.year and display_month == today.month)
        else 1
    )
    context["heading_text"] = f"{context['month_name']} {display_year}"
    context["nav_prev_url"] = (
        f"/calendar/container?year={context['prev_year']}&month={context['prev_month']}"
    )
    context["nav_next_url"] = (
        f"/calendar/container?year={context['next_year']}&month={context['next_month']}"
    )
    context["nav_today_url"] = "/calendar/container"

    emp_ids = _parse_ids(employee_ids)
    cust_ids = _parse_ids(customer_ids)
    await _inject_events(request, context, emp_ids, cust_ids)

    response = templates.TemplateResponse(request, "pages/calendar.html", context)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@router.get("/calendar/prev")
async def calendar_prev(
    year: int = Query(...),
    month: int = Query(...),
) -> RedirectResponse:
    """Navigate to the previous month.

    Computes the previous month from the supplied *year*/*month* and
    issues a 302 redirect to the path-based calendar route.

    Args:
        year:  Current year displayed.
        month: Current month displayed.

    Returns:
        Redirect to ``/calendar/{prev_year}/{prev_month}``.
    """
    first_of_month = date(year, month, 1)
    prev_month_date = first_of_month - timedelta(days=1)
    return RedirectResponse(
        url=f"/calendar/{prev_month_date.year}/{prev_month_date.month}",
        status_code=302,
    )


@router.get("/calendar/next")
async def calendar_next(
    year: int = Query(...),
    month: int = Query(...),
) -> RedirectResponse:
    """Navigate to the next month.

    Computes the next month from the supplied *year*/*month* and
    issues a 302 redirect to the path-based calendar route.

    Args:
        year:  Current year displayed.
        month: Current month displayed.

    Returns:
        Redirect to ``/calendar/{next_year}/{next_month}``.
    """
    # Jump forward 32 days to land in the next month, then snap to the 1st.
    next_month_date = date(year, month, 1) + timedelta(days=32)
    next_month_date = date(next_month_date.year, next_month_date.month, 1)
    return RedirectResponse(
        url=f"/calendar/{next_month_date.year}/{next_month_date.month}",
        status_code=302,
    )


@router.get("/calendar/container", response_class=HTMLResponse)
async def calendar_container(
    request: Request,
    year: int | None = None,
    month: int | None = None,
    employee_ids: str | None = Query(None),
    customer_ids: str | None = Query(None),
) -> HTMLResponse:
    """Render the calendar header + grid as one HTMX-swappable partial.

    This replaces the old ``/calendar/grid`` approach which only swapped
    the grid, leaving the header (month name, navigation URLs) stale.
    Now the entire ``#calendar-container`` is swapped, keeping the
    header, arrows, and grid in sync.

    Args:
        request: Incoming HTTP request.
        year:    Year to display.
        month:   Month to display.
        employee_ids: Comma-separated employee IDs to filter by.
        customer_ids: Comma-separated customer IDs to filter by.

    Returns:
        Rendered ``partials/calendar_container.html`` fragment.
    """
    now = datetime.now()
    display_year: int = year if year is not None else now.year
    display_month: int = month if month is not None else now.month

    context = _month_context(display_year, display_month)
    today = date.today()
    context["day"] = (
        today.day
        if (display_year == today.year and display_month == today.month)
        else 1
    )
    context["heading_text"] = f"{context['month_name']} {display_year}"
    context["nav_prev_url"] = (
        f"/calendar/container?year={context['prev_year']}&month={context['prev_month']}"
    )
    context["nav_next_url"] = (
        f"/calendar/container?year={context['next_year']}&month={context['next_month']}"
    )
    context["nav_today_url"] = "/calendar/container"

    emp_ids = _parse_ids(employee_ids)
    cust_ids = _parse_ids(customer_ids)
    await _inject_events(request, context, emp_ids, cust_ids)

    return templates.TemplateResponse(
        request, "partials/calendar_container.html", context
    )


@router.get("/calendar/grid", response_class=HTMLResponse)
async def calendar_grid(
    request: Request,
    year: int | None = None,
    month: int | None = None,
    employee_ids: str | None = Query(None),
    customer_ids: str | None = Query(None),
) -> HTMLResponse:
    """Render just the calendar grid (HTMX partial, kept for backwards compat).

    Prefer ``/calendar/container`` which swaps the header + grid
    together so the month name and navigation stay in sync.

    Args:
        request: Incoming HTTP request.
        year:    Year to display.
        month:   Month to display.

    Returns:
        Rendered ``partials/calendar_grid.html`` fragment.
    """
    now = datetime.now()
    display_year: int = year if year is not None else now.year
    display_month: int = month if month is not None else now.month

    context = _month_context(display_year, display_month)

    emp_ids = _parse_ids(employee_ids)
    cust_ids = _parse_ids(customer_ids)
    await _inject_events(request, context, emp_ids, cust_ids)

    return templates.TemplateResponse(request, "partials/calendar_grid.html", context)


@router.get("/calendar/week", response_class=HTMLResponse)
async def calendar_week(
    request: Request,
    year: int | None = None,
    month: int | None = None,
    day: int | None = None,
    employee_ids: str | None = Query(None),
    customer_ids: str | None = Query(None),
) -> HTMLResponse:
    """Render the week-view partial (HTMX swap target).

    Displays a 7-column time-slot grid (06:00–22:00) for the week
    containing the specified date.  Multi-day events are extracted
    into an all-day spanning bar section above the time grid.

    Args:
        request:      Incoming HTTP request.
        year:         Year (defaults to current).
        month:        Month (defaults to current).
        day:          Day of month (defaults to today).
        employee_ids: Comma-separated employee IDs to filter by.
        customer_ids: Comma-separated customer IDs to filter by.

    Returns:
        Rendered ``partials/calendar_week.html`` fragment.
    """
    now = datetime.now()
    y = year if year is not None else now.year
    m = month if month is not None else now.month
    d = day if day is not None else now.day

    week = _week_dates(y, m, d)
    today = date.today()

    emp_ids = _parse_ids(employee_ids)
    cust_ids = _parse_ids(customer_ids)

    # Concurrent fetch: events + employees + customers.
    api_days, employees, customers = await asyncio.gather(
        service_client.fetch_calendar_events(request, week[0], week[-1]),
        service_client.fetch_employees(request),
        service_client.fetch_customers(request),
    )

    # Apply filters.
    api_days = _filter_api_jobs(api_days, emp_ids, cust_ids)

    # Build name lookups for enrichment.
    emp_lookup, cust_lookup = _build_name_lookups(employees, customers)

    # Deduplicate jobs across API day entries.
    seen_ids: set[int] = set()
    unique_jobs: list[dict[str, Any]] = []
    for day_data in api_days:
        for job in day_data.get("jobs", []):
            job_id = job.get("id")
            if job_id is not None and job_id not in seen_ids:
                seen_ids.add(job_id)
                unique_jobs.append(job)

    # Build a date → events lookup with slot-position metadata.
    jobs_by_date: dict[date, list[dict[str, Any]]] = {}
    for job in unique_jobs:
        start_dt = _parse_event_date(job.get("start_time"))
        end_dt = _parse_event_date(job.get("end_time"))
        if start_dt is None:
            continue
        if end_dt is None:
            end_dt = start_dt

        start_hhmm = _format_display_time(job.get("start_time"))
        end_hhmm = _format_display_time(job.get("end_time"))
        is_multi_day: bool = end_dt > start_dt

        # Name enrichment.
        emp_name = emp_lookup.get(job.get("assigned_to") or 0, "")
        cust_name = cust_lookup.get(job.get("customer_id") or 0, "")

        cur = max(start_dt, week[0])
        end_bound = min(end_dt, week[-1])
        while cur <= end_bound:
            is_first = cur == start_dt
            is_last = cur == end_dt

            day_start = start_hhmm if is_first else HOUR_SLOTS[0]
            day_end = end_hhmm if is_last else HOUR_SLOTS[-1]

            top_idx = _time_to_slot_index(day_start) or 0
            end_idx = _time_to_slot_index(day_end) or _TOTAL_SLOTS
            height_slots = max(1, end_idx - top_idx)

            formatted_job: dict[str, Any] = {
                **job,
                "start_time": start_hhmm,
                "end_time": end_hhmm,
                "is_multi_day": is_multi_day,
                "is_first_day": is_first,
                "is_last_day": is_last,
                "is_continuation": not is_first,
                "top_slots": top_idx,
                "height_slots": height_slots,
                "employee_name": emp_name,
                "customer_name": cust_name,
            }
            jobs_by_date.setdefault(cur, []).append(formatted_job)
            cur += timedelta(days=1)

    week_data = [
        {
            "date": wd,
            "day_name": wd.strftime("%a"),
            "day_num": wd.day,
            "month_name": wd.strftime("%b"),
            "is_today": wd == today,
            "events": jobs_by_date.get(wd, []),
        }
        for wd in week
    ]

    # Extract multi-day and all-day events into all-day spanning bar section.
    allday_spans, allday_max_lanes = _build_week_allday_spans(week_data)

    # Remove multi-day / all-day events from the timed grid columns.
    for col in week_data:
        col["events"] = [
            e
            for e in col["events"]
            if not e.get("is_multi_day") and not e.get("all_day")
        ]

    # Compute side-by-side columns for overlapping timed events.
    for col in week_data:
        _compute_overlap_columns(col["events"])

    # Previous / next week dates.
    prev_week = week[0] - timedelta(days=7)
    next_week = week[0] + timedelta(days=7)

    context: dict[str, Any] = {
        "week_data": week_data,
        "allday_spans": allday_spans,
        "allday_max_lanes": allday_max_lanes,
        "hour_slots": HOUR_SLOTS,
        "current_view": "week",
        "year": y,
        "month": m,
        "day": d,
        "week_start": week[0],
        "week_end": week[-1],
        "month_name": date(y, m, 1).strftime("%B"),
        "employees": employees,
        "customers": customers,
        # Shared header vars
        "heading_text": (
            f"{week[0].strftime('%d %b')} \u2013 {week[-1].strftime('%d %b %Y')}"
        ),
        "nav_prev_url": (
            f"/calendar/week?year={prev_week.year}"
            f"&month={prev_week.month}&day={prev_week.day}"
        ),
        "nav_next_url": (
            f"/calendar/week?year={next_week.year}"
            f"&month={next_week.month}&day={next_week.day}"
        ),
        "nav_today_url": "/calendar/week",
    }

    return templates.TemplateResponse(request, "partials/calendar_week.html", context)


@router.get("/calendar/day-view/{date_str}", response_class=HTMLResponse)
async def day_timeline_view(
    request: Request,
    date_str: str,
    employee_ids: str | None = Query(None),
    customer_ids: str | None = Query(None),
) -> HTMLResponse:
    """Render the full day-timeline view (HTMX partial).

    Displays a multi-column time-slot grid (06:00–22:00) with events
    positioned by their start/end times.  Overlapping events are
    displayed side-by-side in columns.

    Args:
        request:      Incoming HTTP request.
        date_str:     Date in ``YYYY-MM-DD`` format.
        employee_ids: Comma-separated employee IDs to filter by.
        customer_ids: Comma-separated customer IDs to filter by.

    Returns:
        Rendered ``partials/calendar_day_timeline.html`` fragment.
    """
    target = datetime.strptime(date_str, "%Y-%m-%d").date()
    today = date.today()

    emp_ids = _parse_ids(employee_ids)
    cust_ids = _parse_ids(customer_ids)

    # Concurrent fetch: events + employees + customers.
    events, employees, customers = await asyncio.gather(
        service_client.fetch_day_events(request, target),
        service_client.fetch_employees(request),
        service_client.fetch_customers(request),
    )

    # Apply filters.
    if emp_ids or cust_ids:
        filtered: list[dict[str, Any]] = []
        for ev in events:
            if emp_ids and ev.get("assigned_to") not in emp_ids:
                continue
            if cust_ids and ev.get("customer_id") not in cust_ids:
                continue
            filtered.append(ev)
        events = filtered

    # Build name lookups for enrichment.
    emp_lookup, cust_lookup = _build_name_lookups(employees, customers)

    # Convert ISO timestamps to HH:MM and add slot-position metadata.
    for ev in events:
        ev["start_time"] = _format_display_time(ev.get("start_time"))
        ev["end_time"] = _format_display_time(ev.get("end_time"))
        top_idx = _time_to_slot_index(ev["start_time"]) or 0
        end_idx = _time_to_slot_index(ev["end_time"]) or _TOTAL_SLOTS
        ev["top_slots"] = top_idx
        ev["height_slots"] = max(1, end_idx - top_idx)
        ev["employee_name"] = emp_lookup.get(ev.get("assigned_to") or 0, "")
        ev["customer_name"] = cust_lookup.get(ev.get("customer_id") or 0, "")

    # Assign overlap columns for side-by-side display.
    _compute_overlap_columns(events)

    prev_day = target - timedelta(days=1)
    next_day = target + timedelta(days=1)

    context: dict[str, Any] = {
        "target_date": target,
        "date_str": date_str,
        "day_name": target.strftime("%A"),
        "is_today": target == today,
        "events": events,
        "hour_slots": HOUR_SLOTS,
        "current_view": "day",
        "year": target.year,
        "month": target.month,
        "day": target.day,
        "month_name": target.strftime("%B"),
        "employees": employees,
        "customers": customers,
        # Shared header vars
        "heading_text": target.strftime("%A, %d %B %Y"),
        "nav_prev_url": f"/calendar/day-view/{prev_day.isoformat()}",
        "nav_next_url": f"/calendar/day-view/{next_day.isoformat()}",
        "nav_today_url": f"/calendar/day-view/{today.isoformat()}",
    }

    return templates.TemplateResponse(
        request, "partials/calendar_day_timeline.html", context
    )


@router.get("/calendar/day/{date_str}", response_class=HTMLResponse)
async def day_view(
    request: Request,
    date_str: str,
) -> HTMLResponse:
    """Render the day-detail modal (HTMX partial).

    Lists all events for a given date in a modal overlay triggered
    by double-clicking a calendar grid cell.

    Args:
        request:  Incoming HTTP request.
        date_str: Date in ``YYYY-MM-DD`` format.

    Returns:
        Rendered ``partials/day_view.html`` fragment.
    """
    day_date = datetime.strptime(date_str, "%Y-%m-%d")
    events, employees, company = await asyncio.gather(
        service_client.fetch_day_events(request, day_date.date()),
        service_client.fetch_employees(request),
        service_client.fetch_company(request),
    )

    # Convert raw ISO timestamps to HH:MM strings for the template.
    for ev in events:
        ev["start_time"] = _format_display_time(ev.get("start_time"))
        ev["end_time"] = _format_display_time(ev.get("end_time"))

    return templates.TemplateResponse(
        request,
        "partials/day_view.html",
        {
            "date": day_date,
            "date_str": date_str,
            "events": events,
            "employees": employees,
            "events_json": json.dumps(events),
            "employees_json": json.dumps(employees),
            "company_json": json.dumps(company),
        },
    )


@router.get("/calendar/job-queue", response_class=HTMLResponse)
async def job_queue_panel(request: Request) -> HTMLResponse:
    """Render the unscheduled-job queue sidebar (HTMX partial).

    Jobs displayed here can be dragged onto the calendar to schedule
    them.  Data is fetched from job-bl-service server-side.

    Args:
        request: Incoming HTTP request.

    Returns:
        Rendered ``partials/job_queue.html`` fragment.
    """
    jobs = await service_client.fetch_unscheduled_jobs(request)

    return templates.TemplateResponse(
        request,
        "partials/job_queue.html",
        {
            "jobs": jobs,
        },
    )


def _parse_iso_datetime(
    value: str | datetime | None,
) -> tuple[str | None, str | None]:
    """Parse ISO datetime string or datetime object into separate date/time strings.

    Safely handles strings, datetime objects, and None values. Returns
    properly formatted strings for use in HTML date/time input elements.

    Args:
        value: ISO format datetime string, datetime object, or None.

    Returns:
        Tuple of (date_str: YYYY-MM-DD or None, time_str: HH:MM or None).
    """
    if value is None:
        return None, None

    try:
        # If it's already a datetime object, use it directly
        if isinstance(value, datetime):
            dt = value
        else:
            # Parse ISO string (handles both full datetime and date-only)
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))

        date_str: str = dt.strftime("%Y-%m-%d")
        time_str: str = dt.strftime("%H:%M")
        return date_str, time_str
    except (ValueError, TypeError, AttributeError) as exc:
        logger.warning(f"Failed to parse datetime value {value!r}: {exc}")
        return None, None


@router.get("/calendar/job-modal", response_class=HTMLResponse)
async def job_modal(
    request: Request,
    job_id: int | None = None,
    date: str | None = None,
) -> HTMLResponse:
    """Render the job create / edit modal (HTMX partial).

    When *job_id* is supplied the modal opens in edit mode with
    pre-populated fields; otherwise it opens as a blank creation form.

    Properly formats all date/time values for HTML input elements
    (date inputs expect YYYY-MM-DD, time inputs expect HH:MM).

    Args:
        request: Incoming HTTP request.
        job_id:  Job ID for editing (``None`` for a new job).
        date:    Pre-selected date (``YYYY-MM-DD``) for a new job.

    Returns:
        Rendered ``partials/job_modal.html`` fragment with properly
        formatted date/time values ready for HTML input elements.

    Raises:
        HTTPException: If job_id is supplied but job not found (404).
    """
    job: dict[str, Any] | None = None
    if job_id:
        job = await service_client.fetch_job_detail(request, job_id)
        if job is None:
            raise HTTPException(
                status_code=404,
                detail=f"Job {job_id} not found or access denied",
            )

    # Fetch dropdown data concurrently for the modal selects.
    employees, customers = await asyncio.gather(
        service_client.fetch_employees(request),
        service_client.fetch_customers(request),
    )

    # Parse and format job start/end times for HTML input elements
    start_date_str, start_time_str = None, None
    end_date_str, end_time_str = None, None

    if job:
        # Parse start_time from job object
        if job.get("start_time"):
            start_date_str, start_time_str = _parse_iso_datetime(job["start_time"])
        # Default end time based on start time if not provided
        if job.get("end_time"):
            end_date_str, end_time_str = _parse_iso_datetime(job["end_time"])
        elif start_time_str:
            # Default: same day, 8 hours later (17:00 if started at 09:00)
            end_time_str = "17:00"
            end_date_str = start_date_str

    # Use pre-selected date from query param if provided
    if date and not start_date_str:
        start_date_str = date
        end_date_str = date
        start_time_str = start_time_str or "09:00"
        end_time_str = end_time_str or "17:00"

    return templates.TemplateResponse(
        request,
        "partials/job_modal.html",
        {
            "job": job,
            "start_date": start_date_str,
            "start_time": start_time_str or "09:00",
            "end_date": end_date_str,
            "end_time": end_time_str or "17:00",
            "is_edit": job is not None,
            "employees": employees,
            "customers": customers,
        },
    )


@router.get("/calendar/quick-schedule-modal", response_class=HTMLResponse)
async def quick_schedule_modal(
    request: Request,
    job_id: int = 0,
    date: str = "",
) -> HTMLResponse:
    """Render the quick-schedule modal for drag-and-drop scheduling.

    Shown when a job is dragged from the queue onto a calendar date
    and still requires scheduling details (start/end time, employee).
    This is a lightweight alternative to the full job modal, focused
    only on the fields needed to schedule the job.

    Args:
        request: Incoming HTTP request.
        job_id:  ID of the job being scheduled.
        date:    Target date in ``YYYY-MM-DD`` format.

    Returns:
        Rendered ``partials/quick_schedule_modal.html`` fragment.

    Raises:
        HTTPException: 400 if job_id or date are missing,
                       404 if job is not found.
    """
    if not job_id or not date:
        raise HTTPException(status_code=400, detail="job_id and date are required")

    # Fetch job detail and employee list concurrently
    job, employees = await asyncio.gather(
        service_client.fetch_job_detail(request, job_id),
        service_client.fetch_employees(request),
    )

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Parse existing times if present, otherwise default to 09:00–17:00
    start_time_str = "09:00"
    end_time_str = "17:00"
    if job.get("start_time"):
        _, parsed_start = _parse_iso_datetime(job["start_time"])
        if parsed_start:
            start_time_str = parsed_start
    if job.get("end_time"):
        _, parsed_end = _parse_iso_datetime(job["end_time"])
        if parsed_end:
            end_time_str = parsed_end

    return templates.TemplateResponse(
        request,
        "partials/quick_schedule_modal.html",
        {
            "job": job,
            "date": date,
            "employees": employees,
            "start_time": start_time_str,
            "end_time": end_time_str,
        },
    )


# ── Catch-all path-based month route (MUST be last) ─────────────────────────
# Registered after all specific two-segment routes (``/calendar/day/…``,
# ``/calendar/job-queue``, ``/calendar/job-modal``,
# ``/calendar/quick-schedule-modal``) so that FastAPI doesn't attempt
# to coerce e.g. "day" into ``year: int``.


@router.get("/calendar/{year}/{month}", response_class=HTMLResponse)
async def calendar_by_month(
    request: Request,
    year: int,
    month: int,
    employee_id: int | None = Query(None),
    customer_id: int | None = Query(None),
) -> HTMLResponse:
    """Render the calendar page for a specific year / month.

    This path-based variant (``/calendar/2024/6``) complements the
    query-param variant (``/calendar?year=2024&month=6``) and provides
    cleaner URLs for direct linking and browser history entries.

    Args:
        request: Incoming HTTP request.
        year:    Calendar year to display.
        month:   Calendar month (1–12) to display.

    Returns:
        Rendered ``pages/calendar.html`` template.
    """
    context = _month_context(year, month)
    context["title"] = "Calendar"
    today = date.today()
    context["day"] = today.day if (year == today.year and month == today.month) else 1
    context["heading_text"] = f"{context['month_name']} {year}"
    context["nav_prev_url"] = (
        f"/calendar/container?year={context['prev_year']}&month={context['prev_month']}"
    )
    context["nav_next_url"] = (
        f"/calendar/container?year={context['next_year']}&month={context['next_month']}"
    )
    context["nav_today_url"] = "/calendar/container"

    emp_ids = [employee_id] if employee_id else None
    cust_ids = [customer_id] if customer_id else None
    await _inject_events(request, context, emp_ids, cust_ids)

    return templates.TemplateResponse(request, "pages/calendar.html", context)
