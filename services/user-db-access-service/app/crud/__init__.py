"""CRUD package for user-service."""

from .user import (
    get_user, get_user_by_email, get_users, create_user, 
    update_user, delete_user, authenticate_user,
    get_employee, get_employee_by_user_id, get_employees_by_owner,
    create_employee, update_employee,
    get_company, create_company, update_company,
    get_organizations, get_organization, get_organization_by_slug,
    create_organization, update_organization, suspend_organization, unsuspend_organization,
    get_audit_logs, create_audit_log,
    get_platform_settings, get_platform_setting, upsert_platform_setting,
    get_password_hash, verify_password
)

__all__ = [
    "get_user", "get_user_by_email", "get_users", "create_user",
    "update_user", "delete_user", "authenticate_user",
    "get_employee", "get_employee_by_user_id", "get_employees_by_owner",
    "create_employee", "update_employee",
    "get_company", "create_company", "update_company",
    "get_organizations", "get_organization", "get_organization_by_slug",
    "create_organization", "update_organization", "suspend_organization", "unsuspend_organization",
    "get_audit_logs", "create_audit_log",
    "get_platform_settings", "get_platform_setting", "upsert_platform_setting",
    "get_password_hash", "verify_password"
]
