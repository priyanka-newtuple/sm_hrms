"""Field access for the HRMS service account on the record types HRMS reads and writes.

The platform checks every field the service reads or saves against an explicit list on its role.
When an administrator adds a field to an HRMS form in Settings, the service must be allowed that
field too, or the screen can show it but never save it. The service cannot grant itself access:
the installer does it at deploy, and the Settings gateway does it with the administrator's own
token right after they change a form.
"""
from .cockpit_catalog import TYPES as COCKPIT_TYPES
from .errors import AppError
from .form_config import configured_form
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


def sync_service_field_access(platform, call):
    """Add whatever configured fields the service role lacks; never removes any. `call(method, path,
    json=None)` runs as an administrator."""
    role = next((r for r in call('GET', 'roles') if r['name'] == SERVICE_ROLE), None)
    if role is None:
        return []
    current = call('GET', f"roles/{role['id']}")['field_permissions']
    have = {(p['entity_type'], p['field_name']) for p in current}
    added = [grant(kind, field) for kind in sorted(RUNTIME_TYPES) for field in configured_fields(platform, kind)
             if (kind, field) not in have]
    if added:
        keep = [{k: p[k] for k in ('entity_type', 'field_name', 'can_view', 'can_edit', 'mask_value')} for p in current]
        call('PUT', f"roles/{role['id']}", json={'field_permissions': [*keep, *added]})
    return added


def changes_forms(method, path):
    return method != 'GET' and path.split('/')[0] in FORM_ROOTS
