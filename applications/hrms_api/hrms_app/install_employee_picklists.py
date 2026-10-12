"""One-time native Employee picklist bindings; preserve tenant edits on reinstall."""
import json
from pathlib import Path

from .catalog import pack_by_type

EMPLOYEE = 'HRMS.Employee'
NAMES = {'department': 'HRMS Departments', 'designation': 'HRMS Designations'}


def install_employee_picklists(api):
    catalog = api.call('GET', '/config/picklists')['items']
    defaults = json.loads(Path(__file__).with_name('reference_options.json').read_text())

    def binding(key, settings):
        if settings.get('picklist_id'):
            return None
        picklist = next((p for p in catalog if p['name'] == NAMES[key]), None)
        if picklist is None:
            values = settings.get('enum_values')
            if not values:
                existing = {r['data'][key] for r in api.records(EMPLOYEE, [key]) if r['data'].get(key)}
                values = sorted(existing | set(defaults[key + 's']))
            picklist = api.call('POST', '/config/picklists', json={
                'name': NAMES[key], 'options': [{'value': v, 'label': v} for v in values]})
            catalog.append(picklist)
        return {**settings, 'picklist_id': picklist['id'],
                'enum_values': [o['value'] if isinstance(o, dict) else o for o in picklist['options']]}

    methods = api.call('GET', '/method-library/methods', params={'entity_type': EMPLOYEE, 'limit': 100})['items']
    if methods:
        types = api.call('GET', '/field-library/field-types')['items']
        select_type = next(t['code'] for t in types if t.get('engine_type') == 'enum')
        for method in methods:
            mid = method['method_id']
            # Repinning creates a new method version. Re-read link IDs before each change.
            for key in NAMES:
                detail = api.call('GET', f'/method-library/methods/{mid}')
                field = next((f for f in detail['fields'] if f['field_key'] == key), None)
                if not field:
                    continue
                settings = binding(key, field.get('settings') or {})
                if settings is None:
                    continue
                version = api.call('POST', f"/field-library/fields/{field['library_field_id']}/versions",
                                   json={'field_type': select_type, 'settings': settings})
                api.call('PATCH', f"/method-library/methods/{mid}/fields/{field['id']}/version",
                         json={'version_id': version['version_id']})
        return

    forms = api.call('GET', '/forms/config', params={'entity_type': EMPLOYEE})['items']
    form = next(f for f in forms if f['schema_key'] == pack_by_type(EMPLOYEE).schema_key)
    fields, changed = [], False
    for field in form['fields']:
        settings = binding(field['field'], field) if field['field'] in NAMES else None
        fields.append({**settings, 'type': 'enum' if settings['enum_values'] else 'string'} if settings else field)
        changed = changed or settings is not None
    if changed:
        api.call('PUT', f"/forms/config/{form['schema_key']}", json={'fields': fields})
