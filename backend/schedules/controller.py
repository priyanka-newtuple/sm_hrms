"""REST controller for recurring entity schedules."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from common.auth import require_permission
from exceptions import AuthorizationError, ConflictError, NotFoundError, ValidationError
from schedules.manager import SchedulesServiceManager
from schedules.models.interface import ScheduleRecord, ScheduleTargetRecord
from schedules.models.request import (
    ScheduleCreateRequest,
    ScheduleRunNowRequest,
    ScheduleTargetCreateRequest,
    ScheduleUpdateRequest,
)
from schedules.models.response import (
    ScheduleListResponse,
    SchedulePreviewResponse,
    ScheduleRunNowResponse,
    ScheduleRunPreviewResponse,
    ScheduleTargetListResponse,
    SchedulesStatusResponse,
)

ScheduleReadActor = Annotated[dict[str, object], Depends(require_permission("workflow", "read"))]
ScheduleWriteActor = Annotated[dict[str, object], Depends(require_permission("workflow", "write"))]


class SchedulesRestController:
    def __init__(self, manager: SchedulesServiceManager) -> None:
        self.manager = manager

    @staticmethod
    def _raise(exc: Exception) -> None:
        if isinstance(exc, NotFoundError):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if isinstance(exc, AuthorizationError):
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        if isinstance(exc, ConflictError):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if isinstance(exc, (ValidationError, ValueError)):
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise HTTPException(status_code=500, detail="Internal server error") from exc

    def prepare(self, app: APIRouter, security: Depends | None = None) -> None:
        dependencies = [security] if security else None

        @app.get("/schedules/status", response_model=SchedulesStatusResponse, dependencies=dependencies)
        def module_status(request: Request):
            return self.manager.get_status()

        @app.post("/schedules", response_model=ScheduleRecord, status_code=status.HTTP_201_CREATED, dependencies=dependencies)
        def create_schedule(request: Request, payload: ScheduleCreateRequest, actor: ScheduleWriteActor):
            try:
                return self.manager.create_schedule_for_actor(actor, payload)
            except Exception as exc:
                self._raise(exc)

        @app.get("/schedules", response_model=ScheduleListResponse, dependencies=dependencies)
        def list_schedules(request: Request, actor: ScheduleReadActor, machine_name: str | None = Query(default=None)):
            try:
                return self.manager.list_schedules_for_actor(actor, machine_name)
            except Exception as exc:
                self._raise(exc)

        @app.get("/schedules/{schedule_id}", response_model=ScheduleRecord, dependencies=dependencies)
        def get_schedule(request: Request, schedule_id: str, actor: ScheduleReadActor):
            try:
                return self.manager.get_schedule_for_actor(actor, schedule_id)
            except Exception as exc:
                self._raise(exc)

        @app.put("/schedules/{schedule_id}", response_model=ScheduleRecord, dependencies=dependencies)
        def update_schedule(request: Request, schedule_id: str, payload: ScheduleUpdateRequest, actor: ScheduleWriteActor):
            try:
                return self.manager.update_schedule_for_actor(actor, schedule_id, payload)
            except Exception as exc:
                self._raise(exc)

        @app.delete(
            "/schedules/{schedule_id}",
            status_code=status.HTTP_204_NO_CONTENT,
            dependencies=dependencies,
        )
        def delete_schedule(request: Request, schedule_id: str, actor: ScheduleWriteActor):
            try:
                self.manager.delete_schedule_for_actor(actor, schedule_id)
                return None
            except Exception as exc:
                self._raise(exc)

        @app.post("/schedules/{schedule_id}/targets", response_model=ScheduleTargetRecord, status_code=status.HTTP_201_CREATED, dependencies=dependencies)
        def add_target(request: Request, schedule_id: str, payload: ScheduleTargetCreateRequest, actor: ScheduleWriteActor):
            try:
                return self.manager.add_target_for_actor(actor, schedule_id, payload)
            except Exception as exc:
                self._raise(exc)

        @app.get("/schedules/{schedule_id}/targets", response_model=ScheduleTargetListResponse, dependencies=dependencies)
        def list_targets(request: Request, schedule_id: str, actor: ScheduleReadActor):
            try:
                return self.manager.list_targets_for_actor(actor, schedule_id)
            except Exception as exc:
                self._raise(exc)

        @app.get("/schedules/{schedule_id}/preview", response_model=SchedulePreviewResponse, dependencies=dependencies)
        def preview(request: Request, schedule_id: str, actor: ScheduleReadActor, count: int = Query(default=6, ge=1, le=24)):
            try:
                return self.manager.preview_for_actor(actor, schedule_id, count)
            except Exception as exc:
                self._raise(exc)

        @app.get(
            "/schedules/{schedule_id}/run-preview",
            response_model=ScheduleRunPreviewResponse,
            dependencies=dependencies,
        )
        def run_preview(request: Request, schedule_id: str, actor: ScheduleReadActor):
            try:
                return self.manager.preview_run_now_for_actor(actor, schedule_id)
            except Exception as exc:
                self._raise(exc)

        @app.post(
            "/schedules/{schedule_id}/run-now",
            response_model=ScheduleRunNowResponse,
            dependencies=dependencies,
        )
        def run_now(
            request: Request,
            schedule_id: str,
            payload: ScheduleRunNowRequest,
            actor: ScheduleWriteActor,
        ):
            try:
                return self.manager.run_now_for_actor(actor, schedule_id, payload)
            except Exception as exc:
                self._raise(exc)
