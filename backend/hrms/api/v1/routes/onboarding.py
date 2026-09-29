from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from hrms.authz.deps import get_authz_engine, get_current_employee
from hrms.authz.engine import AuthzEngine
from hrms.authz.enums import Action
from hrms.core.exceptions import PermissionDenied
from hrms.core.pagination import Page
from hrms.database import get_db
from hrms.models.employee import Employee
from hrms.models.enums import DocumentType, OnboardingType
from hrms.schemas.onboarding import (
    AcceptInvitationIn,
    DocumentReviewIn,
    EmployeeDocumentOut,
    MyActionOut,
    OnboardingDetailOut,
    OnboardingRecordOut,
    OnboardingStart,
    OnboardingTaskOut,
    TaskCompleteIn,
    TaskSkipIn,
    WizardProfileIn,
)
from hrms.services import document_service, onboarding_service
from hrms.services.onboarding_service import FEATURE_BY_TYPE

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


async def _require(engine: AuthzEngine, employee: Employee, workflow_type: OnboardingType, action: Action):
    feature = FEATURE_BY_TYPE[workflow_type]
    if not await engine.has_permission(employee, feature, action):
        raise PermissionDenied(f"Role '{employee.role.name}' cannot '{action.value}' on '{feature.value}'")


@router.get("", response_model=Page)
async def list_onboarding(
    workflow_type: OnboardingType = Query(OnboardingType.ONBOARDING),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(get_current_employee),
):
    await _require(engine, current_employee, workflow_type, Action.MANAGE)
    items, total = await onboarding_service.list_onboarding(
        db,
        engine,
        current_employee,
        workflow_type,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return Page(items=items, total=total, page=page, page_size=page_size)


# ------------------------------------------------------- current-user routes
# (declared before /{record_id} so the static segments match first)


@router.get("/my-actions", response_model=list[MyActionOut])
async def my_actions(
    db: AsyncSession = Depends(get_db),
    current_employee: Employee = Depends(get_current_employee),
):
    """READY steps assigned to the current user, across all hires — the page
    every notification email deep-links to."""
    return await onboarding_service.my_actions(db, current_employee)


@router.get("/me", response_model=OnboardingDetailOut | None)
async def my_onboarding(
    db: AsyncSession = Depends(get_db),
    current_employee: Employee = Depends(get_current_employee),
):
    """The current user's own onboarding — powers the /welcome wizard."""
    return await onboarding_service.my_onboarding(db, current_employee)


@router.post("/me/profile", response_model=OnboardingDetailOut | None)
async def submit_wizard_profile(
    payload: WizardProfileIn,
    db: AsyncSession = Depends(get_db),
    current_employee: Employee = Depends(get_current_employee),
):
    return await onboarding_service.submit_wizard_profile(db, current_employee, payload)


@router.post("/invitations/accept")
async def accept_invitation(
    payload: AcceptInvitationIn,
    db: AsyncSession = Depends(get_db),
    current_employee: Employee = Depends(get_current_employee),
):
    accepted = await onboarding_service.accept_invitation(db, current_employee, payload.token)
    return {"accepted": accepted}


# ------------------------------------------------------------------ documents


@router.get("/employees/{employee_id}/documents", response_model=list[EmployeeDocumentOut])
async def list_documents(
    employee_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(get_current_employee),
):
    return await document_service.list_documents(db, engine, current_employee, employee_id)


@router.post("/employees/{employee_id}/documents", response_model=EmployeeDocumentOut)
async def upload_document(
    employee_id: uuid.UUID,
    doc_type: DocumentType = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(get_current_employee),
):
    return await document_service.upload_document(db, engine, current_employee, employee_id, doc_type, file)


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(get_current_employee),
):
    document = await document_service.get_document_for_download(db, engine, current_employee, document_id)
    return FileResponse(
        document.storage_path,
        media_type=document.content_type or "application/octet-stream",
        filename=document.file_name,
    )


@router.post("/documents/{document_id}/review", response_model=EmployeeDocumentOut)
async def review_document(
    document_id: uuid.UUID,
    payload: DocumentReviewIn,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(get_current_employee),
):
    return await document_service.review_document(db, engine, current_employee, document_id, payload.status, payload.note)


# ------------------------------------------------------------ record routes


@router.post("/start", response_model=OnboardingRecordOut)
async def start_onboarding(
    payload: OnboardingStart,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(get_current_employee),
):
    await _require(engine, current_employee, payload.workflow_type, Action.MANAGE)
    return await onboarding_service.start_onboarding(db, current_employee, payload)


@router.get("/{record_id}", response_model=OnboardingDetailOut)
async def get_onboarding_detail(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(get_current_employee),
):
    return await onboarding_service.get_detail(db, engine, current_employee, record_id)


@router.post("/{record_id}/tasks/{task_id}/complete", response_model=OnboardingTaskOut)
async def complete_task(
    record_id: uuid.UUID,
    task_id: uuid.UUID,
    payload: TaskCompleteIn | None = None,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(get_current_employee),
):
    return await onboarding_service.complete_task(db, engine, current_employee, record_id, task_id, payload)


@router.post("/{record_id}/tasks/{task_id}/skip", response_model=OnboardingRecordOut)
async def skip_task(
    record_id: uuid.UUID,
    task_id: uuid.UUID,
    payload: TaskSkipIn | None = None,
    db: AsyncSession = Depends(get_db),
    engine: AuthzEngine = Depends(get_authz_engine),
    current_employee: Employee = Depends(get_current_employee),
):
    return await onboarding_service.skip_task(db, engine, current_employee, record_id, task_id, payload)
