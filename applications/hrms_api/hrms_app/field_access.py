"""Access for the HRMS service account to the fields and workflow steps of the types HRMS runs.

The platform checks every field the service reads or saves, and every transition it runs, against
explicit lists on its role. When an administrator adds a field to an HRMS form, or a step to an
HRMS workflow, in Settings, the service must be allowed it too, or HRMS can show it but never use
it. The service cannot grant itself access: the installer does it at deploy, and the Settings
gateway does it with the administrator's own token right after they change a form or workflow.
"""
from .cockpit_catalog import TYPES as COCKPIT_TYPES
from .errors import AppError
from .form_config import _active_workflow, configured_form
from .project_catalog import TYPES as PROJECT_TYPES
from .wfh_catalog import TYPES as WFH_TYPES

SERVICE_ROLE = 'hrms_application_service'
RUNTIME_TYPES = frozenset({*PROJECT_TYPES, *COCKPIT_TYPES, *WFH_TYPES,
    'HRMS.Employee', 'HRMS.OnboardingCase', 'HRMS.OnboardingStep', 'HRMS.LeaveRequest',
    'HRMS.PerformanceCycle', 'HRMS.PerformanceReview', 'HRMS.PerformanceGoal', 'HRMS.ProjectFeedback'})
# Settings writes that can add a field to a form.
FORM_ROOTS = {'method-library', 'field-library', 'forms', 'workflow-state-machines', 'entity-types'}


def grant(entity_type, field):
    return {'entity_type': entity_type, 'field_name': field, 'can_view': True, 'can_edit': True, 'mask_value': False}


def configured_fields(platform, entity_type):
    """Every field on the type's configured form; none when it has no readable form yet."""
    try:
        return [f['field'] for f in configured_form(platform, entity_type)['fields']]
    except AppError:
        return []


def configured_transitions(platform, entity_type):
    """(machine name, transition key) for every step of the type's active workflow."""
    try:
        workflow = _active_workflow(platform, entity_type)
    except AppError:
        return []
    if not workflow:
        return []
    return [(workflow['machine_name'], t.get('key') or f"{t.get('from', t.get('from_state'))}_to_{t['to_state']}")
            for t in (workflow.get('definition') or {}).get('transitions', [])]


def sync_service_access(platform, call):
    """Add whatever configured fields and workflow steps the service role lacks; never removes
    any. `call(method, path, json=None)` runs as an administrator."""
    role = next((r for r in call('GET', 'roles') if r['name'] == SERVICE_ROLE), None)
    if role is None:
        return []
    current = call('GET', f"roles/{role['id']}")
    have = {(p['entity_type'], p['field_name']) for p in current['field_permissions']}
    fields = [grant(kind, field) for kind in sorted(RUNTIME_TYPES) for field in configured_fields(platform, kind)
              if (kind, field) not in have]
    steps = {(machine, key) for kind in sorted(RUNTIME_TYPES) for machine, key in configured_transitions(platform, kind)}
    steps -= {(p['machine_name'], p['transition_key']) for p in current['transition_permissions']}
    machines = {machine for machine, _ in steps} - {p['machine_name'] for p in current['workflow_permissions']}
    update = {}
    if fields:
        update['field_permissions'] = [*({k: p[k] for k in ('entity_type', 'field_name', 'can_view', 'can_edit', 'mask_value')}
                                         for p in current['field_permissions']), *fields]
    if steps:
        update['transition_permissions'] = [*({'machine_name': p['machine_name'], 'transition_key': p['transition_key']}
                                              for p in current['transition_permissions']),
                                            *({'machine_name': m, 'transition_key': k} for m, k in sorted(steps))]
    if machines:
        update['workflow_permissions'] = [*({'machine_name': p['machine_name']} for p in current['workflow_permissions']),
                                          *({'machine_name': m} for m in sorted(machines))]
    if update:
        call('PUT', f"roles/{role['id']}", json=update)
    return [*fields, *({'machine_name': m, 'transition_key': k} for m, k in sorted(steps))]


def changes_forms(method, path):
    return method != 'GET' and path.split('/')[0] in FORM_ROOTS
