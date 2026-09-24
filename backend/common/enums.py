"""Shared enums for modular backend contracts and runtime constants."""

from __future__ import annotations

from common.data_model import ExtendedStrEnum


class ModuleStatus(ExtendedStrEnum):
    READY = "ready"


class AuditMetadataType(ExtendedStrEnum):
    ENTITY = "entity"
    TRANSITION = "transition"
    AUTH = "auth"
    SCHEDULE = "schedule"


class WorkflowPermissionKey(ExtendedStrEnum):
    """Catalog `permission_key` values for the `workflow` resource — must
    match `permissions/models/interface.py::DEFAULT_PERMISSION_DEFINITIONS`'
    entries for `resource == "workflow"`. Shared here (not owned by either
    module's own `models/interface.py`) since both `roles` and `workflow`
    need it and neither should reach into the other's internals."""

    READ = "workflow:read"
    WRITE = "workflow:write"


class DefaultRole(ExtendedStrEnum):
    SUPERADMIN = "superadmin"
    VIEWER = "viewer"
    RECRUITER = "recruiter"
    ADMIN = "admin"
    OWNER = "owner"


class SortOrder(ExtendedStrEnum):
    ASC = "asc"
    DESC = "desc"


class DocumentStatus(ExtendedStrEnum):
    PENDING = "PENDING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class IntakeJobStatus(ExtendedStrEnum):
    UPLOADED = "UPLOADED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    COMMITTING = "COMMITTING"
    CANCELLING = "CANCELLING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class IntegrationProvider(ExtendedStrEnum):
    GOOGLE = "google"
    OUTLOOK = "outlook"
    ICS = "ics"


class ProjectionSlaRisk(ExtendedStrEnum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    OK = "OK"


class NotificationStatus(ExtendedStrEnum):
    QUEUED = "queued"


class NotificationChannel(ExtendedStrEnum):
    IN_APP = "in_app"
    EMAIL = "email"


class DomainPackAction(ExtendedStrEnum):
    INSTALL = "install"
    ACTIVATE = "activate"


class DomainPackHookPort(ExtendedStrEnum):
    INTAKE_ENRICHMENT = "intake_enrichment_hook"
    PROJECTION_ENRICHMENT = "projection_enrichment_hook"
    AUTOMATION_ACTION = "automation_action_hook"
