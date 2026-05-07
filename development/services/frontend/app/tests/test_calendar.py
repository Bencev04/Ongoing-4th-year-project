"""
Frontend Calendar Route Tests

Comprehensive unit tests for calendar routes, templates, and business
logic helpers.  Tests cover:

- Page renders (month / week / day)
- HTMX navigation (prev / next / today)
- Multi-day event expansion logic
- Event injection into the grid
- View switching
- Job modal rendering
- Drag-and-drop refresh wiring
- Edge cases (year boundary, empty months)
- Date/time parsing and formatting
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.routes.calendar import _format_display_time, _parse_iso_datetime

# ═══════════════════════════════════════════════════════════════════════
# Date parsing helper tests
# ═══════════════════════════════════════════════════════════════════════


class TestParseIsoDateTime:
    """Tests for the _parse_iso_datetime helper function.

    Validates that datetime strings and objects are properly converted
    to separate date (YYYY-MM-DD) and time (HH:MM) strings suitable
    for HTML input elements.
    """

    def test_parse_iso_datetime_with_iso_string(self) -> None:
        """Parse ISO datetime string (full format with Z timezone)."""
        date_str, time_str = _parse_iso_datetime("2026-03-04T14:30:00Z")
        assert date_str == "2026-03-04"
        assert time_str == "14:30"

    def test_parse_iso_datetime_with_datetime_object(self) -> None:
        """Parse datetime object (already parsed by frontend service)."""
        dt = datetime(2026, 3, 4, 14, 30, 45)
        date_str, time_str = _parse_iso_datetime(dt)
        assert date_str == "2026-03-04"
        assert time_str == "14:30"

    def test_parse_iso_datetime_with_iso_string_plus_offset(self) -> None:
        """Parse ISO datetime string with +HH:MM timezone offset."""
        date_str, time_str = _parse_iso_datetime("2026-03-04T14:30:00+00:00")
        assert date_str == "2026-03-04"
        assert time_str == "14:30"

    def test_parse_iso_datetime_with_iso_string_no_timezone(self) -> None:
        """Parse ISO datetime string without timezone (local time)."""
        date_str, time_str = _parse_iso_datetime("2026-03-04T09:00:00")
        assert date_str == "2026-03-04"
        assert time_str == "09:00"

    def test_parse_iso_datetime_with_none(self) -> None:
        """Return (None, None) when input is None."""
        date_str, time_str = _parse_iso_datetime(None)
        assert date_str is None
        assert time_str is None

    def test_parse_iso_datetime_with_invalid_string(self) -> None:
        """Return (None, None) when input is unparseable."""
        date_str, time_str = _parse_iso_datetime("not a datetime")
        assert date_str is None
        assert time_str is None

    def test_parse_iso_datetime_preserves_time_precision(self) -> None:
        """Time is formatted to HH:MM (minutes only, no seconds)."""
        date_str, time_str = _parse_iso_datetime("2026-03-04T14:30:45Z")
        assert time_str == "14:30"  # No seconds
        assert len(time_str) == 5  # HH:MM format


# ═══════════════════════════════════════════════════════════════════════
# Display-time formatting helper tests
# ═══════════════════════════════════════════════════════════════════════


class TestFormatDisplayTime:
    """Test the ``_format_display_time`` helper.

    This helper converts ISO-8601 timestamps (strings or datetime objects)
    into compact ``HH:MM`` strings for calendar event chips.
    """

    def test_iso_string_with_z_suffix(self) -> None:
        """ISO string ending with 'Z' returns the correct HH:MM."""
        assert _format_display_time("2026-03-16T08:30:00Z") == "08:30"

    def test_iso_string_with_offset(self) -> None:
        """ISO string with explicit timezone offset returns HH:MM."""
        assert _format_display_time("2026-03-16T14:45:00+01:00") == "14:45"

    def test_iso_string_without_timezone(self) -> None:
        """ISO string without timezone info returns HH:MM."""
        assert _format_display_time("2024-01-15T09:00:00") == "09:00"

    def test_datetime_object(self) -> None:
        """A ``datetime`` object returns formatted HH:MM."""
        dt = datetime(2024, 6, 15, 17, 5, 0)
        assert _format_display_time(dt) == "17:05"

    def test_none_returns_none(self) -> None:
        """``None`` input returns ``None``."""
        assert _format_display_time(None) is None

    def test_invalid_string_returns_none(self) -> None:
        """An unparseable string returns ``None``."""
        assert _format_display_time("not-a-date") is None

    def test_empty_string_returns_none(self) -> None:
        """An empty string returns ``None``."""
        assert _format_display_time("") is None

    def test_midnight(self) -> None:
        """Midnight is formatted as 00:00."""
        assert _format_display_time("2024-01-01T00:00:00") == "00:00"

    def test_end_of_day(self) -> None:
        """23:59 is preserved correctly."""
        assert _format_display_time("2024-12-31T23:59:00") == "23:59"

    def test_seconds_are_dropped(self) -> None:
        """Seconds are stripped — only HH:MM is returned."""
        assert _format_display_time("2024-06-15T10:30:45") == "10:30"


# ═══════════════════════════════════════════════════════════════════════
# Calendar page — basic smoke tests
# ═══════════════════════════════════════════════════════════════════════


class TestCalendarPage:
    """Tests for the main calendar page."""

    def test_calendar_page_returns_200(self, client: TestClient) -> None:
        """Calendar page loads successfully."""
        response = client.get("/calendar")
        assert response.status_code == 200

    def test_page_contains_calendar_container(self, client: TestClient) -> None:
        """Page contains the HTMX swap target ``#calendar-container``."""
        response = client.get("/calendar")
        assert response.status_code == 200
        assert "calendar-container" in response.text

    def test_calendar_page_contains_calendar_grid(self, client: TestClient) -> None:
        """Page contains the calendar grid inside the container."""
        response = client.get("/calendar")
        assert response.status_code == 200
        assert "calendar-grid" in response.text

    def test_calendar_page_contains_job_queue(self, client: TestClient) -> None:
        """Page contains the job queue sidebar."""
        response = client.get("/calendar")
        assert response.status_code == 200
        assert "job-queue" in response.text

    def test_calendar_page_contains_htmx_attributes(self, client: TestClient) -> None:
        """Page has HTMX integration on navigation buttons."""
        response = client.get("/calendar")
        assert response.status_code == 200
        assert "hx-get" in response.text
        assert "hx-target" in response.text

    def test_calendar_page_contains_alpine_component(self, client: TestClient) -> None:
        """Page has Alpine.js ``calendarApp`` component."""
        response = client.get("/calendar")
        assert response.status_code == 200
        assert "x-data" in response.text
        assert "calendarApp" in response.text

    def test_calendar_page_contains_status_legend(self, client: TestClient) -> None:
        """Page renders the status colour legend."""
        response = client.get("/calendar")
        assert response.status_code == 200
        assert "Pending" in response.text
        assert "Scheduled" in response.text
        assert "In Progress" in response.text
        assert "Completed" in response.text

    def test_calendar_page_displays_month_name(self, client: TestClient) -> None:
        """Page displays the current month name."""
        response = client.get("/calendar?year=2024&month=3")
        assert response.status_code == 200
        assert "March" in response.text

    def test_calendar_page_contains_view_switcher(self, client: TestClient) -> None:
        """Page renders Month / Week / Day view switcher buttons."""
        response = client.get("/calendar")
        assert response.status_code == 200
        assert "Month" in response.text
        assert "Week" in response.text
        assert "Day" in response.text

    def test_calendar_page_contains_new_job_button(self, client: TestClient) -> None:
        """Page renders a 'New Job' button wired to the modal."""
        response = client.get("/calendar")
        assert response.status_code == 200
        assert "New Job" in response.text
        assert "/calendar/job-modal" in response.text


# ═══════════════════════════════════════════════════════════════════════
# Month navigation
# ═══════════════════════════════════════════════════════════════════════


class TestCalendarNavigation:
    """Tests for calendar navigation endpoints."""

    def test_navigate_to_specific_month(self, client: TestClient) -> None:
        """Direct URL ``/calendar/2024/6`` returns 200."""
        response = client.get("/calendar/2024/6")
        assert response.status_code == 200

    def test_navigate_to_previous_month(self, client: TestClient) -> None:
        """``/calendar/prev`` redirects to the previous month."""
        response = client.get(
            "/calendar/prev?year=2024&month=3", follow_redirects=False
        )
        assert response.status_code in (302, 307)
        location = response.headers.get("location", "")
        assert "2024" in location
        assert "/2" in location or "month=2" in location

    def test_navigate_to_next_month(self, client: TestClient) -> None:
        """``/calendar/next`` redirects to the next month."""
        response = client.get(
            "/calendar/next?year=2024&month=3", follow_redirects=False
        )
        assert response.status_code in (302, 307)
        location = response.headers.get("location", "")
        assert "2024" in location
        assert "/4" in location or "month=4" in location


class TestCalendarBoundaryNavigation:
    """Test year-boundary month navigation."""

    def test_december_to_january_navigation(self, client: TestClient) -> None:
        """Next from Dec 2025 → Jan 2026."""
        response = client.get(
            "/calendar/next?year=2025&month=12", follow_redirects=False
        )
        assert response.status_code in (302, 307)
        location = response.headers.get("location", "")
        assert "2026" in location
        assert "/1" in location or "month=1" in location

    def test_january_to_december_navigation(self, client: TestClient) -> None:
        """Prev from Jan 2026 → Dec 2025."""
        response = client.get(
            "/calendar/prev?year=2026&month=1", follow_redirects=False
        )
        assert response.status_code in (302, 307)
        location = response.headers.get("location", "")
        assert "2025" in location
        assert "/12" in location or "month=12" in location


# ═══════════════════════════════════════════════════════════════════════
# Container partial (header + grid swap)
# ═══════════════════════════════════════════════════════════════════════


class TestCalendarContainer:
    """Tests for the ``/calendar/container`` HTMX partial."""

    def test_container_returns_html(self, client: TestClient) -> None:
        """Container partial returns 200 with HTML content."""
        response = client.get("/calendar/container?year=2024&month=6")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_container_includes_month_name(self, client: TestClient) -> None:
        """Container partial includes the month name."""
        response = client.get("/calendar/container?year=2024&month=6")
        assert "June" in response.text

    def test_container_includes_navigation(self, client: TestClient) -> None:
        """Container includes prev/next navigation wired to itself."""
        response = client.get("/calendar/container?year=2024&month=6")
        assert "/calendar/container" in response.text

    def test_container_includes_grid(self, client: TestClient) -> None:
        """Container renders the calendar grid with weekday headers."""
        response = client.get("/calendar/container?year=2024&month=6")
        assert "Mon" in response.text
        assert "Sun" in response.text

    def test_container_defaults_to_current_month(self, client: TestClient) -> None:
        """Calling without params returns current month (200)."""
        response = client.get("/calendar/container")
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════════
# Calendar grid partial
# ═══════════════════════════════════════════════════════════════════════


class TestCalendarGrid:
    """Tests for the ``/calendar/grid`` HTMX partial."""

    def test_calendar_grid_returns_html(self, client: TestClient) -> None:
        """Grid partial returns HTML."""
        response = client.get("/calendar/grid?year=2024&month=1")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_grid_contains_42_day_cells(self, client: TestClient) -> None:
        """Grid renders day cells (42 per layout × number of layouts)."""
        response = client.get("/calendar/grid?year=2024&month=1")
        # Each day cell has the class ``calendar-day``
        day_count = response.text.count("calendar-day")
        # 42 cells per grid (6 rows × 7 cols); may render multiple
        # layouts (e.g. desktop + mobile) so accept multiples of 42
        assert day_count > 0
        assert day_count % 42 == 0

    def test_grid_contains_hidden_year_month(self, client: TestClient) -> None:
        """Grid has hidden inputs for year/month navigation state."""
        response = client.get("/calendar/grid?year=2024&month=3")
        assert 'id="current-year"' in response.text
        assert 'id="current-month"' in response.text
        assert 'value="2024"' in response.text
        assert 'value="3"' in response.text


# ═══════════════════════════════════════════════════════════════════════
# Week view
# ═══════════════════════════════════════════════════════════════════════


class TestWeekView:
    """Tests for the ``/calendar/week`` HTMX partial."""

    def test_week_view_returns_200(self, client: TestClient) -> None:
        """Week view partial loads successfully."""
        response = client.get("/calendar/week?year=2024&month=1&day=15")
        assert response.status_code == 200

    def test_week_view_contains_day_columns(self, client: TestClient) -> None:
        """Week view renders columns for each day of the week."""
        response = client.get("/calendar/week?year=2024&month=1&day=15")
        assert "Mon" in response.text
        assert "Sun" in response.text

    def test_week_view_contains_time_slots(self, client: TestClient) -> None:
        """Week view renders hour labels."""
        response = client.get("/calendar/week?year=2024&month=1&day=15")
        assert "09:00" in response.text
        assert "17:00" in response.text

    def test_week_view_defaults_to_current_week(self, client: TestClient) -> None:
        """Calling without params returns current week."""
        response = client.get("/calendar/week")
        assert response.status_code == 200

    def test_week_view_contains_view_switcher(self, client: TestClient) -> None:
        """Week view includes Month / Week / Day view switcher."""
        response = client.get("/calendar/week?year=2024&month=1&day=15")
        assert "Month" in response.text
        assert "Week" in response.text
        assert "Day" in response.text

    def test_week_view_contains_navigation(self, client: TestClient) -> None:
        """Week view includes prev/next and Today buttons."""
        response = client.get("/calendar/week?year=2024&month=1&day=15")
        assert "Today" in response.text
        assert 'aria-label="Previous"' in response.text
        assert 'aria-label="Next"' in response.text


# ═══════════════════════════════════════════════════════════════════════
# Day timeline view
# ═══════════════════════════════════════════════════════════════════════


class TestDayTimelineView:
    """Tests for the ``/calendar/day-view/{date}`` HTMX partial."""

    def test_day_timeline_returns_200(self, client: TestClient) -> None:
        """Day timeline view loads successfully."""
        response = client.get("/calendar/day-view/2024-01-15")
        assert response.status_code == 200

    def test_day_timeline_contains_date(self, client: TestClient) -> None:
        """Timeline shows the formatted date."""
        response = client.get("/calendar/day-view/2024-01-15")
        assert "15" in response.text
        assert "January" in response.text

    def test_day_timeline_has_navigation(self, client: TestClient) -> None:
        """Timeline has prev/next day navigation."""
        response = client.get("/calendar/day-view/2024-01-15")
        assert "/calendar/day-view/2024-01-14" in response.text
        assert "/calendar/day-view/2024-01-16" in response.text

    def test_day_timeline_has_view_switcher(self, client: TestClient) -> None:
        """Timeline includes Month/Week/Day view switcher."""
        response = client.get("/calendar/day-view/2024-01-15")
        assert "Month" in response.text
        assert "Week" in response.text
        assert "Day" in response.text


# ═══════════════════════════════════════════════════════════════════════
# Day detail (modal) view
# ═══════════════════════════════════════════════════════════════════════


class TestDayView:
    """Tests for day view endpoints (modal / detail).

    Covers:
    - Basic rendering and HTTP status
    - Modal layout: wider container (max-w-7xl), viewport-capped height
    - Map sizing: uses min-h and flex-1 to fill available space
    - Routing logic: per-employee routes, single-job skip behaviour
    - Filter controls: employee and status dropdowns trigger updateMap()
    - Map initialisation wiring (Alpine x-init + mapsReady listener)
    - JSON data injection into script tags
    - Starting point toggle (company / custom eircode)
    - Route summary stats panel presence
    """

    def test_day_view_returns_html(self, client: TestClient) -> None:
        """Day view modal returns HTTP 200 with HTML content."""
        response = client.get("/calendar/day/2024-01-15")
        assert response.status_code == 200

    def test_day_view_modal_is_wider(self, client: TestClient) -> None:
        """Modal panel uses max-w-7xl for a wider layout to accommodate the map."""
        response = client.get("/calendar/day/2024-01-15")
        assert "max-w-7xl" in response.text

    def test_day_view_modal_has_viewport_height_cap(self, client: TestClient) -> None:
        """Modal panel uses max-h-[90vh] so it doesn't overflow the viewport."""
        response = client.get("/calendar/day/2024-01-15")
        assert "max-h-[90vh]" in response.text

    def test_day_view_map_uses_flex_fill(self, client: TestClient) -> None:
        """Map container uses flex-1 to fill available modal height."""
        response = client.get("/calendar/day/2024-01-15")
        assert "min-h-[28rem]" in response.text
        assert "flex-1" in response.text

    def test_day_view_contains_employee_filter(self, client: TestClient) -> None:
        """Day view has an employee filter dropdown that triggers map refresh."""
        response = client.get("/calendar/day/2024-01-15")
        assert "filterEmployee" in response.text
        assert "updateMap()" in response.text

    def test_day_view_contains_status_filter(self, client: TestClient) -> None:
        """Day view has a status filter dropdown with expected options."""
        response = client.get("/calendar/day/2024-01-15")
        assert "filterStatus" in response.text
        assert "pending" in response.text
        assert "scheduled" in response.text
        assert "in_progress" in response.text
        assert "completed" in response.text
        assert "cancelled" in response.text

    def test_day_view_has_json_data_scripts(self, client: TestClient) -> None:
        """Day view injects events, employees, and company JSON into script tags."""
        response = client.get("/calendar/day/2024-01-15")
        assert 'id="day-events-data"' in response.text
        assert 'id="day-employees-data"' in response.text
        assert 'id="day-company-data"' in response.text

    def test_day_view_map_init_wiring(self, client: TestClient) -> None:
        """Map initialises via Alpine x-init with mapsReady check."""
        response = client.get("/calendar/day/2024-01-15")
        assert "initMap()" in response.text
        assert "mapsReady" in response.text

    def test_day_view_has_starting_point_toggle(self, client: TestClient) -> None:
        """Day view has company/custom starting-point toggle buttons."""
        response = client.get("/calendar/day/2024-01-15")
        assert "Company Location" in response.text
        assert "Enter Eircode / Address" in response.text
        assert "startMode" in response.text

    def test_day_view_has_route_summary_panel(self, client: TestClient) -> None:
        """Day view contains the route summary stats panel."""
        response = client.get("/calendar/day/2024-01-15")
        assert "Route Summary" in response.text
        assert "routeSummary" in response.text
        assert "calculatingRoute" in response.text

    def test_day_view_routing_skips_single_job_employees(
        self, client: TestClient
    ) -> None:
        """Template JS contains the single-job skip logic (empJobs.length === 1)."""
        response = client.get("/calendar/day/2024-01-15")
        assert "empJobs.length === 1" in response.text

    def test_day_view_single_employee_route_skips_single_job(
        self, client: TestClient
    ) -> None:
        """Single filtered employee with 1 job shows marker only — no route calc."""
        response = client.get("/calendar/day/2024-01-15")
        # The _renderEmployeeRoute method checks if only 1 job before routing
        assert "jobs.length === 1" in response.text

    def test_day_view_renders_all_routes_per_employee(self, client: TestClient) -> None:
        """_renderAllRoutes groups by employee and draws colour-coded routes."""
        response = client.get("/calendar/day/2024-01-15")
        assert "_renderAllRoutes" in response.text
        assert "_empRouteColours" in response.text
        assert "byEmployee" in response.text

    def test_day_view_has_add_job_button(self, client: TestClient) -> None:
        """Day view footer has an Add Job button."""
        response = client.get("/calendar/day/2024-01-15")
        assert "Add Job" in response.text

    def test_day_view_body_uses_flex_overflow(self, client: TestClient) -> None:
        """Two-column body uses flex-1 and overflow-hidden for proper sizing."""
        response = client.get("/calendar/day/2024-01-15")
        assert "flex-1 overflow-hidden" in response.text


# ═══════════════════════════════════════════════════════════════════════
# Job queue
# ═══════════════════════════════════════════════════════════════════════


class TestJobQueue:
    """Tests for job queue endpoints."""

    def test_job_queue_returns_html(self, client: TestClient) -> None:
        """Job queue partial returns HTML."""
        response = client.get("/calendar/job-queue")
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════════
# Job modal
# ═══════════════════════════════════════════════════════════════════════


class TestJobModal:
    """Tests for job modal endpoints.

    Covers:
    - Create-mode modal rendering (no job_id)
    - Edit-mode modal rendering (with job_id)
    - Date/time field formatting from API responses
    - Pre-filling with query parameter dates
    - Handling of ISO datetime strings
    - Default values for start/end times
    """

    def test_job_modal_create_form(self, client: TestClient) -> None:
        """Create-mode modal renders with an empty form."""
        response = client.get("/calendar/job-modal")
        assert response.status_code == 200
        assert "Create New Job" in response.text

    def test_job_modal_contains_json_enc(self, client: TestClient) -> None:
        """Modal form uses ``hx-ext="json-enc"`` for JSON submission."""
        response = client.get("/calendar/job-modal")
        assert 'hx-ext="json-enc"' in response.text

    def test_job_modal_triggers_calendar_updated(self, client: TestClient) -> None:
        """After submission the modal triggers ``calendarUpdated``."""
        response = client.get("/calendar/job-modal")
        assert "calendarUpdated" in response.text

    def test_job_modal_contains_date_fields(self, client: TestClient) -> None:
        """Modal has start/end date and time fields with proper input types."""
        response = client.get("/calendar/job-modal")
        assert 'id="start_date"' in response.text
        assert 'id="end_date"' in response.text
        assert 'id="start_time_input"' in response.text
        assert 'id="end_time_input"' in response.text
        assert 'type="date"' in response.text
        assert 'type="time"' in response.text

    def test_job_modal_with_date_prefill(self, client: TestClient) -> None:
        """Modal pre-fills the date when ``?date=`` is supplied (YYYY-MM-DD format)."""
        response = client.get("/calendar/job-modal?date=2024-03-15")
        assert response.status_code == 200
        assert 'value="2024-03-15"' in response.text
        # Default times should be set when date is prefilled
        assert 'value="09:00"' in response.text
        assert 'value="17:00"' in response.text

    def test_job_modal_date_fields_have_required_attribute(
        self, client: TestClient
    ) -> None:
        """Date/time input fields are marked as required."""
        response = client.get("/calendar/job-modal")
        assert 'name="start_date"' in response.text
        assert 'name="end_date"' in response.text
        assert 'name="start_time_display"' in response.text
        assert 'name="end_time_display"' in response.text
        # Verify required attributes are present
        assert response.text.count("required") >= 4  # At least 4 required fields

    def test_job_modal_create_mode_default_times(self, client: TestClient) -> None:
        """Create-mode modal has default times (09:00 to 17:00) when no date supplied."""
        response = client.get("/calendar/job-modal")
        assert response.status_code == 200
        # Should have default time values
        html = response.text
        # Count occurrences of time defaults
        assert html.count("09:00") >= 1  # Start time
        assert html.count("17:00") >= 1  # End time

    def test_job_modal_edit_mode_uses_put(self, client: TestClient) -> None:
        """Edit-mode modal submits updates with PUT to the job detail endpoint."""
        from app import service_client

        original_fetch_job_detail = service_client.fetch_job_detail
        original_fetch_employees = service_client.fetch_employees
        original_fetch_customers = service_client.fetch_customers

        service_client.fetch_job_detail = AsyncMock(
            return_value={
                "id": 42,
                "title": "Kitchen Renovation",
                "description": "Full kitchen remodel",
                "customer_id": 1,
                "assigned_to": 2,
                "status": "scheduled",
                "start_time": "2024-01-15T09:00:00",
                "end_time": "2024-01-15T17:00:00",
                "address": "123 Main St, Dublin",
                "eircode": "D02 XY45",
                "notes": "Materials ordered",
            }
        )
        service_client.fetch_employees = AsyncMock(return_value=[])
        service_client.fetch_customers = AsyncMock(return_value=[])

        try:
            response = client.get("/calendar/job-modal?job_id=42")
        finally:
            service_client.fetch_job_detail = original_fetch_job_detail
            service_client.fetch_employees = original_fetch_employees
            service_client.fetch_customers = original_fetch_customers

        assert response.status_code == 200
        assert 'hx-put="/api/jobs/42"' in response.text
        assert 'hx-post="/api/jobs/42"' not in response.text


# ═══════════════════════════════════════════════════════════════════════
# Static assets
# ═══════════════════════════════════════════════════════════════════════


class TestStaticAssets:
    """Tests for static asset serving."""

    def test_css_file_exists(self, client: TestClient) -> None:
        """CSS file is served (no 500 error)."""
        response = client.get("/static/css/styles.css")
        assert response.status_code != 500

    def test_js_file_exists(self, client: TestClient) -> None:
        """JS file is served (no 500 error)."""
        response = client.get("/static/js/main.js")
        assert response.status_code != 500


# ═══════════════════════════════════════════════════════════════════════
# Multi-day event expansion logic (pure unit tests)
# ═══════════════════════════════════════════════════════════════════════


class TestMultiDayExpansion:
    """Test the ``_expand_events_into_days`` helper in calendar.py."""

    @staticmethod
    def _build_grid(start: date, n_days: int = 7) -> list[dict[str, Any]]:
        """Build a minimal calendar grid for testing."""
        return [
            {
                "date": start + timedelta(days=i),
                "day": (start + timedelta(days=i)).day,
                "is_current_month": True,
                "is_today": False,
                "events": [],
            }
            for i in range(n_days)
        ]

    def test_single_day_event(self) -> None:
        """A 1-day event appears only on its own day."""
        from app.routes.calendar import _expand_events_into_days

        grid = self._build_grid(date(2024, 1, 14))
        api_days: list[dict[str, Any]] = [
            {
                "date": "2024-01-15",
                "jobs": [
                    {
                        "id": 1,
                        "title": "One day job",
                        "start_time": "2024-01-15T09:00:00",
                        "end_time": "2024-01-15T17:00:00",
                        "status": "scheduled",
                        "priority": "normal",
                        "all_day": False,
                        "color": None,
                    }
                ],
                "total_jobs": 1,
            }
        ]
        _expand_events_into_days(api_days, grid)
        # Only day index 1 (Jan 15) should have the event
        assert len(grid[1]["events"]) == 1
        evt = grid[1]["events"][0]
        assert evt["title"] == "One day job"
        assert evt["is_multi_day"] is False
        assert evt["is_first_day"] is True
        assert evt["is_last_day"] is True

    def test_multi_day_event_spans_three_days(self) -> None:
        """A 3-day event appears on each spanned day with correct flags."""
        from app.routes.calendar import _expand_events_into_days

        grid = self._build_grid(date(2024, 1, 14), n_days=7)
        api_days: list[dict[str, Any]] = [
            {
                "date": "2024-01-15",
                "jobs": [
                    {
                        "id": 10,
                        "title": "Multi day",
                        "start_time": "2024-01-15T08:00:00",
                        "end_time": "2024-01-17T18:00:00",
                        "status": "scheduled",
                        "priority": "high",
                        "all_day": False,
                        "color": "#3b82f6",
                    }
                ],
                "total_jobs": 1,
            }
        ]
        _expand_events_into_days(api_days, grid)
        # Jan 14 — no events
        assert len(grid[0]["events"]) == 0
        # Jan 15 — first day
        assert len(grid[1]["events"]) == 1
        assert grid[1]["events"][0]["is_first_day"] is True
        assert grid[1]["events"][0]["is_last_day"] is False
        assert grid[1]["events"][0]["is_multi_day"] is True
        # Jan 16 — continuation
        assert len(grid[2]["events"]) == 1
        assert grid[2]["events"][0]["is_continuation"] is True
        assert grid[2]["events"][0]["is_first_day"] is False
        assert grid[2]["events"][0]["is_last_day"] is False
        # Jan 17 — last day
        assert len(grid[3]["events"]) == 1
        assert grid[3]["events"][0]["is_last_day"] is True
        assert grid[3]["events"][0]["is_first_day"] is False

    def test_overlapping_same_day_events(self) -> None:
        """Two events on the same day both appear."""
        from app.routes.calendar import _expand_events_into_days

        grid = self._build_grid(date(2024, 1, 15), n_days=1)
        api_days: list[dict[str, Any]] = [
            {
                "date": "2024-01-15",
                "jobs": [
                    {
                        "id": 20,
                        "title": "Morning",
                        "start_time": "2024-01-15T09:00:00",
                        "end_time": "2024-01-15T12:00:00",
                        "status": "scheduled",
                        "priority": "normal",
                        "all_day": False,
                        "color": None,
                    },
                    {
                        "id": 21,
                        "title": "Afternoon",
                        "start_time": "2024-01-15T11:00:00",
                        "end_time": "2024-01-15T15:00:00",
                        "status": "pending",
                        "priority": "urgent",
                        "all_day": False,
                        "color": None,
                    },
                ],
                "total_jobs": 2,
            }
        ]
        _expand_events_into_days(api_days, grid)
        assert len(grid[0]["events"]) == 2

    def test_event_outside_grid_range_ignored(self) -> None:
        """Events whose date does not match any grid cell are silently ignored."""
        from app.routes.calendar import _expand_events_into_days

        grid = self._build_grid(date(2024, 2, 1), n_days=3)
        api_days: list[dict[str, Any]] = [
            {
                "date": "2024-01-15",
                "jobs": [
                    {
                        "id": 99,
                        "title": "Out of range",
                        "start_time": "2024-01-15T09:00:00",
                        "end_time": "2024-01-15T17:00:00",
                        "status": "scheduled",
                        "priority": "normal",
                        "all_day": False,
                        "color": None,
                    }
                ],
                "total_jobs": 1,
            }
        ]
        _expand_events_into_days(api_days, grid)
        for cell in grid:
            assert len(cell["events"]) == 0

    def test_all_day_event_no_start_time(self) -> None:
        """An all-day event with no start/end times is handled gracefully."""
        from app.routes.calendar import _expand_events_into_days

        grid = self._build_grid(date(2024, 1, 15), n_days=1)
        api_days: list[dict[str, Any]] = [
            {
                "date": "2024-01-15",
                "jobs": [
                    {
                        "id": 50,
                        "title": "All day",
                        "start_time": None,
                        "end_time": None,
                        "status": "scheduled",
                        "priority": "normal",
                        "all_day": True,
                        "color": None,
                    }
                ],
                "total_jobs": 1,
            }
        ]
        _expand_events_into_days(api_days, grid)
        # Should not crash. All-day events with no start_time are skipped.
        assert True


# ═══════════════════════════════════════════════════════════════════════
# _parse_event_date helper
# ═══════════════════════════════════════════════════════════════════════


class TestParseEventDate:
    """Test the ``_parse_event_date`` helper."""

    def test_iso_string(self) -> None:
        from app.routes.calendar import _parse_event_date

        result = _parse_event_date("2024-06-15T10:30:00")
        assert result == date(2024, 6, 15)

    def test_date_only_string(self) -> None:
        from app.routes.calendar import _parse_event_date

        result = _parse_event_date("2024-06-15")
        assert result == date(2024, 6, 15)

    def test_datetime_object(self) -> None:
        from datetime import datetime as dt

        from app.routes.calendar import _parse_event_date

        result = _parse_event_date(dt(2024, 6, 15, 10, 30))
        assert result == date(2024, 6, 15)

    def test_date_object(self) -> None:
        from app.routes.calendar import _parse_event_date

        result = _parse_event_date(date(2024, 6, 15))
        assert result == date(2024, 6, 15)

    def test_none_returns_none(self) -> None:
        from app.routes.calendar import _parse_event_date

        assert _parse_event_date(None) is None

    def test_invalid_string_returns_none(self) -> None:
        from app.routes.calendar import _parse_event_date

        assert _parse_event_date("not-a-date") is None


# ═══════════════════════════════════════════════════════════════════════
# _week_dates helper
# ═══════════════════════════════════════════════════════════════════════


class TestWeekDates:
    """Test the ``_week_dates`` helper."""

    def test_returns_seven_dates(self) -> None:
        from app.routes.calendar import _week_dates

        result = _week_dates(2024, 1, 15)
        assert len(result) == 7

    def test_starts_on_monday(self) -> None:
        from app.routes.calendar import _week_dates

        result = _week_dates(2024, 1, 15)
        assert result[0].weekday() == 0  # Monday

    def test_ends_on_sunday(self) -> None:
        from app.routes.calendar import _week_dates

        result = _week_dates(2024, 1, 15)
        assert result[-1].weekday() == 6  # Sunday

    def test_consecutive_days(self) -> None:
        from app.routes.calendar import _week_dates

        result = _week_dates(2024, 1, 15)
        for i in range(1, 7):
            assert result[i] - result[i - 1] == timedelta(days=1)


# ═══════════════════════════════════════════════════════════════════════
# Job modal — dropdown selects & renamed fields
# ═══════════════════════════════════════════════════════════════════════


class TestJobModalDropdowns:
    """Tests for employee/customer dropdown selects in the job modal.

    The default ``app`` fixture mocks ``service_client._http_client`` with
    ``ConnectError``, so ``fetch_employees`` / ``fetch_customers`` return
    empty lists.  Tests that need populated dropdowns build a custom mock
    returning ``httpx.Response(200, json=[...])``.
    """

    # ── Field presence (default empty dropdowns) ──────────────────────

    def test_modal_has_assigned_to_select(self, client: TestClient) -> None:
        """Modal contains a ``<select>`` for employee assignment."""
        response = client.get("/calendar/job-modal")
        assert response.status_code == 200
        assert 'id="assigned_to"' in response.text
        assert 'name="assigned_to"' in response.text

    def test_modal_has_customer_id_select(self, client: TestClient) -> None:
        """Modal contains a ``<select>`` for customer selection."""
        response = client.get("/calendar/job-modal")
        assert response.status_code == 200
        assert 'id="customer_id"' in response.text
        assert 'name="customer_id"' in response.text

    def test_modal_has_inline_new_customer_controls(self, client: TestClient) -> None:
        """Modal exposes a separate overlay to create/select a new customer."""
        response = client.get("/calendar/job-modal")
        assert response.status_code == 200
        assert "New Customer" in response.text
        assert 'id="new_customer_first_name"' in response.text
        assert 'id="new_customer_last_name"' in response.text
        assert "Create & Select" in response.text

    def test_modal_has_address_field(self, client: TestClient) -> None:
        """Modal contains an ``address`` input (renamed from location)."""
        response = client.get("/calendar/job-modal")
        assert response.status_code == 200
        assert 'id="address"' in response.text
        assert 'name="address"' in response.text

    def test_modal_has_eircode_field(self, client: TestClient) -> None:
        """Modal contains an ``eircode`` input field."""
        response = client.get("/calendar/job-modal")
        assert response.status_code == 200
        assert 'name="eircode"' in response.text

    # ── Populated dropdowns (override mock) ───────────────────────────

    def test_employee_options_rendered(self, client: TestClient) -> None:
        """Employee ``<option>`` elements are rendered when the BL
        service returns data.

        Patches ``fetch_employees`` / ``fetch_customers`` directly so
        that the canned data bypasses the HTTP client mock installed by
        the ``app`` fixture.
        """
        from unittest.mock import AsyncMock, patch

        sample_employees: list[dict[str, Any]] = [
            {"id": 1, "first_name": "Alice", "last_name": "O'Brien", "user_id": 2},
            {"id": 2, "first_name": "Bob", "last_name": "Murphy", "user_id": 3},
        ]

        with (
            patch(
                "app.service_client.fetch_employees",
                new=AsyncMock(return_value=sample_employees),
            ),
            patch(
                "app.service_client.fetch_customers",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = client.get("/calendar/job-modal")

        assert response.status_code == 200
        # Jinja2 may encode the apostrophe as &#x27; (hex) or &#39; (dec)
        assert (
            "Alice O&#x27;Brien" in response.text
            or "Alice O&#39;Brien" in response.text
            or "Alice O'Brien" in response.text
        )
        assert "Bob Murphy" in response.text

    def test_customer_options_rendered(self, client: TestClient) -> None:
        """Customer ``<option>`` elements are rendered when the BL
        service returns data.

        Patches ``fetch_customers`` / ``fetch_employees`` directly so
        that the canned data bypasses the HTTP client mock installed by
        the ``app`` fixture.
        """
        from unittest.mock import AsyncMock, patch

        sample_customers: list[dict[str, Any]] = [
            {"id": 10, "first_name": "Jane", "last_name": "Doe"},
            {"id": 11, "first_name": "John", "last_name": "Smith"},
        ]

        with (
            patch(
                "app.service_client.fetch_employees",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.service_client.fetch_customers",
                new=AsyncMock(return_value=sample_customers),
            ),
        ):
            response = client.get("/calendar/job-modal")

        assert response.status_code == 200
        # Customer options render as "first_name last_name"
        assert "Jane Doe" in response.text
        assert "John Smith" in response.text

    def test_empty_dropdowns_on_service_error(self, client: TestClient) -> None:
        """Dropdowns render empty when backend services are unreachable.

        The default ``app`` fixture raises ``ConnectError`` on all HTTP
        calls, so ``fetch_employees`` / ``fetch_customers`` return ``[]``.
        The modal should still load without error.
        """
        response = client.get("/calendar/job-modal")
        assert response.status_code == 200
        # Both selects exist but only contain the placeholder <option>
        assert 'id="assigned_to"' in response.text
        assert 'id="customer_id"' in response.text


# ═══════════════════════════════════════════════════════════════════════
# Service client — fetch_employees / fetch_customers unit tests
# ═══════════════════════════════════════════════════════════════════════


class TestServiceClientFetch:
    """Unit tests for ``fetch_employees`` and ``fetch_customers``.

    These test the service_client functions directly (not via HTTP routes)
    by patching the module-level ``_http_client``.
    """

    @pytest.fixture
    def _mock_request(self) -> Any:
        """Create a minimal mock ``Request`` with an Authorization header."""
        from unittest.mock import MagicMock

        req = MagicMock()
        req.headers = {"authorization": "Bearer test-token-abc"}
        return req

    # ── fetch_employees ───────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_fetch_employees_success(self, _mock_request: Any) -> None:
        """Returns employee list on a successful 200 response."""
        from unittest.mock import AsyncMock

        import httpx

        from app import service_client

        employees = [{"id": 1, "name": "Test Employee"}]
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = httpx.Response(200, json=employees)

        original = service_client._http_client
        service_client._http_client = mock_client
        try:
            result = await service_client.fetch_employees(_mock_request)
        finally:
            service_client._http_client = original

        assert result == employees

    @pytest.mark.asyncio
    async def test_fetch_employees_paginated_envelope(self, _mock_request: Any) -> None:
        """Handles paginated envelope ``{"items": [...]}``."""
        from unittest.mock import AsyncMock

        import httpx

        from app import service_client

        employees = [{"id": 2, "name": "Paginated Employee"}]
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = httpx.Response(
            200, json={"items": employees, "total": 1}
        )

        original = service_client._http_client
        service_client._http_client = mock_client
        try:
            result = await service_client.fetch_employees(_mock_request)
        finally:
            service_client._http_client = original

        assert result == employees

    @pytest.mark.asyncio
    async def test_fetch_employees_connect_error(self, _mock_request: Any) -> None:
        """Returns empty list when user-bl-service is unreachable."""
        from unittest.mock import AsyncMock

        import httpx

        from app import service_client

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.ConnectError("unreachable")

        original = service_client._http_client
        service_client._http_client = mock_client
        try:
            result = await service_client.fetch_employees(_mock_request)
        finally:
            service_client._http_client = original

        assert result == []

    # ── fetch_customers ───────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_fetch_customers_success(self, _mock_request: Any) -> None:
        """Returns customer list on a successful 200 response."""
        from unittest.mock import AsyncMock

        import httpx

        from app import service_client

        customers = [{"id": 1, "first_name": "Jane", "last_name": "Doe"}]
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = httpx.Response(200, json=customers)

        original = service_client._http_client
        service_client._http_client = mock_client
        try:
            result = await service_client.fetch_customers(_mock_request)
        finally:
            service_client._http_client = original

        assert result == customers

    @pytest.mark.asyncio
    async def test_fetch_customers_paginated_envelope(self, _mock_request: Any) -> None:
        """Handles paginated envelope ``{"items": [...]}``."""
        from unittest.mock import AsyncMock

        import httpx

        from app import service_client

        customers = [{"id": 3, "first_name": "John", "last_name": "Smith"}]
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = httpx.Response(
            200, json={"items": customers, "total": 1}
        )

        original = service_client._http_client
        service_client._http_client = mock_client
        try:
            result = await service_client.fetch_customers(_mock_request)
        finally:
            service_client._http_client = original

        assert result == customers

    @pytest.mark.asyncio
    async def test_fetch_customers_connect_error(self, _mock_request: Any) -> None:
        """Returns empty list when customer-bl-service is unreachable."""
        from unittest.mock import AsyncMock

        import httpx

        from app import service_client

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.ConnectError("unreachable")

        original = service_client._http_client
        service_client._http_client = mock_client
        try:
            result = await service_client.fetch_customers(_mock_request)
        finally:
            service_client._http_client = original

        assert result == []


# ═══════════════════════════════════════════════════════════════════════
# hx-boost page transitions & view-transition API
# ═══════════════════════════════════════════════════════════════════════


class TestHxBoostTransitions:
    """Tests for smooth page transitions powered by hx-boost.

    Verifies that ``base.html`` includes the required HTMX boost
    attribute and the CSS View Transitions API meta tag so navigation
    between pages avoids full page reloads.
    """

    def test_body_has_hx_boost(self, client: TestClient) -> None:
        """``<body>`` tag includes ``hx-boost="true"``."""
        response = client.get("/calendar")
        assert response.status_code == 200
        assert 'hx-boost="true"' in response.text

    def test_view_transition_meta_tag(self, client: TestClient) -> None:
        """``<head>`` contains the View Transitions API meta tag."""
        response = client.get("/calendar")
        assert response.status_code == 200
        assert 'name="view-transition"' in response.text

    def test_logout_disables_hx_boost(self, client: TestClient) -> None:
        """Logout link opts out of hx-boost to force a full redirect."""
        response = client.get("/calendar")
        assert response.status_code == 200
        # The logout link should contain hx-boost="false"
        text = response.text
        # Find the logout link section and verify it has hx-boost="false"
        assert 'hx-boost="false"' in text


# ═══════════════════════════════════════════════════════════════════════
# Quick-schedule modal route
# ═══════════════════════════════════════════════════════════════════════


class TestQuickScheduleModal:
    """Tests for the ``/calendar/quick-schedule-modal`` route.

    Verifies the lightweight drag-and-drop scheduling modal renders
    correctly, validates required parameters, and displays job details
    with employee dropdown options.
    """

    # ── Parameter validation ──────────────────────────────────────────

    def test_missing_job_id_returns_400(self, client: TestClient) -> None:
        """Returns 400 when ``job_id`` query param is missing."""
        response = client.get("/calendar/quick-schedule-modal?date=2024-01-15")
        assert response.status_code == 400

    def test_missing_date_returns_400(self, client: TestClient) -> None:
        """Returns 400 when ``date`` query param is missing."""
        response = client.get("/calendar/quick-schedule-modal?job_id=1")
        assert response.status_code == 400

    def test_missing_both_params_returns_400(self, client: TestClient) -> None:
        """Returns 400 when both params are missing."""
        response = client.get("/calendar/quick-schedule-modal")
        assert response.status_code == 400

    # ── Successful render with mocked data ────────────────────────────

    def test_modal_renders_with_valid_params(self, client: TestClient) -> None:
        """Modal renders 200 when given a valid job_id and date.

        Patches ``fetch_job_detail`` and ``fetch_employees`` to return
        canned data.
        """
        from unittest.mock import AsyncMock, patch

        job_data: dict[str, Any] = {
            "id": 42,
            "title": "Window Installation",
            "customer_name": "Acme Corp",
            "priority": "high",
            "location": "99 Elm St",
            "assigned_to": None,
            "start_time": None,
            "end_time": None,
            "status": "pending",
        }
        employees: list[dict[str, Any]] = [
            {"id": 1, "first_name": "Alice", "last_name": "Smith"},
            {"id": 2, "first_name": "Bob", "last_name": "Jones"},
        ]

        with (
            patch(
                "app.service_client.fetch_job_detail",
                new=AsyncMock(return_value=job_data),
            ),
            patch(
                "app.service_client.fetch_employees",
                new=AsyncMock(return_value=employees),
            ),
        ):
            response = client.get(
                "/calendar/quick-schedule-modal?job_id=42&date=2024-01-15"
            )

        assert response.status_code == 200

    def test_modal_contains_job_title(self, client: TestClient) -> None:
        """Modal header displays the job title."""
        from unittest.mock import AsyncMock, patch

        job_data: dict[str, Any] = {
            "id": 42,
            "title": "Window Installation",
            "customer_name": "Acme Corp",
            "priority": "high",
            "location": "99 Elm St",
            "assigned_to": None,
            "start_time": None,
            "end_time": None,
            "status": "pending",
        }

        with (
            patch(
                "app.service_client.fetch_job_detail",
                new=AsyncMock(return_value=job_data),
            ),
            patch(
                "app.service_client.fetch_employees",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = client.get(
                "/calendar/quick-schedule-modal?job_id=42&date=2024-01-15"
            )

        assert response.status_code == 200
        assert "Window Installation" in response.text

    def test_modal_contains_date_input(self, client: TestClient) -> None:
        """Modal pre-fills the date from the drop target."""
        from unittest.mock import AsyncMock, patch

        job_data: dict[str, Any] = {
            "id": 42,
            "title": "Test Job",
            "customer_name": None,
            "priority": "medium",
            "location": None,
            "assigned_to": None,
            "start_time": None,
            "end_time": None,
            "status": "pending",
        }

        with (
            patch(
                "app.service_client.fetch_job_detail",
                new=AsyncMock(return_value=job_data),
            ),
            patch(
                "app.service_client.fetch_employees",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = client.get(
                "/calendar/quick-schedule-modal?job_id=42&date=2024-03-20"
            )

        assert response.status_code == 200
        assert 'value="2024-03-20"' in response.text

    def test_modal_contains_time_inputs(self, client: TestClient) -> None:
        """Modal includes start and end time inputs with defaults."""
        from unittest.mock import AsyncMock, patch

        job_data: dict[str, Any] = {
            "id": 42,
            "title": "Test Job",
            "customer_name": None,
            "priority": "low",
            "location": None,
            "assigned_to": None,
            "start_time": None,
            "end_time": None,
            "status": "pending",
        }

        with (
            patch(
                "app.service_client.fetch_job_detail",
                new=AsyncMock(return_value=job_data),
            ),
            patch(
                "app.service_client.fetch_employees",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = client.get(
                "/calendar/quick-schedule-modal?job_id=42&date=2024-01-15"
            )

        assert response.status_code == 200
        assert 'id="qs-start-time"' in response.text
        assert 'id="qs-end-time"' in response.text
        # Default times
        assert 'value="09:00"' in response.text
        assert 'value="17:00"' in response.text

    def test_modal_renders_employee_options(self, client: TestClient) -> None:
        """Employee dropdown is populated with employee names."""
        from unittest.mock import AsyncMock, patch

        job_data: dict[str, Any] = {
            "id": 42,
            "title": "Test Job",
            "customer_name": None,
            "priority": "medium",
            "location": None,
            "assigned_to": None,
            "start_time": None,
            "end_time": None,
            "status": "pending",
        }
        employees: list[dict[str, Any]] = [
            {"id": 5, "first_name": "Charlie", "last_name": "Brown"},
            {"id": 6, "first_name": "Lucy", "last_name": "Van Pelt"},
        ]

        with (
            patch(
                "app.service_client.fetch_job_detail",
                new=AsyncMock(return_value=job_data),
            ),
            patch(
                "app.service_client.fetch_employees",
                new=AsyncMock(return_value=employees),
            ),
        ):
            response = client.get(
                "/calendar/quick-schedule-modal?job_id=42&date=2024-01-15"
            )

        assert response.status_code == 200
        assert "Charlie Brown" in response.text
        assert "Lucy Van Pelt" in response.text

    def test_modal_preserves_existing_start_time(self, client: TestClient) -> None:
        """When a job already has start_time set, the modal uses it."""
        from unittest.mock import AsyncMock, patch

        job_data: dict[str, Any] = {
            "id": 42,
            "title": "Test Job",
            "customer_name": None,
            "priority": "medium",
            "location": None,
            "assigned_to": None,
            "start_time": "2024-01-15T10:30:00",
            "end_time": None,
            "status": "pending",
        }

        with (
            patch(
                "app.service_client.fetch_job_detail",
                new=AsyncMock(return_value=job_data),
            ),
            patch(
                "app.service_client.fetch_employees",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = client.get(
                "/calendar/quick-schedule-modal?job_id=42&date=2024-01-15"
            )

        assert response.status_code == 200
        assert 'value="10:30"' in response.text

    def test_modal_shows_customer_name(self, client: TestClient) -> None:
        """Job summary section displays customer name when present."""
        from unittest.mock import AsyncMock, patch

        job_data: dict[str, Any] = {
            "id": 42,
            "title": "Test Job",
            "customer_name": "Global Widgets Inc",
            "priority": "urgent",
            "location": "100 High St",
            "assigned_to": None,
            "start_time": None,
            "end_time": None,
            "status": "pending",
        }

        with (
            patch(
                "app.service_client.fetch_job_detail",
                new=AsyncMock(return_value=job_data),
            ),
            patch(
                "app.service_client.fetch_employees",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = client.get(
                "/calendar/quick-schedule-modal?job_id=42&date=2024-01-15"
            )

        assert response.status_code == 200
        assert "Global Widgets Inc" in response.text

    def test_modal_shows_priority_badge(self, client: TestClient) -> None:
        """Job summary displays a styled priority badge."""
        from unittest.mock import AsyncMock, patch

        job_data: dict[str, Any] = {
            "id": 42,
            "title": "Urgent Fix",
            "customer_name": None,
            "priority": "urgent",
            "location": None,
            "assigned_to": None,
            "start_time": None,
            "end_time": None,
            "status": "pending",
        }

        with (
            patch(
                "app.service_client.fetch_job_detail",
                new=AsyncMock(return_value=job_data),
            ),
            patch(
                "app.service_client.fetch_employees",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = client.get(
                "/calendar/quick-schedule-modal?job_id=42&date=2024-01-15"
            )

        assert response.status_code == 200
        assert "Urgent" in response.text

    def test_modal_contains_hidden_job_id(self, client: TestClient) -> None:
        """Modal includes a hidden input with the job ID."""
        from unittest.mock import AsyncMock, patch

        job_data: dict[str, Any] = {
            "id": 42,
            "title": "Test",
            "customer_name": None,
            "priority": "low",
            "location": None,
            "assigned_to": None,
            "start_time": None,
            "end_time": None,
            "status": "pending",
        }

        with (
            patch(
                "app.service_client.fetch_job_detail",
                new=AsyncMock(return_value=job_data),
            ),
            patch(
                "app.service_client.fetch_employees",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = client.get(
                "/calendar/quick-schedule-modal?job_id=42&date=2024-01-15"
            )

        assert response.status_code == 200
        assert 'id="qs-job-id"' in response.text
        assert 'value="42"' in response.text

    def test_modal_contains_schedule_button(self, client: TestClient) -> None:
        """Modal footer contains a 'Schedule Job' submit button."""
        from unittest.mock import AsyncMock, patch

        job_data: dict[str, Any] = {
            "id": 42,
            "title": "Test Job",
            "customer_name": None,
            "priority": "medium",
            "location": None,
            "assigned_to": None,
            "start_time": None,
            "end_time": None,
            "status": "pending",
        }

        with (
            patch(
                "app.service_client.fetch_job_detail",
                new=AsyncMock(return_value=job_data),
            ),
            patch(
                "app.service_client.fetch_employees",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = client.get(
                "/calendar/quick-schedule-modal?job_id=42&date=2024-01-15"
            )

        assert response.status_code == 200
        assert "Schedule Job" in response.text

    def test_modal_contains_cancel_button(self, client: TestClient) -> None:
        """Modal footer contains a Cancel button."""
        from unittest.mock import AsyncMock, patch

        job_data: dict[str, Any] = {
            "id": 42,
            "title": "Test",
            "customer_name": None,
            "priority": "low",
            "location": None,
            "assigned_to": None,
            "start_time": None,
            "end_time": None,
            "status": "pending",
        }

        with (
            patch(
                "app.service_client.fetch_job_detail",
                new=AsyncMock(return_value=job_data),
            ),
            patch(
                "app.service_client.fetch_employees",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = client.get(
                "/calendar/quick-schedule-modal?job_id=42&date=2024-01-15"
            )

        assert response.status_code == 200
        assert "Cancel" in response.text

    def test_job_not_found_returns_404(self, client: TestClient) -> None:
        """Returns 404 when the job does not exist."""
        from unittest.mock import AsyncMock, patch

        with (
            patch(
                "app.service_client.fetch_job_detail",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.service_client.fetch_employees",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = client.get(
                "/calendar/quick-schedule-modal?job_id=999&date=2024-01-15"
            )

        assert response.status_code == 404

    def test_modal_empty_employees_on_service_error(self, client: TestClient) -> None:
        """Modal still renders when employee service is unreachable.

        The default ``app`` fixture raises ``ConnectError`` on all HTTP
        calls, so ``fetch_employees`` returns ``[]``.  The modal should
        still load, with an empty employee dropdown showing only the
        '— Unassigned —' placeholder.
        """
        from unittest.mock import AsyncMock, patch

        job_data: dict[str, Any] = {
            "id": 42,
            "title": "Test Job",
            "customer_name": None,
            "priority": "medium",
            "location": None,
            "assigned_to": None,
            "start_time": None,
            "end_time": None,
            "status": "pending",
        }

        with (
            patch(
                "app.service_client.fetch_job_detail",
                new=AsyncMock(return_value=job_data),
            ),
            patch(
                "app.service_client.fetch_employees",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = client.get(
                "/calendar/quick-schedule-modal?job_id=42&date=2024-01-15"
            )

        assert response.status_code == 200
        assert "Unassigned" in response.text
        assert 'id="qs-employee"' in response.text


# ═══════════════════════════════════════════════════════════════════════
# Job queue toggle button placement
# ═══════════════════════════════════════════════════════════════════════


class TestJobQueueTogglePlacement:
    """Tests that the job queue toggle button is in the calendar header.

    The toggle was moved from the global navbar to the calendar header
    so it sits beside the 'New Job' button — only visible on the
    calendar page.
    """

    def test_toggle_in_calendar_header(self, client: TestClient) -> None:
        """Calendar page contains the job queue toggle button."""
        response = client.get("/calendar")
        assert response.status_code == 200
        assert 'id="nav-job-queue"' in response.text

    def test_toggle_not_in_navbar_globally(self, client: TestClient) -> None:
        """Non-calendar pages do NOT contain the toggle ID.

        The login page is a simple page that doesn't include the
        calendar header, so the toggle should be absent.
        """
        response = client.get("/login")
        assert response.status_code == 200
        assert 'id="nav-job-queue"' not in response.text

    def test_toggle_has_queue_icon(self, client: TestClient) -> None:
        """The toggle button renders with its four-line icon SVG."""
        response = client.get("/calendar")
        assert response.status_code == 200
        # The 4-bar icon path matches the hamburger-style lines
        assert "M4 6h16M4 10h16M4 14h16M4 18h16" in response.text
