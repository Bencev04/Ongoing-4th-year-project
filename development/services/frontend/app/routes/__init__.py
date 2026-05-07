"""Routes package for frontend service."""

from . import api_proxy, auth, calendar, customers, employees, legal, map

__all__ = ["auth", "calendar", "api_proxy", "customers", "employees", "legal", "map"]
