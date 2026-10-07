from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from hrms_app.catalog import pack_by_type
from hrms_app.errors import AppError
from hrms_app.policy import ROLE_CAPABILITIES
from hrms_app.project_catalog import (
    ALLOCATION,
    CUSTOMER,
    PROJECT,
    ROLE,
)
from hrms_app.project_contracts import Action
from hrms_app.projects import ProjectsService, capacity_segments
from test_performance import Journal, Platform, actor


class ProjectPlatform(Platform):
    def __init__(self):
        super().__init__()
        self.role_options = []
        self.role_form = {**pack_by_type(ALLOCATION).form_request(), 'fields': [
            {'field': 'project_role_id', 'type': 'enum', 'picklist_id': 'staffing-roles'}]}

    def call(self, method, path, **kwargs):
        if method == 'GET' and path == '/forms/config':
            return {'items': [deepcopy(self.role_form)]}
        if method == 'GET' and path == '/config/picklists':
            return {'items': [{'id': 'staffing-roles', 'options': deepcopy(self.role_options)}]}
        return super().call(method, path, **kwargs)


class ProjectJournal(Journal):
    def execute(self, sql, params):
        return SimpleNamespace(
            fetchone=lambda: next(
                (
                    (key,)
                    for key, op in self.ops.items()
                    if key != params[1]
                    and op.result is None
                    and "project_plan" in op.progress
                ),
                None,
            )
        )


@pytest.fixture
def system():
    platform, journal = ProjectPlatform(), ProjectJournal()
    ids = {
        key: str(uuid4())
        for key in (
            "pm",
            "dm",
            "sa",
            "hr",
            "employee",
            "outsider",
            "customer",
            "role",
            "employee_record",
        )
    }
    platform.add(CUSTOMER, {"name": "Customer"}, entity_id=ids["customer"])
    platform.add(ROLE, {"name": "Engineer"}, entity_id=ids["role"])
    platform.role_options = [{"value": ids["role"], "label": "Engineer"}]
    people = [
        {"id": ids[k], "name": k, "capabilities": ROLE_CAPABILITIES[r]}
        for k, r in [
            ("pm", "hrms_project_manager"),
            ("dm", "hrms_delivery_manager"),
            ("sa", "superadmin"),
            ("hr", "hrms_hr_full"),
        ]
    ]
    employees = [
        {
            "entity_id": ids["employee_record"],
            "data": {
                "first_name": "Employee",
                "last_name": "One",
                "platform_user_id": ids["employee"],
                "employment_status": "active",
            },
        }
    ]
    service = ProjectsService(
        SimpleNamespace(
            platform=platform,
            journal=journal,
            employees=lambda: deepcopy(employees),
            onboarding=lambda actor: [],
        )
    )
    service.people = lambda actor=None: deepcopy(people)
    return service, platform, journal, ids


def perform(system, who, target, action, data=None, key=None, revision=None):
    service, platform, _, ids = system
    roles = {
        "pm": "hrms_project_manager",
        "dm": "hrms_delivery_manager",
        "sa": "superadmin",
        "hr": "hrms_hr_full",
        "employee": "hrms_employee",
        "outsider": "hrms_project_manager",
    }
    revision = (
        platform.rows[target]["data"].get("revision", 0)
        if revision is None and target in platform.rows
        else revision or 0
    )
    return service.execute(
        actor(ids[who], roles[who]),
        target,
        Action(
            action=action,
            data=data or {},
            expected_revision=revision,
            idempotency_key=key or str(uuid4()),
        ),
    )


def project_data(ids):
    return {
        "name": "Delivery project",
        "customer_id": ids["customer"],
        "pm_id": ids["pm"],
        "dm_id": ids["dm"],
        "approver_id": ids["sa"],
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "budget_amount": 999,
        "billing_rate": 123,
    }


def open_project(system):
    _, platform, _, ids = system
    change = perform(system, "pm", "new", "create_project", project_data(ids))[
        "entity_id"
    ]
    project = platform.rows[change]["data"]["project_id"]
    perform(system, "pm", change, "submit")
    perform(system, "sa", change, "approve")
    return project


def allocation_data(ids, **extra):
    return dict(
        employee_id=ids["employee_record"],
        project_role_id=ids["role"],
        start_date="2026-02-01",
        end_date="2026-06-30",
        percentage=50,
        billing_rate=100,
        **extra,
    )


def test_project_creation_approval_amendment_and_scope(system):
    service, platform, _, ids = system
    project = open_project(system)
    assert platform.rows[project]["state"] == "planned"
    hr = service.dashboard(actor(ids["hr"], "hrms_hr_full"))
    assert "budget_amount" not in hr["projects"][0]["data"]
    assert "billing_rate" not in hr["requests"][0]["data"]["proposed"]
    assert not service.dashboard(actor(ids["employee"], "hrms_employee"))["projects"]
    assert not service.manage(
        actor(ids["outsider"], "hrms_hr_full", "hrms_project_manager"),
        platform.rows[project],
    )
    with pytest.raises(AppError) as exc:
        perform(system, "outsider", project, "propose_amendment", project_data(ids))
    assert exc.value.status == 403
    amended = project_data(ids)
    amended["name"] = "Revised project"
    change = perform(system, "pm", project, "propose_amendment", amended)["entity_id"]
    assert platform.rows[project]["data"]["name"] == "Delivery project"
    perform(system, "pm", change, "submit")
    with pytest.raises(AppError):
        perform(system, "pm", change, "approve")
    perform(system, "sa", change, "request_changes", {"comment": "Clarify scope"})
    perform(system, "pm", change, "revise")
    perform(system, "pm", change, "submit")
    perform(system, "sa", change, "approve")
    assert platform.rows[project]["data"]["name"] == "Revised project"


def test_allocations_commit_only_after_approval_and_release(system):
    service, platform, _, ids = system
    project = open_project(system)
    change = perform(system, "pm", project, "request_allocation", allocation_data(ids))[
        "entity_id"
    ]
    assert not service.snapshot()[ALLOCATION]
    assert platform.rows[change]["data"]["approver_id"] == ids["dm"]
    perform(system, "pm", change, "submit")
    perform(system, "dm", change, "approve")
    allocation = service.snapshot()[ALLOCATION][0]
    own = service.dashboard(actor(ids["employee"], "hrms_employee"))
    assert len(own["projects"]) == 1 and len(own["allocations"]) == 1
    assert "billing_rate" not in own["allocations"][0]["data"]
    with pytest.raises(AppError, match="overlapping"):
        perform(system, "pm", project, "request_allocation", allocation_data(ids))
    release = perform(
        system,
        "pm",
        allocation["entity_id"],
        "release_allocation",
        {"note": "Moved to another project"},
    )["entity_id"]
    perform(system, "pm", release, "submit")
    perform(system, "dm", release, "approve")
    assert platform.rows[allocation["entity_id"]]["state"] == "cancelled"


def test_stale_version_and_recheck_at_approval(system):
    _service, platform, _, ids = system
    project = open_project(system)
    with pytest.raises(AppError, match="changed"):
        perform(system, "pm", project, "start", revision=99)
    change = perform(system, "pm", project, "request_allocation", allocation_data(ids))[
        "entity_id"
    ]
    perform(system, "pm", change, "submit")
    platform.add(
        ALLOCATION,
        {**allocation_data(ids), "project_id": "another-project", "percentage": 75},
        state="active",
    )
    with pytest.raises(AppError, match="100%"):
        perform(system, "dm", change, "approve")
    assert platform.rows[change]["state"] == "pending"
    perform(system, "pm", change, "withdraw")
    updated = allocation_data(ids)
    updated["note"] = "Approved staffing exception requested"
    perform(system, "pm", change, "edit_request", updated)
    perform(system, "pm", change, "submit")
    perform(system, "dm", change, "approve")


def test_dm_request_routes_to_independent_business_approver(system):
    _, platform, _, ids = system
    project = open_project(system)
    with pytest.raises(AppError, match="independent"):
        perform(system, "dm", project, "request_allocation", allocation_data(ids))
    change = perform(
        system,
        "dm",
        project,
        "request_allocation",
        allocation_data(ids, approver_id=ids["sa"]),
    )["entity_id"]
    assert platform.rows[change]["data"]["approver_id"] == ids["sa"]


def test_partial_approval_recovery_blocks_other_mutations(system):
    service, platform, _, ids = system
    change = perform(system, "pm", "new", "create_project", project_data(ids))[
        "entity_id"
    ]
    perform(system, "pm", change, "submit")
    revision = platform.rows[change]["data"]["revision"]
    platform.fail_trigger = "approve"
    with pytest.raises(AppError, match="Injected"):
        perform(system, "sa", change, "approve", key="retry-key-123", revision=revision)
    with pytest.raises(AppError, match="recovery"):
        perform(system, "pm", "new", "create_project", project_data(ids))
    result = perform(
        system, "sa", change, "approve", key="retry-key-123", revision=revision
    )
    assert result == perform(
        system, "sa", change, "approve", key="retry-key-123", revision=revision
    )
    assert len(service.snapshot()[PROJECT]) == 1
    assert platform.rows[change]["data"]["applied"] == "yes"


def test_capacity_uses_disjoint_intervals_not_total_sum():
    proposed = {
        "employee_id": "e",
        "project_id": "p",
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "percentage": 40,
    }
    rows = [
        {
            "entity_id": "a",
            "state": "active",
            "data": {
                **proposed,
                "project_id": "other",
                "start_date": "2026-01-01",
                "end_date": "2026-01-15",
                "percentage": 60,
            },
        },
        {
            "entity_id": "b",
            "state": "planned",
            "data": {
                **proposed,
                "project_id": "other",
                "start_date": "2026-01-16",
                "end_date": "2026-01-31",
                "percentage": 60,
            },
        },
    ]
    preview = capacity_segments(rows, proposed)
    assert not preview["over_capacity"] and not preview["duplicate"]
    assert len(preview["segments"]) == 2 and all(
        s["total"] == 100 for s in preview["segments"]
    )


def test_project_lifecycle_and_committed_date_bounds(system):
    service, platform, _, ids = system
    project = open_project(system)
    change = perform(system, "pm", project, "request_allocation", allocation_data(ids))[
        "entity_id"
    ]
    perform(system, "pm", change, "submit")
    perform(system, "dm", change, "approve")
    allocation = service.snapshot()[ALLOCATION][0]["entity_id"]
    perform(system, "pm", project, "start")
    perform(system, "pm", allocation, "start")
    perform(system, "pm", project, "hold")
    with pytest.raises(AppError):
        perform(system, "pm", project, "request_allocation", allocation_data(ids))
    perform(system, "pm", project, "resume")
    details = project_data(ids)
    details["end_date"] = "2026-03-01"
    amendment = perform(system, "pm", project, "propose_amendment", details)[
        "entity_id"
    ]
    with pytest.raises(AppError, match="committed allocations"):
        perform(system, "pm", amendment, "submit")
    with pytest.raises(AppError, match="live allocations"):
        perform(system, "pm", project, "complete")
    perform(system, "pm", allocation, "complete")
    perform(system, "pm", project, "complete")
    perform(system, "pm", project, "archive")
    assert platform.rows[project]["state"] == "archived"


def test_failure_after_approval_transition_resumes_without_duplicate(system):
    service, platform, _, ids = system
    change = perform(system, "pm", "new", "create_project", project_data(ids))[
        "entity_id"
    ]
    project = platform.rows[change]["data"]["project_id"]
    perform(system, "pm", change, "submit")
    revision = platform.rows[change]["data"]["revision"]
    original_call = platform.call

    def fail_once(method, path, **kwargs):
        if path == f"/entities/{project}/transitions":
            platform.call = original_call
            raise AppError(503, "Failure after request approval")
        return original_call(method, path, **kwargs)

    platform.call = fail_once
    with pytest.raises(AppError, match="after request approval"):
        perform(
            system,
            "sa",
            change,
            "approve",
            key="partial-approval-123",
            revision=revision,
        )
    assert (
        platform.rows[change]["state"] == "approved"
        and platform.rows[change]["data"]["applied"] == "no"
    )
    assert platform.rows[project]["state"] == "draft"
    perform(
        system, "sa", change, "approve", key="partial-approval-123", revision=revision
    )
    assert (
        platform.rows[project]["state"] == "planned"
        and platform.rows[change]["data"]["applied"] == "yes"
    )
    assert len(service.snapshot()[PROJECT]) == 1


def test_allocation_approval_completes_only_ready_authorized_onboarding_step(system):
    service, platform, _, ids = system
    project = open_project(system)
    step = platform.add(
        "HRMS.OnboardingStep",
        {"case_id": "case", "sequence": 8, "title": "Allocate to project"},
        state="open",
    )["entity_id"]
    service.hrms.onboarding = lambda who: [
        {
            "employee_entity_id": ids["employee_record"],
            "steps": [
                {
                    "sequence": 8,
                    "task_id": step,
                    "can_complete": who.user_id == ids["dm"],
                }
            ],
        }
    ]
    change = perform(system, "pm", project, "request_allocation", allocation_data(ids))[
        "entity_id"
    ]
    perform(system, "pm", change, "submit")
    perform(system, "dm", change, "approve")
    assert platform.rows[step]["state"] == "completed"
    assert len(service.snapshot()[ALLOCATION]) == 1


def test_tenant_and_draft_visibility(system):
    service, _platform, _, ids = system
    change = perform(system, "pm", "new", "create_project", project_data(ids))[
        "entity_id"
    ]
    assert not service.dashboard(actor(ids["hr"], "hrms_hr_full"))["projects"]
    assert not service.dashboard(actor(ids["outsider"], "hrms_delivery_manager"))[
        "projects"
    ]
    foreign = actor(ids["pm"], "hrms_project_manager")
    foreign = type(foreign)(
        foreign.user_id, "other-org", "", foreign.roles, frozenset()
    )
    with pytest.raises(AppError, match="Organization"):
        service.execute(
            foreign,
            change,
            Action(
                action="submit", expected_revision=1, idempotency_key="cross-org-denied"
            ),
        )



def test_configured_allocation_access_is_enforced(system):
    from dataclasses import replace

    from hrms_app.policy import capabilities
    service, platform, _, ids = system
    project = open_project(system)
    pm = actor(ids['pm'], 'hrms_project_manager')
    restricted = replace(pm, project_policy={'hrms_project_manager': ['project:view', 'project:manage_assigned']})
    assert 'request_allocation' in service.allowed(pm, platform.rows[project], service.snapshot())
    assert 'request_allocation' not in service.allowed(restricted, platform.rows[project], service.snapshot())
    with pytest.raises(AppError) as error:
        service.execute(restricted, project, Action(action='request_allocation', data=allocation_data(ids), expected_revision=platform.rows[project]['data'].get('revision',0), idempotency_key=str(uuid4())))
    assert error.value.status == 403
    assert 'allocation:request' in capabilities(pm)  # Other tenants retain defaults.
    disabled = replace(pm, project_policy={'hrms_project_manager': []})
    assert service.workflows(disabled) == []
    with pytest.raises(AppError):
        service.dashboard(disabled)


def test_project_policy_cannot_grant_core_or_hr_permissions():
    from dataclasses import replace

    from hrms_app.policy import capabilities
    from hrms_app.project_access import validate_project_access
    for grants in [['platform:configure'], ['employee:create'], ['allocation:request'], ['project:view', 'allocation:request']]:
        with pytest.raises(AppError):
            validate_project_access({'hrms_project_manager': grants}, {'hrms_project_manager'})
    with pytest.raises(AppError):
        validate_project_access({'hrms_application_service': []}, {'hrms_project_manager'})
    validate_project_access({'custom': ['project:view', 'project:manage_assigned', 'allocation:request']}, {'custom'})
    sa = replace(actor('admin', 'superadmin'), project_policy={'superadmin': []})
    assert 'platform:configure' in capabilities(sa)
    assert 'project:view' not in capabilities(sa)


def test_project_role_options_follow_all_native_picklist_values_and_labels(system):
    service, platform, _, ids = system
    platform.role_options = [{'value': f'role-{i}', 'label': f'Role {i}'} for i in range(40)]
    options = service.options(actor(ids['pm'], 'hrms_project_manager'))
    assert options['project_roles'] == [{'id': o['value'], 'name': o['label']} for o in platform.role_options]
    platform.role_options = [{'value': 'architect', 'label': 'Solution Architect'}]
    assert service.options(actor(ids['pm'], 'hrms_project_manager'))['project_roles'] == [
        {'id': 'architect', 'name': 'Solution Architect'}]


def test_allocation_accepts_static_picklist_value_without_role_record(system):
    _, platform, _, ids = system
    project = open_project(system)
    platform.role_options.append({'value': 'architect', 'label': 'Solution Architect'})
    data = allocation_data(ids)
    data['project_role_id'] = 'architect'
    change = perform(system, 'pm', project, 'request_allocation', data)['entity_id']
    assert platform.rows[change]['data']['proposed']['project_role_name'] == 'Solution Architect'
    perform(system, 'pm', change, 'submit')
    perform(system, 'dm', change, 'approve')


def test_removed_picklist_role_is_rejected_at_request_and_approval(system):
    service, platform, _, ids = system
    project = open_project(system)
    change = perform(system, 'pm', project, 'request_allocation', allocation_data(ids))['entity_id']
    perform(system, 'pm', change, 'submit')
    platform.role_options = []
    assert service.options(actor(ids['pm'], 'hrms_project_manager'))['project_roles'] == []
    with pytest.raises(AppError, match='current configured picklist'):
        perform(system, 'dm', change, 'approve')
    with pytest.raises(AppError, match='current configured picklist'):
        perform(system, 'pm', project, 'request_allocation', allocation_data(ids))
    assert platform.rows[change]['state'] == 'pending'


def test_project_role_form_missing_or_inactive_fails_closed(system):
    service, platform, _, ids = system
    platform.role_form['is_active'] = False
    with pytest.raises(AppError) as error:
        service.options(actor(ids['pm'], 'hrms_project_manager'))
    assert error.value.status == 409
