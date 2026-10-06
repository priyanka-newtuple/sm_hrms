"""Presentation metadata adapter; HRMS contracts still own commands and permissions."""
from .catalog import pack_by_type
from .errors import AppError
from .policy import capabilities

from .cockpit_catalog import TYPES as COCKPIT_TYPES

FORM_ACCESS = {
    'HRMS.WorkFromHomePolicy': {'wfh:configure'},
    'HRMS.WorkFromHomeRequest': {'wfh:request', 'wfh:approve'},
    **{kind: {'cockpit:view'} for kind in COCKPIT_TYPES},
    'HRMS.Employee': {'employee:create', 'employee:read'},
    'HRMS.LeaveRequest': {'leave:create'},
    **{kind: {'project:view'} for kind in ('HRMS.Project', 'HRMS.ProjectChange', 'HRMS.Customer', 'HRMS.Allocation', 'HRMS.AllocationChange', 'HRMS.ProjectRole')},
    **{kind: set() for kind in ('HRMS.PerformanceCycle', 'HRMS.PerformanceGoal', 'HRMS.PerformanceReview', 'HRMS.ProjectFeedback')},
}


def form_configuration(platform, actor, entity_type):
    if entity_type not in FORM_ACCESS:
        raise AppError(404, 'This form is not exposed by HRMS')
    required = FORM_ACCESS[entity_type]
    caps = capabilities(actor)
    if (required and not required.intersection(caps)) or (not required and not caps):
        raise AppError(403, 'You cannot access this HRMS form')
    pack = pack_by_type(entity_type)
    forms = platform.call('GET', '/forms/config', params={'entity_type': entity_type})['items']
    form = next((f for f in forms if f.get('schema_key') == pack.schema_key and f.get('is_active', True)), None)
    if not form:
        raise AppError(409, 'The configured HRMS form is missing or inactive')
    # Resolve the native picklist once; expose only presentation values.
    picklists = {}
    if any(f.get('picklist_id') for f in form.get('fields', [])):
        picklists = {p['id']: p.get('options', []) for p in platform.call('GET', '/config/picklists')['items']}
    fields = []
    for field in form.get('fields', []):
        item = {key: field.get(key) for key in ('field', 'description', 'placeholder', 'required', 'read_only', 'col_span', 'type', 'enum_values')}
        if field.get('picklist_id'):
            choices = picklists.get(field['picklist_id'], [])
            item['enum_values'] = [c['value'] if isinstance(c, dict) else c for c in choices]
            item['enum_labels'] = {c['value']: c.get('label', c['value']) for c in choices if isinstance(c, dict)}
        fields.append(item)
    return {'entity_type': entity_type, 'name': form['name'], 'fields': fields}
