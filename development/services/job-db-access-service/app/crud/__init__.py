"""CRUD package for job-service."""

from .job import (
    assign_employee_to_job,
    create_job,
    create_job_history,
    delete_job,
    get_job,
    get_job_employees,
    get_job_history,
    get_jobs,
    get_jobs_for_calendar,
    get_unscheduled_jobs,
    remove_employee_from_job,
    update_job,
    update_job_status,
)

__all__ = [
    "get_job",
    "get_jobs",
    "get_jobs_for_calendar",
    "get_unscheduled_jobs",
    "create_job",
    "update_job",
    "update_job_status",
    "delete_job",
    "create_job_history",
    "get_job_history",
    "assign_employee_to_job",
    "get_job_employees",
    "remove_employee_from_job",
]
