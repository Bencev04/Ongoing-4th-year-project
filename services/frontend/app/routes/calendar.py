"""Calendar page routes.

Serves the full-page calendar view and HTMX partial templates used
for month navigation, day details, the job queue sidebar, and the
job create/edit modal.

Routes
------
GET /calendar              – Full calendar page.
GET /calendar/grid          – Calendar grid partial (HTMX swap target).
GET /calendar/day/{date}    – Day detail partial.
GET /calendar/job-queue     – Unscheduled-job sidebar partial.
GET /calendar/job-modal     – Job create / edit modal partial.
"""

from __future__ import annotations

import calendar as cal
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

# ── Template engine ──────────────────────────────────────────────────────────
_templates_path: Path = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=_templates_path)

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
            days.append(
                _build_day_cell(pad_start + timedelta(days=i), False, today)
            )

    # ── Current-month days ───────────────────────────────────────────
    for day_num in range(1, days_in_month + 1):
        days.append(
            _build_day_cell(date(year, month, day_num), True, today)
        )

    # ── Next-month padding (fill to 42 cells) ────────────────────────
    remaining: int = 42 - len(days)
    if remaining > 0:
        next_month_start: date = date(year, month, days_in_month) + timedelta(days=1)
        for i in range(remaining):
            days.append(
                _build_day_cell(next_month_start + timedelta(days=i), False, today)
            )

    return days


def _month_context(year: int, month: int) -> dict[str, object]:
    """Compute the shared template context for a given month.

    Args:
        year:  Calendar year.
        month: Calendar month (1–12).

    Returns:
        Dict containing year, month, navigation values, day grid, etc.
    """
    current_date = date(year, month, 1)
    prev_date = current_date - timedelta(days=1)

    # Jump to the 1st of the next month
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
    }


# ── Route handlers ───────────────────────────────────────────────────────────

@router.get("/calendar", response_class=HTMLResponse)
async def calendar_page(
    request: Request,
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> HTMLResponse:
    """Render the full calendar page.

    If *year* / *month* are omitted the current date is used.

    Args:
        request: Incoming HTTP request.
        year:    Year to display (defaults to current year).
        month:   Month to display (defaults to current month).

    Returns:
        Rendered ``pages/calendar.html`` template.
    """
    now = datetime.now()
    display_year: int = year if year is not None else now.year
    display_month: int = month if month is not None else now.month

    context = _month_context(display_year, display_month)
    context.update({"request": request, "title": "Calendar"})

    return templates.TemplateResponse("pages/calendar.html", context)


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


@router.get("/calendar/grid", response_class=HTMLResponse)
async def calendar_grid(
    request: Request,
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> HTMLResponse:
    """Render just the calendar grid (HTMX partial).

    Used for client-side month navigation without a full page reload.
    Defaults to the current month when query params are omitted (the
    "Today" button sends no params).

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
    context["request"] = request

    return templates.TemplateResponse("partials/calendar_grid.html", context)


@router.get("/calendar/day/{date_str}", response_class=HTMLResponse)
async def day_view(
    request: Request,
    date_str: str,
) -> HTMLResponse:
    """Render the day-detail view (HTMX partial).

    Args:
        request:  Incoming HTTP request.
        date_str: Date in ``YYYY-MM-DD`` format.

    Returns:
        Rendered ``partials/day_view.html`` fragment.
    """
    day_date: datetime = datetime.strptime(date_str, "%Y-%m-%d")

    return templates.TemplateResponse(
        "partials/day_view.html",
        {
            "request": request,
            "date": day_date,
            "date_str": date_str,
            # TODO(job-integration): Fetch events from job-service for this specific date
            "events": [],
        },
    )


@router.get("/calendar/job-queue", response_class=HTMLResponse)
async def job_queue_panel(request: Request) -> HTMLResponse:
    """Render the unscheduled-job queue sidebar (HTMX partial).

    Jobs displayed here can be dragged onto the calendar to schedule
    them.

    Args:
        request: Incoming HTTP request.

    Returns:
        Rendered ``partials/job_queue.html`` fragment.
    """
    return templates.TemplateResponse(
        "partials/job_queue.html",
        {
            "request": request,
            # TODO(job-integration): Fetch unscheduled jobs from job-service
            "jobs": [],
        },
    )


@router.get("/calendar/job-modal", response_class=HTMLResponse)
async def job_modal(
    request: Request,
    job_id: Optional[int] = None,
    date: Optional[str] = None,
) -> HTMLResponse:
    """Render the job create / edit modal (HTMX partial).

    When *job_id* is supplied the modal opens in edit mode; otherwise
    it opens as a blank creation form.

    Args:
        request: Incoming HTTP request.
        job_id:  Job ID for editing (``None`` for a new job).
        date:    Pre-selected date (``YYYY-MM-DD``) for a new job.

    Returns:
        Rendered ``partials/job_modal.html`` fragment.
    """
    job: Optional[dict] = None
    if job_id:
        # TODO(job-integration): Fetch job details from job-bl-service via service_client
        # Example: job = await service_client.get_job(job_id)
        pass

    return templates.TemplateResponse(
        "partials/job_modal.html",
        {
            "request": request,
            "job": job,
            "date": date,
            "is_edit": job_id is not None,
        },
    )


# ── Catch-all path-based month route (MUST be last) ─────────────────────────
# Registered after all specific two-segment routes (``/calendar/day/…``,
# ``/calendar/job-queue``, ``/calendar/job-modal``) so that FastAPI
# doesn't attempt to coerce e.g. "day" into ``year: int``.

@router.get("/calendar/{year}/{month}", response_class=HTMLResponse)
async def calendar_by_month(
    request: Request,
    year: int,
    month: int,
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
    context.update({"request": request, "title": "Calendar"})
    return templates.TemplateResponse("pages/calendar.html", context)
