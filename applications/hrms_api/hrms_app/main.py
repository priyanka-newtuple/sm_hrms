"""HRMS API and browser gateway. The platform is an internal upstream service."""
from contextlib import asynccontextmanager
from json import JSONDecodeError
import logging
import asyncio
import os
from uuid import UUID

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from .errors import AppError
from .google_auth import google_auth
from .journal import Journal
from .platform import PlatformClient
from .policy import capabilities, require
from .settings_gateway import configuration_route, authorize_configuration
from .field_access import changes_forms, sync_service_access
from .extra_steps import ExtraSteps
from . import custom_fields
from .requests import (EmployeeCreateRequest, EmployeeExitRequest, EmployeeOperationRequest, EmployeeUpdateRequest,
                       LeaveCreateRequest)
from .responses import EmployeeListItem, LeaveCreateResponse, LeaveListItem
from .service import HrmsService
from .employee_access import setup_access
from .workflow_view import workflow_rows, employee_workflow_rows
from .performance import PerformanceService
from .performance_contracts import Action as PerformanceAction
from .cockpit import CockpitService, Command as CockpitCommand
from .projects import ProjectsService
from .project_contracts import Action as ProjectAction
from .wfh import WfhService, PolicyInput, RequestInput, DecisionInput
from .assets import AssetService, AssetCommand, AssetBatchCommand


class EmployeeAccessRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=128)


class OfferCommand(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=128)
    machine_name: str = ''
    expected_hash: str = ''
    values: dict = Field(default_factory=dict)
    trigger: str = ''


class EmployeeWorkflowAction(BaseModel):
    workflow_id: UUID
    trigger: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=8, max_length=128)


class EmployeeFormSave(BaseModel):
    workflow_id: UUID
    values: dict = Field(default_factory=dict)


class Decision(BaseModel):
    trigger: str
    idempotency_key: str = Field(min_length=8, max_length=128)


class StepRequest(BaseModel):
    trigger: str = Field(min_length=1, max_length=100)
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
    wfh = WfhService(service)
    assets = AssetService(service)
    from .offer_documents import OfferDocuments, digest
    offers = OfferDocuments(platform, journal)
    from .offboarding import OffboardingService
    offboarding = OffboardingService(service)
    from .offboarding_participation import EmployeeOffboarding
    employee_offboarding = EmployeeOffboarding(offboarding)


    @asynccontextmanager
    async def lifespan(app):
        journal.initialize()
        stopping = asyncio.Event()
        async def sync_accounts():
            from .employee_lifecycle import reconcile
            while not stopping.is_set():
                try:
                    await asyncio.to_thread(reconcile, service)
                except Exception:
                    logging.getLogger(__name__).exception('Employee account synchronization failed')
                try:
                    await asyncio.wait_for(stopping.wait(), timeout=30)
                except TimeoutError:
                    pass
        worker = asyncio.create_task(sync_accounts())
        try:
            yield
        finally:
            stopping.set()
            await worker
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
        if 'hrms_onboarding_employee' in current.roles:
            path = request.url.path
            allowed = path in {'/v1/api/hrms/employee-work', '/v1/api/hrms/capabilities', '/v1/api/hrms/organization'} or path.startswith('/v1/api/hrms/employee-work/')
            if not allowed:
                raise AppError(403, 'Complete your onboarding before accessing other modules')
        return current

    @app.get('/v1/api/hrms/my-offboarding')
    def my_offboarding(current=Depends(actor)):
        return employee_offboarding.rows(current)

    @app.get('/v1/api/hrms/my-offboarding/{entity_id}')
    def my_offboarding_detail(entity_id: UUID, current=Depends(actor)):
        return employee_offboarding.detail(current,str(entity_id))

    @app.post('/v1/api/hrms/my-offboarding/{entity_id}')
    def my_offboarding_command(entity_id: UUID, payload: OfferCommand, current=Depends(actor)):
        return employee_offboarding.command(current,str(entity_id),payload.model_dump())

    @app.get('/v1/api/hrms/offboarding/assignees')
    def offboarding_assignees(current=Depends(actor)):
        return offboarding.assignees(current)

    @app.get('/v1/api/hrms/offboarding/config')
    def offboarding_config(current=Depends(actor)):
        return offboarding.config(current)

    @app.get('/v1/api/hrms/offboarding/inbox')
    def offboarding_inbox(current=Depends(actor)):
        return offboarding.inbox(current)

    @app.get('/v1/api/hrms/offboarding')
    def offboarding_list(current=Depends(actor)):
        return offboarding.rows(current)

    @app.post('/v1/api/hrms/offboarding')
    def offboarding_create(payload: OfferCommand, current=Depends(actor)):
        return offboarding.save(current, payload.model_dump())

    @app.get('/v1/api/hrms/offboarding/{entity_id}')
    def offboarding_detail(entity_id: UUID, current=Depends(actor)):
        return offboarding.detail(current, str(entity_id))

    @app.get('/v1/api/hrms/offboarding/{entity_id}/related')
    def offboarding_related(entity_id: UUID, current=Depends(actor)):
        return offboarding.related(current, str(entity_id))

    @app.put('/v1/api/hrms/offboarding/{entity_id}')
    def offboarding_save(entity_id: UUID, payload: OfferCommand, current=Depends(actor)):
        return offboarding.save(current, payload.model_dump(), str(entity_id))

    @app.post('/v1/api/hrms/offboarding/{entity_id}/actions')
    def offboarding_action(entity_id: UUID, payload: OfferCommand, current=Depends(actor)):
        result = offboarding.act(current, str(entity_id), payload.model_dump())
        if payload.trigger == 'confirm_departure':
            item = offboarding.detail(current, str(entity_id))
            follow_directory(current, item['values']['employee_id'], left=True)
        return result

    @app.get('/v1/api/hrms/offers/config')
    def offer_config(machine_name: str, current=Depends(actor)):
        return offers.config(current, machine_name)

    @app.post('/v1/api/hrms/offers')
    def create_offer(payload: OfferCommand, current=Depends(actor)):
        return offers.save(current, payload.model_dump())

    @app.get('/v1/api/hrms/offers/{entity_id}')
    def offer_detail(entity_id: UUID, current=Depends(actor)):
        item = offers.detail(current, str(entity_id))
        return {**item, 'values_hash': digest(item['values'])}

    @app.put('/v1/api/hrms/offers/{entity_id}')
    def save_offer(entity_id: UUID, payload: OfferCommand, current=Depends(actor)):
        return offers.save(current, payload.model_dump(), str(entity_id))

    @app.post('/v1/api/hrms/offers/{entity_id}/preview')
    def preview_offer(entity_id: UUID, payload: OfferCommand, current=Depends(actor)):
        return offers.generate(current, str(entity_id), payload.model_dump())

    @app.get('/v1/api/hrms/offers/{entity_id}/pdf')
    def offer_pdf(entity_id: UUID, current=Depends(actor)):
        return Response(offers.download(current, str(entity_id)), media_type='application/pdf',
                        headers={'Cache-Control': 'no-store', 'Content-Disposition': 'inline; filename="Offer.pdf"'})

    @app.post('/v1/api/hrms/offers/{entity_id}/actions')
    def offer_action(entity_id: UUID, payload: OfferCommand, current=Depends(actor)):
        return offers.transition(current, str(entity_id), payload.model_dump())

    @app.get('/v1/api/hrms/employee-work/{entity_id}/assets')
    def employee_assets(entity_id: UUID, workflow_id: UUID, current=Depends(actor)):
        from .onboarding_assets import board
        return board(assets, current, str(entity_id), str(workflow_id))

    @app.post('/v1/api/hrms/employee-work/{entity_id}/assets/assign')
    def employee_assign_assets(entity_id: UUID, workflow_id: UUID, payload: AssetBatchCommand, current=Depends(actor)):
        from .onboarding_assets import context, evidence, ASSET_FIELD
        require(current, 'asset:manage')
        _, actionable = context(assets.platform, current, str(entity_id), str(workflow_id))
        if not actionable:
            raise AppError(403, 'Asset issuance is not available at your current workflow step')
        if payload.data.get('issued_employee_id') != str(entity_id):
            raise AppError(422, 'Choose the employee on this onboarding record')
        result = assets.assign_many(current, payload)
        if result.get('started') is False:
            return result
        assets.platform.request('PUT', f'/entity-records/{entity_id}', token=current.token,
            json={'data': {ASSET_FIELD: evidence(assets.platform, str(entity_id))}})
        return result

    @app.post('/v1/api/hrms/employee-work/{entity_id}/assets/{asset_id}')
    def employee_issue_asset(entity_id: UUID, asset_id: UUID, workflow_id: UUID, payload: AssetCommand, current=Depends(actor)):
        from .onboarding_assets import issue
        return issue(assets, current, str(entity_id), str(workflow_id), str(asset_id), payload)

    @app.get('/v1/api/hrms/onboarding-tracker')
    def employee_onboarding_tracker(current=Depends(actor)):
        from .employee_work import onboarding_tracker
        return onboarding_tracker(platform, current)

    @app.get('/v1/api/hrms/employee-work')
    def employee_inbox(current=Depends(actor)):
        from .employee_work import employee_work
        return employee_work(platform, current)

    @app.post('/v1/api/hrms/employee-work/{entity_id}/actions')
    def employee_action(entity_id: UUID, payload: EmployeeWorkflowAction, current=Depends(actor)):
        from .employee_work import transition_employee
        return transition_employee(platform, current, str(entity_id), str(payload.workflow_id),
                                   payload.trigger, payload.idempotency_key)

    @app.get('/v1/api/hrms/employee-work/{entity_id}/form')
    def employee_work_form(entity_id: UUID, workflow_id: UUID, current=Depends(actor)):
        from .employee_work import employee_form
        return employee_form(platform, current, str(entity_id), str(workflow_id))

    @app.put('/v1/api/hrms/employee-work/{entity_id}/form')
    def employee_work_save(entity_id: UUID, payload: EmployeeFormSave, current=Depends(actor)):
        from .employee_work import save_employee_form
        return save_employee_form(platform, current, str(entity_id), str(payload.workflow_id), payload.values)

    @app.get('/health')
    def health():
        return {'status': 'ok', 'service': 'hrms-application'}

    @app.get('/v1/api/hrms/configuration-release')
    def configuration_release(current=Depends(actor)):
        require(current, 'platform:configure')
        from .configuration_promotion import release_status
        return {'application_revision': os.environ.get('HRMS_RELEASE_SHA', 'development'),
                'releases': release_status(journal.dsn, current.organization_id),
                'live_drift_checked': False}

    from .uat_mail import routes as uat_mail_routes
    uat_mail_routes(app, actor, getattr(platform, 'org', None))

    @app.get('/v1/api/hrms/assets')
    def asset_inventory(current=Depends(actor)):
        return assets.board(current)

    @app.post('/v1/api/hrms/assets')
    def asset_create(payload: AssetCommand, current=Depends(actor)):
        if payload.action != 'create':
            raise AppError(422, 'Use an asset ID to edit or issue')
        return assets.execute(current, None, payload)

    @app.get('/v1/api/hrms/assets/pending-assignments')
    def pending_asset_assignments(current=Depends(actor)):
        return assets.pending_batches(current)

    @app.post('/v1/api/hrms/assets/assign')
    def asset_assign(payload: AssetBatchCommand, current=Depends(actor)):
        return assets.assign_many(current, payload)

    @app.post('/v1/api/hrms/assets/{entity_id}/actions')
    def asset_action(entity_id: UUID, payload: AssetCommand, current=Depends(actor)):
        return assets.execute(current, str(entity_id), payload)

    @app.get('/v1/api/hrms/wfh')
    def wfh_board(year: int = Query(ge=2000, le=2100), current=Depends(actor)):
        return wfh.board(current, year)

    @app.post('/v1/api/hrms/wfh/policy')
    def wfh_policy(payload: PolicyInput, current=Depends(actor)):
        return wfh.save_policy(current, payload)

    @app.get('/v1/api/hrms/wfh/inbox')
    def wfh_inbox(current=Depends(actor)):
        return wfh.inbox(current)

    @app.post('/v1/api/hrms/wfh/requests')
    def wfh_request(payload: RequestInput, current=Depends(actor)):
        return wfh.create(current, payload)

    @app.post('/v1/api/hrms/wfh/requests/{entity_id}/actions')
    def wfh_decision(entity_id: UUID, payload: DecisionInput, current=Depends(actor)):
        return wfh.decide(current, str(entity_id), payload)

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

    @app.get('/v1/api/hrms/capabilities')
    def get_capabilities(current=Depends(actor)):
        return {'capabilities': sorted(capabilities(current)), 'roles': sorted(current.roles),
                'employee_profile': 'hrms_onboarding_employee' not in current.roles and service.has_employee_profile(current)}

    @app.get('/v1/api/hrms/organization')
    def current_organization(current=Depends(actor)):
        organization = platform.request('GET', '/organizations/current', token=current.token)
        if organization['id'] != current.organization_id:
            raise AppError(403, 'Organization does not match the HRMS session')
        return {key: organization.get(key) for key in ('id', 'name', 'slug', 'domain', 'status')}

    @app.get('/v1/api/hrms/forms/{entity_type}')
    def form_configuration_view(entity_type: str, purpose: str = 'record', current=Depends(actor)):
        from .form_config import form_configuration
        return form_configuration(platform, current, entity_type, purpose)

    @app.get('/v1/api/hrms/user-approvals')
    def pending_user_approvals(current=Depends(actor)):
        if 'employee:activate' not in capabilities(current):
            raise AppError(403, 'Account approval permission is required')
        # Native Users remains authoritative. Account approval uses the native user APIs.
        rows = platform.request('GET', '/users/pending', token=current.token)
        return [{'id': row['id'], 'full_name': row['full_name'], 'email': row['email']}
                for row in rows if row.get('organization_id') == current.organization_id
                and row.get('status') == 'pending']

    @app.get('/v1/api/hrms/employees/form-options')
    def form_options(current=Depends(actor)):
        return service.form_options(current)

    @app.get('/v1/api/hrms/employees', response_model=list[EmployeeListItem])
    def directory(current=Depends(actor)):
        return service.directory(current)

    def follow_directory(current, employee_id, left=False):
        # Reviews follow a manager change or a leaver, and a leaver's open onboarding ends; the
        # directory change itself is already saved.
        for follow in (performance.sync_employee,):
            try:
                follow(current, employee_id)
            except AppError:
                logging.getLogger(__name__).exception('%s failed for employee %s', follow.__name__, employee_id)

    @app.put('/v1/api/hrms/employees/{employee_id}', response_model=EmployeeListItem)
    def update_employee(employee_id: str, payload: EmployeeUpdateRequest, current=Depends(actor)):
        result = service.update_employee(current, employee_id, payload)
        follow_directory(current, employee_id)
        return result

    @app.post('/v1/api/hrms/employees/{employee_id}/exit', response_model=EmployeeListItem)
    def exit_employee(employee_id: str, payload: EmployeeExitRequest, current=Depends(actor)):
        result = service.exit_employee(current, employee_id, payload)
        if result['employment_status'] == 'offboarded':
            follow_directory(current, employee_id, left=True)
        return result

    @app.post('/v1/api/hrms/employees/{employee_id}/exit/withdraw', response_model=EmployeeListItem)
    def withdraw_employee_exit(employee_id: str, payload: EmployeeOperationRequest, current=Depends(actor)):
        return service.withdraw_exit(current, employee_id, payload.idempotency_key)

    @app.post('/v1/api/hrms/employees/{employee_id}/setup-access')
    def employee_setup_access(employee_id: str, payload: EmployeeAccessRequest, current=Depends(actor)):
        return setup_access(service, current, employee_id, payload.idempotency_key)

    @app.post('/v1/api/hrms/employees', status_code=201)
    def create_employee(payload: EmployeeCreateRequest, current=Depends(actor)):
        return service.create_employee(current, payload)

    @app.get('/v1/api/hrms/workflows')
    def workflows(current=Depends(actor)):
        from .workflow_config import configured_workflow_rows
        from .offers import offer_workflow_rows
        # One record without a usable enrollment must not hide everyone's other work.
        return configured_workflow_rows(platform, workflow_rows(service, current) + performance.workflows(current) + projects.workflows(current) + cockpit.workflows(current) + wfh.workflows(current),
                                        skip_unenrolled=True) + employee_workflow_rows(platform, current) + offer_workflow_rows(platform, current) + offboarding.workflows(current)

    @app.get('/v1/api/hrms/projects')
    def project_dashboard(current=Depends(actor)):
        return projects.dashboard(current)

    @app.get('/v1/api/hrms/customers')
    def customer_directory(current=Depends(actor)):
        return projects.customers(current)

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
        allowed = performance.allowed(current, row, snap)
        check('request_feedback' in allowed or 'reassign_feedback' in allowed, 'Only the assigned manager or HR can choose a reviewer', 403)
        review = performance.find(snap, row['data']['review_id']) if 'reassign_feedback' in allowed else row
        return [{'id': u['id'], 'name': u['name']} for u in performance.user_options()
                if u['id'] not in {review['data']['employee_user_id'], row['data'].get('reviewer_user_id')}]

    @app.post('/v1/api/hrms/performance/cycles')
    def performance_create(payload: PerformanceAction, current=Depends(actor)):
        from .performance import check
        check(payload.action == 'create_cycle', 'Expected create_cycle', 422)
        return performance.execute(current, 'new', payload)

    @app.post('/v1/api/hrms/performance/{entity_id}/actions')
    def performance_action(entity_id: UUID, payload: PerformanceAction, current=Depends(actor)):
        return performance.execute(current, str(entity_id), payload)

    extra_steps = ExtraSteps(service)

    @app.get('/v1/api/hrms/workflow-steps/{entity_id}')
    def added_steps(entity_id: UUID, current=Depends(actor)):
        return extra_steps.available(current, str(entity_id))

    @app.post('/v1/api/hrms/workflow-steps/{entity_id}')
    def run_added_step(entity_id: UUID, payload: StepRequest, current=Depends(actor)):
        return extra_steps.run(current, str(entity_id), payload.trigger, payload.idempotency_key)

    @app.get('/v1/api/hrms/leave-requests', response_model=list[LeaveListItem])
    def leave(view: str = 'mine', limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
              state: str | None = None, current=Depends(actor)):
        return service.leave(current, view, limit, offset, state)

    @app.post('/v1/api/hrms/leave-requests', response_model=LeaveCreateResponse, status_code=201)
    def create_leave(payload: LeaveCreateRequest, current=Depends(actor)):
        return service.create_leave(current, payload)

    @app.get('/v1/api/hrms/leave-requests/{entity_id}/actions')
    def available(entity_id: UUID, current=Depends(actor)):
        return service.leave_actions(current, str(entity_id))

    @app.post('/v1/api/hrms/leave-requests/{entity_id}/actions')
    def decide(entity_id: UUID, payload: Decision, current=Depends(actor)):
        return service.decide_leave(current, str(entity_id), payload.trigger, payload.idempotency_key)

    def collaboration_access(current, entity_id, scope):
        from .employee_work import employee_enrollments
        from .record_collaboration import authorize_record
        sources = {
            'employee': lambda: employee_enrollments(platform, current),
            'projects': lambda: projects.workflows(current),
            'performance': lambda: performance.workflows(current),
            'content': lambda: cockpit.workflows(current),
            'wfh': lambda: wfh.workflows(current),
            'leave': lambda: workflow_rows(service, current),
            'assets': lambda: assets.board(current)['items'],
            'offboarding': lambda: offboarding.rows(current),
        }
        if scope not in sources:
            raise AppError(404, 'Unknown record scope')
        authorize_record(platform, current, str(entity_id), sources[scope]())

    @app.get('/v1/api/hrms/records/{entity_id}/{scope}/activity')
    def record_activity(entity_id: UUID, scope: str, limit: int = Query(50, ge=1, le=200),
                        offset: int = Query(0, ge=0), current=Depends(actor)):
        collaboration_access(current, entity_id, scope)
        return platform.request('GET', '/audit-events', token=current.token,
                                params={'entity_id': str(entity_id), 'limit': limit, 'offset': offset})

    @app.api_route('/v1/api/hrms/records/{entity_id}/{scope}/comments', methods=['GET', 'POST'])
    @app.api_route('/v1/api/hrms/records/{entity_id}/{scope}/comments/{comment_id}', methods=['PATCH', 'DELETE'])
    @app.api_route('/v1/api/hrms/records/{entity_id}/{scope}/comments/{comment_id}/{operation}', methods=['GET', 'POST'])
    async def record_comments(entity_id: UUID, scope: str, request: Request,
                              comment_id: UUID | None = None, operation: str | None = None,
                              current=Depends(actor)):
        from starlette.concurrency import run_in_threadpool
        from .record_collaboration import comment_path
        if operation and (operation not in {'replies', 'like'} or (operation == 'like' and request.method != 'POST')):
            raise AppError(404, 'Unknown comment operation')
        await run_in_threadpool(collaboration_access, current, entity_id, scope)
        path = await run_in_threadpool(comment_path, platform, current, str(entity_id),
                                      str(comment_id) if comment_id else None, operation)
        return await _proxy(platform, request, path.lstrip('/'), current.token)

    # Explicit read/auth facade: no catch-all mutation proxy. Core task/record/transition,
    # bulk-import mutations cannot bypass HRMS business rules. Native agent execution
    # is available only through the explicitly authorized tenant Settings surface.
    public_gets = {'auth/status', 'invitations/validate'}
    auth_posts = {'auth/login', 'auth/refresh', 'auth/logout', 'auth/forgot-password',
                  'auth/reset-password', 'invitations/accept'}
    private_gets = {'auth/me', 'users/me/organizations', 'organizations/current', 'roles/my-permissions',
                    'workflow-state-machines', 'permissions', 'users/search'}

    @app.api_route('/v1/api/{path:path}', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
    async def facade(path: str, request: Request):
        if path in {'auth/google/url', 'auth/google/callback'}:
            return await google_auth(platform, request, path)
        token = request.headers.get('authorization', '').removeprefix('Bearer ').removeprefix('bearer ')
        if request.method == 'GET' and path in public_gets:
            pass
        elif request.method == 'POST' and path in auth_posts:
            pass
        elif request.method == 'GET' and (path in private_gets or
                (path.startswith('workflow-state-machines/') and path.endswith('/active'))):
            from starlette.concurrency import run_in_threadpool
            await run_in_threadpool(platform.actor, token)
        elif (request.method == 'GET' and path == 'config/file-types') or path.startswith('filehandler/'):
            from .employee_work import authorize_employee_file
            from starlette.concurrency import run_in_threadpool
            current = await run_in_threadpool(platform.actor, token)
            if not await run_in_threadpool(offboarding.authorize_file, current, request.method, path, dict(request.query_params)):
                await run_in_threadpool(authorize_employee_file, platform, current, request.method, path, dict(request.query_params))
        elif request.method == 'POST' and (path == 'entity-records' or
                (path.startswith('workflow-state-machines/') and path.endswith('/enrollments'))):
            from .offers import authorize_offer_request
            from starlette.concurrency import run_in_threadpool
            current = await run_in_threadpool(platform.actor, token)
            try:
                payload = await request.json()
            except (JSONDecodeError, UnicodeDecodeError) as exc:
                raise AppError(400, 'Invalid JSON request body') from exc
            await run_in_threadpool(authorize_offer_request, platform, current, path, payload)
        elif configuration_route(request.method, path, platform.org):
            from starlette.concurrency import run_in_threadpool
            current = await run_in_threadpool(platform.actor, token)
            payload = None
            if request.method != 'GET' and 'application/json' in request.headers.get('content-type', '').lower():
                # Native actions such as user approval have no body even when the
                # browser client sends its default JSON Content-Type header.
                if await request.body():
                    try:
                        payload = await request.json()
                    except (JSONDecodeError, UnicodeDecodeError) as exc:
                        raise AppError(400, 'Invalid JSON request body') from exc
            from .offers import offer_metadata_access
            if request.method == 'GET' and offer_metadata_access(current, path):
                if any(value != current.organization_id for key in ('organization_id', 'org_id')
                       for value in request.query_params.getlist(key)):
                    raise AppError(403, 'Offer configuration is restricted to your organization')
            else:
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
        if response.status_code < 300 and changes_forms(request.method, path):
            from starlette.concurrency import run_in_threadpool
            await run_in_threadpool(follow_form_change, token)
        if request.method == 'GET' and path == 'workflow-state-machines' and response.status_code == 403:
            # The shared skin loader lists workflows for every signed-in user, but only people with
            # platform workflow access may read them; give everyone else the empty list it falls back on.
            return JSONResponse({'scope': request.query_params.get('scope', 'all'),
                                 'published_items': [], 'draft_items': []})
        return response

    def follow_form_change(token):
        """An administrator changed a form or workflow: let the HRMS service use any field or step
        they added, with their own access. Best effort; the change itself has already been saved."""
        custom_fields._keys.clear()

        def as_admin(method, path, json=None):
            response = platform.http.request(method, path, json=json, headers={'authorization': f'Bearer {token}'})
            if response.status_code >= 300:
                raise AppError(response.status_code, f'{method} {path} was refused')
            return response.json()
        try:
            sync_service_access(platform, as_admin)
        except Exception:  # noqa: BLE001 - never fail the administrator's saved change
            logging.getLogger(__name__).exception('HRMS service access was not updated')

    return app


async def _proxy(platform, request, path, token):
    from starlette.concurrency import run_in_threadpool
    content = await request.body()
    headers = {'content-type': request.headers.get('content-type', 'application/json')}
    if token:
        headers['authorization'] = f'Bearer {token}'
    options = {'timeout': 120} if request.method == 'POST' and path.startswith('agent/') else {}
    response = await run_in_threadpool(platform.http.request, request.method, path,
                                     params=list(request.query_params.multi_items()), content=content, headers=headers, **options)
    return Response(response.content, status_code=response.status_code,
                    media_type=response.headers.get('content-type', 'application/json'))


# Importable factory keeps tests independent of environment secrets.
app = create_app() if os.environ.get('PLATFORM_API_URL') else FastAPI()
