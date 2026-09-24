"""Modular backend application entrypoint."""

from __future__ import annotations

import asyncio
import os
import time
import warnings
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import uvicorn
from fastapi import APIRouter, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

import mail.models  # noqa: F401
from actions.controller import ActionsRestController
from actions.db_models import ActionsModelService
from actions.manager import ActionsServiceManager
from agent.controller import AgentRestController
from agent.db_models import AgentModelService
from agent.manager import AgentServiceManager
from agent.models.interface import AgentTemplateContract
from analytics.controller import AnalyticsRestController
from analytics.db_models import AnalyticsModelService
from analytics.manager import AnalyticsServiceManager
from audit.controller import AuditRestController
from audit.db_models import AuditEventsModelService
from audit.manager import AuditServiceManager
from auth.controller import AuthRestController
from auth.db_models import AuthModelService
from auth.manager import AuthServiceManager
from background_jobs.controller import BackgroundJobsRestController
from background_jobs.db_models import BackgroundJobsModelService
from background_jobs.manager import BackgroundJobsServiceManager
from blob_storage.service import BlobStorageService
from bootstrap.runner import run_bootstrap
from bulk_import.controller import BulkImportRestController
from bulk_import.manager import BulkImportServiceManager
from bulk_import.services.relation_bindings import BulkImportRelationBindingService
from bulk_import.services.spreadsheet import SpreadsheetImportService
from comments.controller import CommentsRestController
from comments.db_models import CommentModelService
from comments.manager import CommentsServiceManager
from common.auth import register_membership_db_service, register_roles_db_service
from common.configuration import Configuration, get_configuration
from common.logger import logger, tracer
from communications.controller import CommunicationsRestController
from communications.db_models import CommunicationsModelService
from communications.manager import CommunicationsServiceManager
from connectors.controller import ConnectorsRestController
from connectors.db_models import ConnectorsModelService
from connectors.manager import ConnectorsServiceManager
from dashboard.controller import DashboardRestController
from dashboard.db_models import DashboardModelService
from dashboard.manager import DashboardServiceManager
from database.manager import DatabaseServiceManager
from documents.controller import DocumentsRestController
from documents.db_models import DocumentsModelService
from documents.manager import DocumentsServiceManager
from custom_forms.controller import CustomFormsRestController
from custom_forms.manager import CustomFormsServiceManager
from entities.controller import EntitiesRestController
from entities.db_models import EntitiesModelService
from entities.manager import EntitiesServiceManager
from executor.controller import ExecutorRestController
from executor.manager import ExecutorServiceManager
from field_library.controller import FieldLibraryRestController
from field_library.db_models import FieldLibraryModelService, FormFieldLinkModelService
from field_library.manager import FieldLibraryServiceManager
from filehandler.controller import FilehandlerRestController
from filehandler.db_models import FilehandlerModelService
from filehandler.manager import FilehandlerServiceManager
from fileprocessor.manager import FileprocessorServiceManager
from forms.controller import FormsRestController
from forms.db_models import FormsModelService
from forms.manager import FormsServiceManager
from health.controller import HealthRestController
from health.manager import HealthServiceManager
from integrations.controller import IntegrationsRestController
from integrations.db_models import IntegrationsModelService
from integrations.manager import IntegrationsServiceManager
from invitation.controller import InvitationRestController
from invitation.db_models import InvitationModelService
from invitation.manager import InvitationServiceManager
from llm.controller import LlmRestController
from llm.db_models import LlmModelService
from llm.manager import LlmServiceManager
from mail.controller import MailRestController
from mail.db_models import MailModelService
from mail.manager import MailServiceManager
from mcp.controller import McpRestController
from mcp.db_models import McpModelService
from mcp.manager import McpServiceManager
from method_library.controller import MethodLibraryRestController
from method_library.db_models import MethodLibraryModelService
from method_library.manager import MethodLibraryServiceManager
from notifications.controller import NotificationsRestController
from notifications.db_models import NotificationsModelService
from notifications.manager import NotificationsServiceManager
from organizations.controller import OrganizationsRestController
from organizations.db_models import OrganizationsModelService
from organizations.manager import OrganizationsServiceManager
from permissions.controller import PermissionsRestController
from permissions.db_models import PermissionsModelService
from permissions.manager import PermissionsServiceManager
from playbooks.controller import PlaybooksRestController
from playbooks.db_models import PlaybooksModelService
from playbooks.manager import PlaybooksServiceManager
from projections.controller import ProjectionsRestController
from projections.db_models import ProjectionsModelService
from projections.manager import ProjectionsServiceManager
from remote_files.manager import RemoteFilesServiceManager
from roles.controller import RolesRestController
from roles.db_models import RolesModelService
from roles.manager import RolesServiceManager
from schedules.controller import SchedulesRestController
from schedules.db_models import SchedulesModelService
from schedules.manager import SchedulesServiceManager
from tasks.controller import TasksRestController
from tasks.db_models import TasksModelService
from tasks.manager import TasksServiceManager
from tenants.controller import TenantsRestController
from tenants.db_models import TenantsModelService
from tenants.manager import TenantsServiceManager
from tools.controller import ToolsRestController
from tools.db_models import ToolsModelService
from tools.manager import ToolsServiceManager
from transcription.controller import TranscriptionRestController
from transcription.db_models import TranscriptionModelService
from transcription.manager import TranscriptionServiceManager
from user.controller import UserRestController
from user.db_models import UserModelService
from user.manager import UserServiceManager
from views.controller import ViewsRestController
from views.db_models import ViewsModelService
from views.manager import ViewsServiceManager
from workflow.controller import WorkflowRestController
from workflow.db_models import WorkflowModelService
from workflow.manager import WorkflowServiceManager

warnings.filterwarnings("ignore", category=UserWarning)


# `.env` is loaded by `common.configuration` at its own import time using the
# `ENV_FILE` env var (defaults to `./etc/.env`). Override via `ENV_FILE=...`.


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _load_environment() -> str:
    return os.environ.get("ENV_FILE", "./etc/.env")


def _initialize_base_tables(
    database_service_manager: DatabaseServiceManager,
    config: Configuration,
) -> None:
    logger.info(
        "Running bootstrap and migrations before app startup..",
        extra={"tags": "create_base_tables"},
    )
    try:
        run_bootstrap(database_service_manager, config)
    except Exception as exc:
        logger.critical(f"Startup aborted during bootstrap/migrations: {exc}")
        raise


def _prepare_controller(app_router: APIRouter | None, controller: Any) -> None:
    # In worker mode the service graph is built without an HTTP router, so
    # controller registration is skipped — the managers are still wired.
    if app_router is None:
        return
    controller.prepare(app_router)


def _setup_generic_modules(
    app_router: APIRouter | None,
    database_service_manager: DatabaseServiceManager,
    config: Configuration,
) -> list[Any]:
    """Wire generic controllers/managers and return managed services.

    When ``app_router`` is ``None`` (worker mode) the full service graph is
    still constructed and returned, but no HTTP controllers are registered.
    This is the single source of truth shared by the web app and the worker.
    """
    managed_services: list[Any] = []

    health_service_manager = HealthServiceManager()
    _prepare_controller(
        app_router,
        HealthRestController(
            health_service_manager,
            database_service_manager=database_service_manager,
        ),
    )

    permissions_db_model_service = PermissionsModelService(database_service_manager)
    permissions_service_manager = PermissionsServiceManager(
        permissions_db_model_service,
        database_service_manager,
        config,
    )
    _prepare_controller(
        app_router,
        PermissionsRestController(
            permissions_service_manager,
            database_service_manager=database_service_manager,
        ),
    )
    managed_services.append(permissions_service_manager)

    roles_db_model_service = RolesModelService(
        database_service_manager,
        permissions_model_service=permissions_db_model_service,
    )
    register_roles_db_service(roles_db_model_service)
    roles_service_manager = RolesServiceManager(
        roles_db_model_service,
        database_service_manager,
        config,
    )

    forms_db_model_service = FormsModelService(database_service_manager)
    entities_db_model_service = EntitiesModelService(
        database_service_manager, forms_db_model_service
    )

    audit_events_service = AuditEventsModelService(database_service_manager)
    audit_service_manager = AuditServiceManager(
        audit_events_service,
        roles_manager=roles_service_manager,
        entities_service=entities_db_model_service,
    )
    _prepare_controller(
        app_router,
        AuditRestController(audit_service_manager),
    )

    auth_db_model_service = AuthModelService(database_service_manager)
    auth_service_manager = AuthServiceManager(
        auth_db_model_service,
        database_service_manager,
        config,
        roles_db_model_service,
        audit_events_service=audit_events_service,
    )
    _prepare_controller(
        app_router,
        AuthRestController(
            auth_service_manager,
            database_service_manager=database_service_manager,
            auth_service_provider=auth_service_manager,
        ),
    )
    managed_services.append(auth_service_manager)

    user_db_model_service = UserModelService(database_service_manager)
    register_membership_db_service(user_db_model_service)
    user_service_manager = UserServiceManager(
        user_db_model_service,
        database_service_manager,
        config,
        roles_db_service=roles_db_model_service,
    )
    _prepare_controller(
        app_router,
        UserRestController(
            user_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    managed_services.append(user_service_manager)

    analytics_db_model_service = AnalyticsModelService(database_service_manager)
    analytics_service_manager = AnalyticsServiceManager(
        analytics_db_model_service,
        user_db_model_service,
        audit_events_service,
    )
    _prepare_controller(
        app_router,
        AnalyticsRestController(
            analytics_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    managed_services.append(analytics_service_manager)

    _prepare_controller(
        app_router,
        RolesRestController(
            roles_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    managed_services.append(roles_service_manager)

    invitation_db_model_service = InvitationModelService(database_service_manager)
    invitation_service_manager = InvitationServiceManager(
        invitation_db_model_service,
        database_service_manager,
        roles_service_manager,
        config,
    )
    _prepare_controller(
        app_router,
        InvitationRestController(
            invitation_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    managed_services.append(invitation_service_manager)
    auth_service_manager.invitation_service_manager = invitation_service_manager

    transcription_db_model_service = TranscriptionModelService(database_service_manager)
    transcription_service_manager = TranscriptionServiceManager(
        transcription_db_model_service,
        database_service_manager,
        config,
        auth_service_manager,
    )
    _prepare_controller(
        app_router,
        TranscriptionRestController(
            transcription_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    managed_services.append(transcription_service_manager)

    tenants_db_model_service = TenantsModelService(database_service_manager)
    tenants_service_manager = TenantsServiceManager(
        tenants_db_model_service,
        database_service_manager,
        config,
    )
    _prepare_controller(
        app_router,
        TenantsRestController(
            tenants_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    managed_services.append(tenants_service_manager)

    integrations_db_model_service = IntegrationsModelService(database_service_manager)
    integrations_service_manager = IntegrationsServiceManager(
        integrations_db_model_service,
        database_service_manager,
        config,
        auth_service_manager,
    )
    integrations_rest_controller = IntegrationsRestController(
        integrations_service_manager,
        database_service_manager=database_service_manager,
        auth_service_manager=auth_service_manager,
    )
    _prepare_controller(app_router, integrations_rest_controller)
    managed_services.append(integrations_service_manager)

    connectors_db_model_service = ConnectorsModelService(database_service_manager)
    connectors_service_manager = ConnectorsServiceManager(
        connectors_db_model_service,
        database_service_manager,
        config,
    )
    _prepare_controller(
        app_router,
        ConnectorsRestController(
            connectors_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    managed_services.append(connectors_service_manager)

    organizations_db_model_service = OrganizationsModelService(
        database_service_manager, user_model_service=user_db_model_service
    )
    roles_db_model_service.register_organizations_service(organizations_db_model_service)
    organizations_service_manager = OrganizationsServiceManager(
        organizations_db_model_service,
        database_service_manager,
        config,
        roles_service_manager=roles_service_manager,
    )
    _prepare_controller(
        app_router,
        OrganizationsRestController(
            organizations_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
            roles_service_manager=roles_service_manager,
        ),
    )
    managed_services.append(organizations_service_manager)

    llm_db_model_service = LlmModelService(database_service_manager, config=config)
    llm_service_manager = LlmServiceManager(
        llm_db_model_service,
        database_service_manager,
        config,
        auth_service_manager,
        integrations_service_manager=integrations_service_manager,
    )
    _prepare_controller(
        app_router,
        LlmRestController(
            llm_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    managed_services.append(llm_service_manager)

    # fileprocessor is now a pure parsing service exposed via the read_document tool;
    # it owns no queue, jobs, or REST surface.
    fileprocessor_service_manager = FileprocessorServiceManager(config)

    filehandler_db_model_service = FilehandlerModelService(database_service_manager)
    filehandler_service_manager = FilehandlerServiceManager(
        filehandler_db_model_service,
        database_service_manager,
        config,
        integrations_service_manager=integrations_service_manager,
    )
    organizations_service_manager.bind_filehandler(filehandler_service_manager)
    _prepare_controller(
        app_router,
        FilehandlerRestController(
            filehandler_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    managed_services.append(filehandler_service_manager)

    communications_db_model_service = CommunicationsModelService(database_service_manager)
    communications_service_manager = CommunicationsServiceManager(
        communications_db_model_service,
        database_service_manager,
        config,
        auth_service_manager,
    )
    _prepare_controller(
        app_router,
        CommunicationsRestController(
            communications_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    managed_services.append(communications_service_manager)

    field_library_db_model_service = FieldLibraryModelService(database_service_manager)
    field_library_service_manager = FieldLibraryServiceManager(
        field_library_db_model_service,
        database_service_manager,
        config,
        form_field_link_db_model_service=FormFieldLinkModelService(database_service_manager),
    )
    _prepare_controller(
        app_router,
        FieldLibraryRestController(field_library_service_manager),
    )
    managed_services.append(field_library_service_manager)

    method_library_db_model_service = MethodLibraryModelService(database_service_manager)
    method_library_service_manager = MethodLibraryServiceManager(
        method_library_db_model_service,
        database_service_manager,
        config,
    )
    _prepare_controller(
        app_router,
        MethodLibraryRestController(method_library_service_manager),
    )
    managed_services.append(method_library_service_manager)

    notifications_db_model_service = NotificationsModelService(database_service_manager)
    notifications_service_manager = NotificationsServiceManager(
        notifications_db_model_service,
        database_service_manager,
        config,
        auth_service_manager,
        user_service_manager=user_service_manager,
        organizations_service_manager=organizations_service_manager,
    )
    _prepare_controller(
        app_router,
        NotificationsRestController(
            notifications_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    managed_services.append(notifications_service_manager)
    auth_service_manager.notifications_manager = notifications_service_manager
    communications_service_manager.notifications_manager = notifications_service_manager
    filehandler_service_manager.notifications_service_manager = notifications_service_manager

    actions_db_model_service = ActionsModelService(database_service_manager)
    actions_service_manager = ActionsServiceManager(
        actions_db_model_service,
        database_service_manager,
        config,
        auth_service_manager,
    )
    _prepare_controller(
        app_router,
        ActionsRestController(
            actions_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    managed_services.append(actions_service_manager)

    mail_db_model_service = MailModelService(database_service_manager)
    mail_service_manager = MailServiceManager(
        email_config_model_service=mail_db_model_service,
        database_service_manager=database_service_manager,
        config=config,
        auth_service_manager=auth_service_manager,
    )
    _prepare_controller(
        app_router,
        MailRestController(
            mail_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    managed_services.append(mail_service_manager)
    notifications_service_manager._mail_service_manager = mail_service_manager
    integrations_rest_controller.mail_service_manager = mail_service_manager
    invitation_service_manager._mail_service_manager = mail_service_manager
    auth_service_manager._mail_service_manager = mail_service_manager

    executor_service_manager = ExecutorServiceManager(
        _database_service_manager=database_service_manager,
        _mail_service=mail_service_manager,
        _config=config,
        _notifications_service=notifications_service_manager,
        _filehandler_service=filehandler_service_manager,
    )
    _prepare_controller(
        app_router,
        ExecutorRestController(
            executor_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    managed_services.append(executor_service_manager)

    projections_db_model_service = ProjectionsModelService(database_service_manager)
    projections_service_manager = ProjectionsServiceManager(
        projections_db_model_service,
        database_service_manager,
        config,
        roles_manager=roles_service_manager,
    )
    _prepare_controller(
        app_router,
        ProjectionsRestController(
            projections_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    managed_services.append(projections_service_manager)

    dashboard_db_model_service = DashboardModelService(database_service_manager)
    dashboard_service_manager = DashboardServiceManager(
        dashboard_db_model_service,
        database_service_manager,
        config,
        roles_manager=roles_service_manager,
    )
    _prepare_controller(
        app_router,
        DashboardRestController(dashboard_service_manager),
    )
    managed_services.append(dashboard_service_manager)

    tasks_db_model_service = TasksModelService(database_service_manager)
    tasks_service_manager = TasksServiceManager(
        tasks_db_model_service,
        database_service_manager,
        config,
        communications_service_manager,
        auth_service_manager,
    )
    _prepare_controller(
        app_router,
        TasksRestController(
            tasks_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    managed_services.append(tasks_service_manager)

    comment_model_service = CommentModelService(database_service_manager)
    comments_service_manager = CommentsServiceManager(
        comment_model_service,
        database_service_manager,
        config,
        auth_service_manager,
        audit_events_service=audit_events_service,
    )
    comments_service_manager.notifications_manager = notifications_service_manager
    _prepare_controller(
        app_router,
        CommentsRestController(
            comments_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    managed_services.append(comments_service_manager)

    entities_service_manager = EntitiesServiceManager(
        entities_db_model_service,
        database_service_manager,
        config,
        auth_service_manager,
        roles_manager=roles_service_manager,
        # Entities reaches audit through its manager, not its persistence
        # adapter — workflow/auth below still hold the adapter directly.
        audit_service_manager=audit_service_manager,
        notifications_service_manager=notifications_service_manager,
        user_service_manager=user_service_manager,
    )
    blob_storage_service = BlobStorageService()
    _prepare_controller(
        app_router,
        EntitiesRestController(
            entities_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
            blob_storage_service=blob_storage_service,
        ),
    )
    managed_services.append(entities_service_manager)

    documents_db_model_service = DocumentsModelService(
        database_service_manager,
        filehandler_service_manager=filehandler_service_manager,
    )
    documents_service_manager = DocumentsServiceManager(
        documents_db_model_service,
        database_service_manager,
        config,
        entities_service_manager=entities_service_manager,
    )
    _prepare_controller(
        app_router,
        DocumentsRestController(
            documents_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    managed_services.append(documents_service_manager)

    filehandler_service_manager.entities_service_manager = entities_service_manager
    entities_service_manager.filehandler_service_manager = filehandler_service_manager

    dashboard_service_manager.entities_service_manager = entities_service_manager

    views_db_model_service = ViewsModelService(database_service_manager)
    views_service_manager = ViewsServiceManager(
        views_db_model_service,
        database_service_manager,
        config,
        auth_service_manager,
    )
    _prepare_controller(
        app_router,
        ViewsRestController(
            views_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    managed_services.append(views_service_manager)

    background_jobs_db_model_service = BackgroundJobsModelService(database_service_manager)
    background_jobs_service_manager = BackgroundJobsServiceManager(
        background_jobs_db_model_service,
        database_service_manager,
        config,
        executor_service_manager=executor_service_manager,
        mail_service_manager=mail_service_manager,
        forms_db_model_service=forms_db_model_service,
    )
    _prepare_controller(
        app_router,
        BackgroundJobsRestController(
            background_jobs_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    managed_services.append(background_jobs_service_manager)

    forms_db_model_service.background_jobs_manager = background_jobs_service_manager
    forms_db_model_service.mail_db = mail_service_manager

    forms_service_manager = FormsServiceManager(
        forms_db_model_service,
        database_service_manager,
        config,
        entities_service_manager,
        roles_manager=roles_service_manager,
    )
    _prepare_controller(
        app_router,
        FormsRestController(
            forms_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    managed_services.append(forms_service_manager)

    playbooks_db_model_service = PlaybooksModelService(database_service_manager)
    playbooks_service_manager = PlaybooksServiceManager(
        playbooks_db_model_service,
        database_service_manager,
        config,
    )
    _prepare_controller(
        app_router,
        PlaybooksRestController(
            playbooks_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    managed_services.append(playbooks_service_manager)

    tools_db_model_service = ToolsModelService(database_service_manager)
    tools_service_manager = ToolsServiceManager(
        tools_db_model_service,
        database_service_manager,
        config,
        llm_service_manager=llm_service_manager,
        entities_service_manager=entities_service_manager,
        forms_service_manager=forms_service_manager,
        documents_service_manager=filehandler_service_manager,
        communications_service_manager=communications_service_manager,
        integrations_service_manager=integrations_service_manager,
        connectors_service_manager=connectors_service_manager,
        auth_service_manager=auth_service_manager,
        fileprocessor_service_manager=fileprocessor_service_manager,
        dashboard_service_manager=dashboard_service_manager,
        comments_service_manager=comments_service_manager,
    )
    _prepare_controller(
        app_router,
        ToolsRestController(
            tools_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    managed_services.append(tools_service_manager)
    mcp_db_model_service = McpModelService(database_service_manager)
    mcp_service_manager = McpServiceManager(
        mcp_db_model_service,
        database_service_manager,
        config,
        tools_service_manager=tools_service_manager,
        auth_service_manager=auth_service_manager,
    )
    _prepare_controller(
        app_router,
        McpRestController(
            mcp_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    managed_services.append(mcp_service_manager)
    workflow_db_model_service = WorkflowModelService(database_service_manager)
    workflow_service_manager = WorkflowServiceManager(
        workflow_db_model_service=workflow_db_model_service,
        database_service_manager=database_service_manager,
        config=config,
        entities_service_manager=entities_service_manager,
        roles_manager=roles_service_manager,
        audit_events_service=audit_events_service,
        forms_service_manager=forms_service_manager,
        method_library_db_model_service=method_library_db_model_service,
        filehandler_service_manager=filehandler_service_manager,
        user_service_manager=user_service_manager,
        blob_storage_service=blob_storage_service,
        executor_service_manager=executor_service_manager,
    )
    background_jobs_service_manager.workflow_service_manager = workflow_service_manager
    workflow_db_model_service.action_runs_enqueue_fn = background_jobs_service_manager.enqueue_action_run
    forms_service_manager.workflow_service_manager = workflow_service_manager
    roles_service_manager.workflow_service_manager = workflow_service_manager
    tools_service_manager.workflow_service_manager = workflow_service_manager
    executor_service_manager.bind_entity_workflow_services(
        entities_service_manager, workflow_service_manager
    )
    executor_service_manager.bind_assign_user_services(
        entities_service_manager, user_service_manager
    )
    _prepare_controller(
        app_router,
        WorkflowRestController(
            workflow_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )

    schedules_db_model_service = SchedulesModelService(database_service_manager)
    schedules_service_manager = SchedulesServiceManager(
        schedules_db_model_service,
        entities_service_manager=entities_service_manager,
        workflow_service_manager=workflow_service_manager,
        background_jobs_service_manager=background_jobs_service_manager,
        audit_events_service=audit_events_service,
    )
    _prepare_controller(app_router, SchedulesRestController(schedules_service_manager))
    background_jobs_service_manager.schedules_service_manager = schedules_service_manager
    tools_service_manager.schedules_service_manager = schedules_service_manager
    executor_service_manager.bind_schedules_service(schedules_service_manager)
    managed_services.append(schedules_service_manager)

    agent_db_model_service = AgentModelService(database_service_manager)
    agent_service_manager = AgentServiceManager(
        agent_db_model_service,
        database_service_manager,
        config,
        tools_service_manager=tools_service_manager,
        mcp_registry_service=mcp_service_manager.registry_service,
        llm_service_manager=llm_service_manager,
        auth_service_manager=auth_service_manager,
        system_agent_templates=[
            AgentTemplateContract.model_validate(item)
            for item in get_configuration().agent_configuration.system_agent_templates
        ],
        # background_jobs is built before the agent manager, so its enqueue fn is
        # available now — inject it directly rather than late-binding afterward.
        async_run_enqueue_fn=background_jobs_service_manager.enqueue_agent_run,
        # filehandler is also built before the agent manager, so inject its file
        # reader here too (the runtime builds vision image input from it). Passing it
        # in the constructor makes image support a clear, required dependency.
        document_source_fn=filehandler_service_manager.read_document_source,
    )
    _prepare_controller(
        app_router,
        AgentRestController(
            agent_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    executor_service_manager.bind_agent_service(agent_service_manager)
    # Late-bind the agent runtime into filehandler so uploads of agent-processing
    # document types auto-run the configured agent (built after filehandler at line 399).
    filehandler_service_manager.agent_service_manager = agent_service_manager
    # The only genuine cycle: background_jobs is built before the agent manager,
    # so the agent manager (and its enqueue fn) must be bound back here. The
    # reverse direction (agent -> enqueue fn) is injected at construction above.
    background_jobs_service_manager.agent_service_manager = agent_service_manager
    remote_files_service_manager = RemoteFilesServiceManager(
        get_configuration().remote_files_configuration
    )
    relation_binding_service = BulkImportRelationBindingService(entities=entities_service_manager)
    spreadsheet_import_service = SpreadsheetImportService(
        filehandler=filehandler_service_manager,
        fileprocessor=fileprocessor_service_manager,
        entities=entities_service_manager,
        agents=agent_service_manager,
        relations=relation_binding_service,
    )
    bulk_import_service_manager = BulkImportServiceManager(
        jobs=background_jobs_db_model_service,
        database=database_service_manager,
        organizations=organizations_service_manager,
        roles=roles_service_manager,
        filehandler=filehandler_service_manager,
        spreadsheets=spreadsheet_import_service,
        entities=entities_service_manager,
        agents=agent_service_manager,
        workflows=workflow_service_manager,
        remote_files=remote_files_service_manager,
        relations=relation_binding_service,
    )
    _prepare_controller(
        app_router,
        BulkImportRestController(bulk_import_service_manager),
    )
    background_jobs_service_manager.workflow_service_manager = workflow_service_manager
    custom_forms_service_manager = CustomFormsServiceManager(
        workflow_db_model_service=workflow_db_model_service,
        method_library_db_model_service=method_library_db_model_service,
        connectors_service_manager=connectors_service_manager,
        entities_db_model_service=entities_db_model_service,
    )
    entities_service_manager.custom_forms_service_manager = custom_forms_service_manager
    _prepare_controller(
        app_router,
        CustomFormsRestController(
            custom_forms_service_manager,
            database_service_manager=database_service_manager,
            auth_service_manager=auth_service_manager,
        ),
    )
    # Lets a connector action with writeback_target: "custom_form" fill the
    # record's fetched form. Back-linked for the same reason grid forms is.
    background_jobs_service_manager.custom_forms_service_manager = (
        custom_forms_service_manager
    )
    managed_services.append(custom_forms_service_manager)

    managed_services.append(workflow_service_manager)
    managed_services.append(agent_service_manager)
    managed_services.append(remote_files_service_manager)
    managed_services.append(bulk_import_service_manager)

    return managed_services


def _build_lifespan(managed_services: list[Any]):
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        for manager in managed_services:
            if hasattr(manager, "start"):
                manager.start()
        yield
        for manager in managed_services:
            if hasattr(manager, "stop"):
                manager.stop()

    return lifespan


def _configure_middleware(app: FastAPI, request_timeout_seconds: int) -> None:
    app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_process_time_header(request: Request, call_next):
        start_time = time.perf_counter()
        response = await call_next(request)
        process_time = time.perf_counter() - start_time
        logger.info(f"{request.method} {request.url} completed in {process_time:.4f}s")
        response.headers["X-Process-Time"] = f"{process_time:.4f}s"
        return response

    @app.middleware("http")
    async def timeout_middleware(request: Request, call_next):
        try:
            return await asyncio.wait_for(call_next(request), timeout=request_timeout_seconds)
        except TimeoutError:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"message": "Request timed out"},
            )

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = uuid4().hex
        with tracer.start_as_current_span("request"):
            request.state.request_id = request_id
            span_attributes = {"X-Request-ID": request_id}
            logger.info(f"Starting api call for url: {request.url}", extra=span_attributes)
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response


def _create_app() -> tuple[FastAPI, Any]:
    env_path = _load_environment()
    logger.info(f"Loading environment from {env_path}")
    logger.info("Starting modular backend application ...")

    config = Configuration()
    config_env = get_configuration()
    database_service_manager = DatabaseServiceManager(config)
    _initialize_base_tables(database_service_manager, config)

    app_router = APIRouter()
    managed_services = _setup_generic_modules(app_router, database_service_manager, config)

    app = FastAPI(lifespan=_build_lifespan(managed_services))

    @app.get("/health")
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    _configure_middleware(app, config_env.server_configuration.request_timeout_seconds)
    app.include_router(app_router, prefix="/v1/api")
    # app.include_router(inbound_email_router)

    return app, config_env


# The background worker imports this module to reuse `_setup_generic_modules`
# (the shared service-graph builder). In that case we must NOT build the web
# ASGI app — the worker constructs its own graph without an HTTP router.
if _env_flag("WORKER_MODE", False):
    app, config_env = None, None
else:
    app, config_env = _create_app()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config_env.server_configuration.host,
        timeout_keep_alive=config_env.server_configuration.request_timeout_seconds,
        port=int(config_env.server_configuration.port),
        reload=True,
    )
