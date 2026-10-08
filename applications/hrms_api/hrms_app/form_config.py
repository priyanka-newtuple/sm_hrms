"""Presentation metadata adapter; HRMS contracts still own commands and permissions.

Fields come from the native model the tenant edits under Settings -> Fields and
Settings -> Forms (method blocks):

1. the entity type's active workflow, once method blocks are pinned to it; the
   engine assembles its schema from those blocks on every publish;
2. the method blocks tagged to the entity type, for a type with no workflow
   (Customer, Employee, Project role);
3. the legacy Form, only while a tenant's forms are not migrated to method blocks.
"""
import re

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
PRESENTATION_KEYS = ('field', 'description', 'placeholder', 'required', 'read_only', 'col_span', 'type', 'enum_values')
METHOD_PAGE_LIMIT = 100


def form_configuration(platform, actor, entity_type):
    if entity_type not in FORM_ACCESS:
        raise AppError(404, 'This form is not exposed by HRMS')
    required = FORM_ACCESS[entity_type]
    caps = capabilities(actor)
    if (required and not required.intersection(caps)) or (not required and not caps):
        raise AppError(403, 'You cannot access this HRMS form')
    return configured_form(platform, entity_type)


def configured_form(platform, entity_type):
    """The entity type's current field configuration, without the access check."""
    workflow = _active_workflow(platform, entity_type)
    if workflow is not None:
        form = _workflow_form(workflow) or _legacy_form(platform, entity_type)
    else:
        form = _method_block_form(platform, entity_type) or _legacy_form(platform, entity_type)
    if form is None:
        raise AppError(409, 'The configured HRMS form is missing or inactive')
    return {'entity_type': entity_type, 'name': form['name'], 'fields': _presentation(platform, form['fields'])}


def has_method_blocks(platform, entity_type):
    """Whether the tenant has moved this entity type's fields onto method blocks."""
    return bool(_methods(platform, entity_type, limit=1))


def _active_workflow(platform, entity_type):
    workflows = platform.call('GET', '/workflow-state-machines', params={'scope': 'published'})['published_items']
    active = [w for w in workflows if w['entity_type'] == entity_type and w['is_active']]
    if len(active) > 1:
        raise AppError(409, f'{entity_type} needs exactly one active workflow')
    return active[0] if active else None


def _workflow_form(workflow):
    definition = workflow.get('definition') or {}
    if not any(state.get('method_refs') for state in definition.get('states', [])):
        return None  # Not migrated yet: its tenant edits still live on the legacy Form.
    fields = [{**field, 'read_only': bool(field.get('read_only') or field.get('editable') is False)}
              for field in definition.get('entity_schema', {}).get('fields', [])]
    return {'name': workflow.get('name') or definition.get('name') or workflow['entity_type'], 'fields': fields}


def _method_block_form(platform, entity_type):
    methods = _methods(platform, entity_type)
    if not methods:
        return None
    engine_types = {t['code']: t.get('engine_type') for t in platform.call('GET', '/field-library/field-types')['items']}
    fields, seen = [], set()
    for method in sorted(methods, key=lambda m: m.get('method_code', 0)):
        detail = platform.call('GET', f"/method-library/methods/{method['method_id']}")
        for field in sorted(detail.get('fields', []), key=lambda f: f.get('position', 0)):
            key = field['field_key']
            if key in seen:
                continue
            seen.add(key)
            settings = field.get('settings') or {}
            fields.append({
                'field': key,
                'type': engine_types.get(field['field_type']) or field['field_type'],
                'description': field.get('label'),
                'placeholder': field.get('placeholder'),
                'required': bool(field.get('required')),
                'read_only': bool(settings.get('read_only')),
                'col_span': settings.get('col_span'),
                'enum_values': settings.get('enum_values') or [],
                'picklist_id': settings.get('picklist_id'),
            })
    return {'name': methods[0]['name'], 'fields': fields}


def _legacy_form(platform, entity_type):
    pack = pack_by_type(entity_type)
    forms = platform.call('GET', '/forms/config', params={'entity_type': entity_type})['items']
    return next((f for f in forms if f.get('schema_key') == pack.schema_key and f.get('is_active', True)), None)


def _methods(platform, entity_type, limit=METHOD_PAGE_LIMIT):
    return platform.call('GET', '/method-library/methods',
                         params={'entity_type': entity_type, 'limit': limit})['items']


def _presentation(platform, fields):
    picklists = []
    if any(f.get('picklist_id') or f.get('enum_values') for f in fields):
        picklists = platform.call('GET', '/config/picklists')['items']
    by_id = {p['id']: p.get('options', []) for p in picklists}
    result = []
    for field in fields:
        item = {key: field.get(key) for key in PRESENTATION_KEYS}
        if item['description'] == _auto_label(field['field']):
            # The Forms migration labels unlabelled fields from their key ("Pm Name");
            # that is not a tenant choice, so the screen keeps its own wording.
            item['description'] = None
        if field.get('picklist_id'):
            choices = by_id.get(field['picklist_id'], [])
            item['enum_values'] = [_value(c) for c in choices]
            item['enum_labels'] = {c['value']: c.get('label', c['value']) for c in choices if isinstance(c, dict)}
        elif field.get('enum_values'):
            # Pinning a block keeps a select's values (what the engine accepts) but not
            # the picklist they came from; recover labels from a picklist holding them.
            labels = _picklist_labels(picklists, field['enum_values'])
            if labels:
                item['enum_labels'] = labels
        result.append(item)
    return result


def _picklist_labels(picklists, values):
    for picklist in picklists:
        options = picklist.get('options', [])
        if set(values) <= {_value(o) for o in options}:
            return {o['value']: o.get('label', o['value']) for o in options if isinstance(o, dict) and o['value'] in values}
    return None


def _auto_label(key):
    return re.sub(r'[_\-.]+', ' ', key).strip().title() or key


def _value(option):
    return option['value'] if isinstance(option, dict) else option
