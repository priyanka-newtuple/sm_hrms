from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hrms.authz.engine import AuthzEngine
from hrms.authz.enums import Action, FeatureKey
from hrms.authz.scope_filters import apply_employee_scope
from hrms.config import get_settings
from hrms.core.audit import record_audit
from hrms.core.exceptions import Conflict, NotFound, PermissionDenied, ValidationFailed
from hrms.models.document import EmployeeDocument
from hrms.models.employee import Employee
from hrms.models.enums import DocumentStatus, DocumentType
from hrms.schemas.onboarding import EmployeeDocumentOut
from hrms.services import onboarding_flow_service

settings = get_settings()

FEATURE = FeatureKey.EMPLOYEE_ONBOARDING

_MAX_SIZE_BYTES = 15 * 1024 * 1024
_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
}


async def _can_manage(engine: AuthzEngine, actor: Employee) -> bool:
    return await engine.has_permission(actor, FEATURE, Action.MANAGE)


async def assert_employee_access(db, engine, actor, employee_id):
    if actor.id == employee_id:
        return
    if not await _can_manage(engine, actor):
        raise PermissionDenied("You can only access your own documents.")
    scope = await engine.get_scope(actor, FEATURE)
    visible = await db.execute(apply_employee_scope(select(Employee.id).where(Employee.id == employee_id), scope, actor))
    if visible.scalar_one_or_none() is None:
        raise NotFound("Employee not found")


async def list_documents(
    db: AsyncSession,
    engine: AuthzEngine,
    actor: Employee,
    employee_id: uuid.UUID,
) -> list[dict]:
    await assert_employee_access(db, engine, actor, employee_id)
    employee = await db.get(Employee, employee_id)
    if employee is None:
        raise NotFound("Employee not found")
    result = await db.execute(
        select(EmployeeDocument)
        .options(selectinload(EmployeeDocument.verified_by))
        .where(EmployeeDocument.employee_id == employee_id)
        .order_by(EmployeeDocument.created_at)
    )
    out = []
    for doc in result.scalars().all():
        item = EmployeeDocumentOut.model_validate(doc)
        if doc.verified_by is not None:
            item.verified_by_name = doc.verified_by.full_name
        out.append(item.model_dump(mode="json"))
    return out


async def upload_document(
    db: AsyncSession,
    engine: AuthzEngine,
    actor: Employee,
    employee_id: uuid.UUID,
    doc_type: DocumentType,
    file: UploadFile,
) -> EmployeeDocument:
    await assert_employee_access(db, engine, actor, employee_id)

    employee = await db.get(Employee, employee_id)
    if employee is None:
        raise NotFound("Employee not found")

    content_type = file.content_type or "application/octet-stream"
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise ValidationFailed("Only PDF, JPEG, PNG or WebP files are accepted.")
    data = await file.read()
    if len(data) > _MAX_SIZE_BYTES:
        raise ValidationFailed("File exceeds the 15 MB limit.")
    if not data:
        raise ValidationFailed("Uploaded file is empty.")

    safe_name = Path(file.filename or "document").name
    directory = Path(settings.DOCUMENT_STORAGE_DIR) / str(employee_id)
    directory.mkdir(parents=True, exist_ok=True)
    storage_path = directory / f"{uuid.uuid4().hex}_{safe_name}"
    storage_path.write_bytes(data)

    # Serialize upload/review with workflow handoffs and competing uploads.
    await onboarding_flow_service._open_onboarding_record(db, employee_id)

    document = EmployeeDocument(
        employee_id=employee_id,
        doc_type=doc_type,
        file_name=safe_name,
        storage_path=str(storage_path),
        content_type=content_type,
        size_bytes=len(data),
        status=DocumentStatus.SUBMITTED,
        uploaded_by_id=actor.id,
    )
    db.add(document)
    await db.flush()

    await onboarding_flow_service.on_document_uploaded(db, employee)
    await record_audit(
        db,
        actor_id=actor.user_id,
        action="upload",
        entity_type="employee_document",
        entity_id=str(document.id),
        diff={"doc_type": doc_type.value, "file_name": safe_name},
    )
    await db.commit()
    await db.refresh(document)
    return document


async def review_document(
    db: AsyncSession,
    engine: AuthzEngine,
    actor: Employee,
    document_id: uuid.UUID,
    status: DocumentStatus,
    note: str | None,
) -> EmployeeDocument:
    if status not in (DocumentStatus.VERIFIED, DocumentStatus.REJECTED):
        raise ValidationFailed("Review status must be 'verified' or 'rejected'.")
    if not await _can_manage(engine, actor):
        raise PermissionDenied("Only roles that manage onboarding can verify documents.")

    existing = await db.get(EmployeeDocument, document_id)
    if existing is None:
        raise NotFound("Document not found")
    await assert_employee_access(db, engine, actor, existing.employee_id)
    await onboarding_flow_service._open_onboarding_record(db, existing.employee_id)
    document = (
        await db.execute(
            select(EmployeeDocument)
            .where(EmployeeDocument.id == document_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if document is None:
        raise NotFound("Document not found")
    if actor.id in (document.employee_id, document.uploaded_by_id):
        raise PermissionDenied("You cannot review your own document or upload.")
    if document.status != DocumentStatus.SUBMITTED:
        raise Conflict("This document has already been reviewed. Refresh My Work.")
    if status == DocumentStatus.REJECTED and not (note and note.strip()):
        raise ValidationFailed("A reason is required when requesting changes or rejecting a document.")
    from hrms.services.work_service import latest_document_predicate

    latest = await db.execute(select(EmployeeDocument.id).where(EmployeeDocument.id == document_id, latest_document_predicate()))
    if latest.scalar_one_or_none() is None:
        raise Conflict("A newer upload has replaced this document. Review the latest version.")
    employee = await db.get(Employee, document.employee_id)

    document.status = status
    document.note = note
    document.verified_by_id = actor.id
    document.verified_at = datetime.now(UTC)

    await onboarding_flow_service.on_document_reviewed(db, employee, document, actor)
    await record_audit(
        db,
        actor_id=actor.user_id,
        action="review",
        entity_type="employee_document",
        entity_id=str(document.id),
        diff={"status": status.value, "note": note},
    )
    await db.commit()
    await db.refresh(document)
    return document


async def get_document_for_download(
    db: AsyncSession,
    engine: AuthzEngine,
    actor: Employee,
    document_id: uuid.UUID,
) -> EmployeeDocument:
    document = await db.get(EmployeeDocument, document_id)
    if document is None:
        raise NotFound("Document not found")
    await assert_employee_access(db, engine, actor, document.employee_id)
    if not Path(document.storage_path).is_file():
        raise NotFound("Stored file is missing on the server.")
    return document
