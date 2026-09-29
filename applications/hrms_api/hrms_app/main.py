"""HRMS API and browser gateway. The platform is an internal upstream service."""
from contextlib import asynccontextmanager
from dataclasses import replace
import os
from uuid import UUID

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from .errors import AppError
from .journal import Journal
from .platform import PlatformClient
from .policy import capabilities
from .settings_gateway import configuration_route, authorize_configuration
from .requests import EmployeeCreateRequest, LeaveCreateRequest
from .responses import EmployeeCreateResponse, EmployeeListItem, LeaveCreateResponse, LeaveListItem, OnboardingCaseItem
from .service import HrmsService
from .workflow_view import workflow_rows
from .performance import PerformanceService
from .performance_contracts import Action as PerformanceAction
from .cockpit import CockpitService, Command as CockpitCommand
from .projects import ProjectsService
from .project_contracts import Action as ProjectAction
from .project_access import ProjectAccessRequest


class Decision(BaseModel):
    trigger: str
    idempotency_key: str = Field(min_length=8, max_length=128)


def create_app(platform=None, journal=None):
    platform = platform or PlatformClient(
        os.environ['PLATFORM_API_URL'], os.environ['HRMS_ORGANIZATION_ID'],
        os.environ['HRMS_SERVICE_EMAIL'], os.environ['HRMS_SERVICE_PASSWORD'])
    journal = journal or Journal(os.environ['HRMS_APP_DATABASE_URL'])
    service = HrmsService(platform, journal, os.environ.get('HRMS_WORK_EMAIL_DOMAIN', 'newtuple.com'))
    performance = PerformanceService(service)
    projects = ProjectsService(service)
    cockpit = CockpitService(platform, journal)

    @asynccontextmanager
    async def lifespan(app):
        journal.initialize()
        yield
        platform.close()

    app = FastAPI(title='HRMS Application API', version='1.0.0', lifespan=lifespan)

    @app.exception_handler(AppError)
    async def app_error(request, exc):
        return JSONResponse(status_code=exc.status, content={'detail': exc.detail})

    def actor(request: Request):
        authorization = request.headers.get('authorization', '')
        if not authorization.lower().startswith('bearer '):
            raise AppError(401, 'Sign in to continue')
        current = platform.actor(authorization.split(' ', 1)[1])
        if hasattr(journal, 'project_policy'):
            current = replace(current, project_policy=journal.project_policy(current.organization_id)['roles'])
        if hasattr(journal, 'cockpit_policy'):
            current = replace(current, cockpit_policy=journal.cockpit_policy(current.organization_id)['roles'])
        return current

    @app.get('/health')
    def health():
        return {'status': 'ok', 'service': 'hrms-application'}

    @app.get('/v1/api/hrms/public/content')
    def public_content():
        return JSONResponse(cockpit.feed(), headers={'Cache-Control':'no-store'})

    @app.get('/v1/api/hrms/content')
    def employee_content(current=Depends(actor)):
        return cockpit.feed(employee=True)

    @app.get('/v1/api/hrms/cockpit')
    def cockpit_board(current=Depends(actor)):
        return cockpit.board(current)

    @app.post('/v1/api/hrms/cockpit/actions')
    def cockpit_create(payload: CockpitCommand, current=Depends(actor)):
        return cockpit.execute(current, 'new', payload)

    @app.post('/v1/api/hrms/cockpit/{entity_id}/actions')
    def cockpit_action(entity_id: UUID, payload: CockpitCommand, current=Depends(actor)):
        return cockpit.execute(current, str(entity_id), payload)

    @app.get('/v1/api/hrms/settings/cockpit-access')
    def cockpit_access(current=Depends(actor)):
        from .policy import COCKPIT_CAPABILITIES, role_capabilities, require
        require(current, 'platform:configure')
        policy=journal.cockpit_policy(current.organization_id)
        roles=platform.request('GET','/roles',token=current.token)
        return {'revision':policy['revision'],'capabilities':sorted(COCKPIT_CAPABILITIES),
                'roles':{r['name']:sorted(role_capabilities(r['name'],None,policy['roles']) & COCKPIT_CAPABILITIES) for r in roles if r['name']!='hrms_application_service'}}

    @app.put('/v1/api/hrms/settings/cockpit-access')
    def save_cockpit_access(payload: ProjectAccessRequest, current=Depends(actor)):
        from .policy import COCKPIT_CAPABILITIES, require
        from .cockpit import check
        require(current,'platform:configure')
        names={r['name'] for r in platform.request('GET','/roles',token=current.token) if r['name']!='hrms_application_service'}
        check(not set(payload.roles)-names,'Unknown or internal role')
        for grants in payload.roles.values():
            check(not set(grants)-COCKPIT_CAPABILITIES,'Only cockpit permissions can be changed here')
            check(not grants or 'cockpit:view' in grants,'Enable cockpit access before granting actions')
        return journal.save_cockpit_policy(current,payload.roles,payload.revision)

    @app.get('/v1/api/hrms/capabilities')
    def get_capabilities(current=Depends(actor)):
        return {'capabilities': sorted(capabilities(current)), 'roles': sorted(current.roles)}

    @app.get('/v1/api/hrms/forms/{entity_type}')
    def form_configuration_view(entity_type: str, current=Depends(actor)):
        from .form_config import form_configuration
        return form_configuration(platform, current, entity_type)

    @app.get('/v1/api/hrms/settings/project-access')
    def project_access(current=Depends(actor)):
        from .policy import PROJECT_CAPABILITIES, role_capabilities, require
        require(current, 'platform:configure')
        policy = journal.project_policy(current.organization_id)
        roles = platform.request('GET', '/roles', token=current.token)
        return {'revision': policy['revision'], 'capabilities': sorted(PROJECT_CAPABILITIES),
                'roles': {r['name']: sorted(role_capabilities(r['name'], policy['roles']) & PROJECT_CAPABILITIES)
                          for r in roles if r['name'] != 'hrms_application_service'}}

    @app.put('/v1/api/hrms/settings/project-access')
    def save_project_access(payload: ProjectAccessRequest, current=Depends(actor)):
        from .project_access import validate_project_access
        from .policy import require
        require(current, 'platform:configure')
        names = {r['name'] for r in platform.request('GET', '/roles', token=current.token) if r['name'] != 'hrms_application_service'}
        validate_project_access(payload.roles, names)
        return journal.save_project_policy(current, payload.roles, payload.revision)

    @app.get('/v1/api/hrms/settings/role-capabilities')
    def product_role_configuration(current=Depends(actor)):
        from .policy import ROLE_CAPABILITIES, require
        require(current, 'platform:configure')
        from .policy import role_capabilities
        return {role: sorted(role_capabilities(role, current.project_policy, current.cockpit_policy)) for role in ROLE_CAPABILITIES}

    @app.get('/v1/api/hrms/employees/form-options')
    def form_options(current=Depends(actor)):
        return service.form_options(current)

    @app.get('/v1/api/hrms/employees', response_model=list[EmployeeListItem])
    def directory(current=Depends(actor)):
        return service.directory(current)

    @app.post('/v1/api/hrms/employees', response_model=EmployeeCreateResponse, status_code=201)
    def create_employee(payload: EmployeeCreateRequest, current=Depends(actor)):
        return service.create_employee(current, payload)

    @app.get('/v1/api/hrms/onboarding', response_model=list[OnboardingCaseItem])
    def onboarding(current=Depends(actor)):
        return service.onboarding(current)

    @app.get('/v1/api/hrms/workflows')
    def workflows(current=Depends(actor)):
        from .workflow_config import configured_workflow_rows
        return configured_workflow_rows(platform, workflow_rows(service, current) + performance.workflows(current) + projects.workflows(current) + cockpit.workflows(current))

    @app.get('/v1/api/hrms/projects')
    def project_dashboard(current=Depends(actor)):
        return projects.dashboard(current)

    @app.get('/v1/api/hrms/projects/options')
    def project_options(current=Depends(actor)):
        return projects.options(current)

    @app.get('/v1/api/hrms/projects/pending-actions')
    def project_pending(current=Depends(actor)):
        return projects.pending(current)

    @app.post('/v1/api/hrms/projects/actions')
    def project_create(payload: ProjectAction, current=Depends(actor)):
        return projects.execute(current, 'new', payload)

    @app.post('/v1/api/hrms/projects/{entity_id}/actions')
    def project_action(entity_id: UUID, payload: ProjectAction, current=Depends(actor)):
        return projects.execute(current, str(entity_id), payload)

    @app.post('/v1/api/hrms/projects/{entity_id}/capacity')
    def project_capacity(entity_id: UUID, payload: ProjectAction, allocation_id: UUID | None = None, current=Depends(actor)):
        return projects.preview(current, str(entity_id), payload.data, str(allocation_id) if allocation_id else None)

    @app.get('/v1/api/hrms/performance')
    def performance_dashboard(current=Depends(actor)):
        return performance.dashboard(current)

    @app.get('/v1/api/hrms/performance/options')
    def performance_options(current=Depends(actor)):
        return performance.options(current)

    @app.get('/v1/api/hrms/performance/pending-actions')
    def performance_pending(current=Depends(actor)):
        return performance.pending(current)

    @app.get('/v1/api/hrms/performance/{entity_id}/reviewers')
    def performance_reviewers(entity_id: UUID, current=Depends(actor)):
        from .performance import check
        snap = performance.snapshot()
        row = performance.find(snap, str(entity_id))
        check('request_feedback' in performance.allowed(current, row, snap), 'Only the assigned manager can request feedback', 403)
        return [{'id': u['id'], 'name': u['name']} for u in performance.user_options()
                if u['id'] != row['data']['employee_user_id']]

    @app.post('/v1/api/hrms/performance/cycles')
    def performance_create(payload: PerformanceAction, current=Depends(actor)):
        from .performance import check
        check(payload.action == 'create_cycle', 'Expected create_cycle', 422)
        return performance.execute(current, 'new', payload)

    @app.post('/v1/api/hrms/performance/{entity_id}/actions')
    def performance_action(entity_id: UUID, payload: PerformanceAction, current=Depends(actor)):
        return performance.execute(current, str(entity_id), payload)

    @app.post('/v1/api/hrms/onboarding/{case_id}/steps/{sequence}/complete', response_model=OnboardingCaseItem)
    def complete_step(case_id: UUID, sequence: int, current=Depends(actor)):
        return service.complete_step(current, str(case_id), sequence)

    @app.post('/v1/api/hrms/onboarding/{case_id}/complete', response_model=OnboardingCaseItem)
    def complete_case(case_id: UUID, current=Depends(actor)):
        return service.complete_case(current, str(case_id))

    @app.get('/v1/api/hrms/leave-requests', response_model=list[LeaveListItem])
    def leave(view: str = 'mine', limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), current=Depends(actor)):
        return service.leave(current, view, limit, offset)

    @app.post('/v1/api/hrms/leave-requests', response_model=LeaveCreateResponse, status_code=201)
    def create_leave(payload: LeaveCreateRequest, current=Depends(actor)):
        return service.create_leave(current, payload)

    @app.get('/v1/api/hrms/leave-requests/{entity_id}/actions')
    def available(entity_id: UUID, current=Depends(actor)):
        return service.leave_actions(current, str(entity_id))

    @app.post('/v1/api/hrms/leave-requests/{entity_id}/actions')
    def decide(entity_id: UUID, payload: Decision, current=Depends(actor)):
        return service.decide_leave(current, str(entity_id), payload.trigger, payload.idempotency_key)

    # Explicit read/auth facade: no catch-all mutation proxy. Core task/record/transition,
    # bulk-import, agent and configuration mutations cannot bypass HRMS business rules.
    public_gets = {'auth/google/url', 'auth/microsoft/url', 'auth/status', 'invitations/validate'}
    auth_posts = {'auth/login', 'auth/refresh', 'auth/logout', 'auth/forgot-password',
                  'auth/reset-password', 'auth/google/callback', 'auth/microsoft/callback',
                  'auth/microsoft/id-token', 'invitations/accept'}
    private_gets = {'auth/me', 'users/me/organizations', 'organizations/current', 'roles/my-permissions',
                    'workflow-state-machines', 'permissions'}

    @app.api_route('/v1/api/{path:path}', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
    async def facade(path: str, request: Request):
        token = request.headers.get('authorization', '').removeprefix('Bearer ').removeprefix('bearer ')
        if request.method == 'GET' and path in public_gets:
            pass
        elif request.method == 'POST' and path in auth_posts:
            pass
        elif request.method == 'GET' and (path in private_gets or
                (path.startswith('workflow-state-machines/') and path.endswith('/active'))):
            from starlette.concurrency import run_in_threadpool
            await run_in_threadpool(platform.actor, token)
        elif configuration_route(request.method, path, platform.org):
            from starlette.concurrency import run_in_threadpool
            current = await run_in_threadpool(platform.actor, token)
            payload = None
            if request.method != 'GET' and 'application/json' in request.headers.get('content-type', ''):
                payload = await request.json()
            authorize_configuration(current, request.query_params, payload)
        else:
            raise AppError(403, 'Use the HRMS application action for this operation')
        # Preserve upstream authentication status/content without leaking service credentials.
        try:
            response = await _proxy(platform, request, path, token)
        except Exception as exc:
            if isinstance(exc, AppError):
                raise
            raise AppError(503, 'The platform is unavailable') from exc
        return response

    return app


async def _proxy(platform, request, path, token):
    from starlette.concurrency import run_in_threadpool
    content = await request.body()
    headers = {'content-type': request.headers.get('content-type', 'application/json')}
    if token:
        headers['authorization'] = f'Bearer {token}'
    response = await run_in_threadpool(platform.http.request, request.method, path,
                                     params=list(request.query_params.multi_items()), content=content, headers=headers)
    return Response(response.content, status_code=response.status_code,
                    media_type=response.headers.get('content-type', 'application/json'))


# Importable factory keeps tests independent of environment secrets.
app = create_app() if os.environ.get('PLATFORM_API_URL') else FastAPI()
