"""Install additive offer configuration through the public native APIs."""
from pathlib import Path
from copy import deepcopy

FIELDS = [
    ('offer_template_id', 'Offer letter template', 'string', True, None),
    ('first_name', 'First name', 'string', True, None),
    ('last_name', 'Last name', 'string', True, None),
    ('salutation', 'Salutation', 'string', False, 'Mr'),
    ('personal_email', 'Candidate personal email', 'email', True, None),
    ('current_address_line_1', 'Current address line 1', 'text', True, None),
    ('designation', 'Designation', 'string', True, None),
    ('joining_date', 'Expected joining date', 'date', True, None),
    ('base_location', 'Base location', 'string', True, 'Pune, India'),
    ('reporting_manager', 'Reporting manager', 'string', True, 'Dhiraj Nambiar'),
    ('duties', 'Scope of duties', 'text', True, None),
    ('ctc', 'Annual compensation (INR, excluding joining bonus)', 'float', True, None),
    ('basic_percent', 'Basic salary (%)', 'float', True, 50),
    ('hra_percent', 'HRA (%)', 'float', True, 12.5),
    ('special_percent', 'Special allowance (%)', 'float', True, 30),
    ('lta_percent', 'LTA (%)', 'float', True, 7.5),
    ('joining_bonus', 'Joining bonus (INR, additional to annual compensation)', 'float', False, 0),
    ('bonus_payment_terms', 'Joining bonus payment timing', 'string', False, 'with the first payroll that you are part of'),
    ('bonus_tenure_months', 'Joining bonus minimum tenure (months)', 'int', False, 6),
    ('probation_months', 'Probation period (months)', 'int', True, 6),
    ('probation_notice', 'Notice during probation', 'string', True, '2 weeks'),
    ('notice_period', 'Notice after probation', 'string', True, 'one-month'),
    ('signatory_name', 'Authorised signatory', 'string', True, 'Shilpa Mishra'),
    ('offer_date', 'Offer issue date', 'date', True, None),
    ('offer_pdf', 'Generated offer PDF', 'document', False, None),
    ('offer_document_hash', 'Generated document fingerprint', 'string', False, None),
    ('offer_template_hash', 'Template version fingerprint', 'string', False, None),
    ('offer_revision', 'Offer document revision', 'int', False, None),
]


def install(api, machine):
    current = api('GET', f'/workflow-state-machines/{machine}/active')
    if current['entity_type'] != 'hrms_offer':
        raise ValueError('Expected the configured hrms_offer workflow')
    templates = api('GET', '/email-templates')['items']
    template = next((t for t in templates if t['name'] == 'Newtuple offer letter' and t.get('organization_id') == current['organization_id']), None)
    if not template:
        template = api('POST', '/email-templates', json={
            'name': 'Newtuple offer letter', 'subject': 'Offer of employment – {{candidate_full_name}}',
            'entity_type': 'hrms_offer', 'body_html': Path(__file__).with_name('templates').joinpath('newtuple_offer.html').read_text(encoding='utf-8')})
    types = api('GET', '/field-library/field-types')['items']
    links = []
    for key, label, engine, required, default in FIELDS:
        existing = api('GET', '/field-library/fields', params={'search': key, 'limit': 200})['items']
        found = next((f for f in existing if f['identity']['field_key'] == key), None)
        if not found:
            target = 'datetime' if engine == 'date' else engine
            code = next(t['code'] for t in types if t['engine_type'] == target and t['selectable'])
            settings = {'default': default} if default is not None else {}
            if engine == 'document':
                settings = {'document_config': {'type_id': 'generic_document', 'multiple': False}}
            found = api('POST', '/field-library/fields', json={'name': label, 'field_key': key, 'description': label, 'field_type': code, 'settings': settings})
        links.append({'library_field_id': found['identity']['library_field_id'], 'version_id': found['version']['version_id'], 'label': label, 'required': required})
    methods = api('GET', '/method-library/methods', params={'entity_type': 'hrms_offer', 'limit': 200})['items']
    method = next((m for m in methods if m.get('name') == 'Offer'), None)
    if not method:
        method = api('POST', '/method-library/methods', json={'name': 'Offer', 'entity_types': ['hrms_offer'], 'fields': links})['identity']
    mid = method['method_id']
    detail = api('GET', f'/method-library/methods/{mid}')
    def field_link(f):
        return {'library_field_id': f['library_field_id'], 'version_id': f['field_version_id'],
                **{k: f.get(k) for k in ('label', 'placeholder', 'required', 'inherit_from', 'source_entity_type', 'source_field_key', 'ownership')}}
    # Preserve FR-38's original fields and metadata; append only new letter fields.
    merged = [field_link(f) for f in detail['fields']]
    ids = {f['library_field_id'] for f in merged}
    merged.extend(f for f in links if f['library_field_id'] not in ids)
    required_ids = {f['library_field_id'] for f in links if f['required']}
    for field in merged:
        if field['library_field_id'] in required_ids:
            field['required'] = True
    old = [field_link(f) for f in detail['fields']]
    if merged != old:
        detail = api('PUT', f'/method-library/methods/{mid}/fields', json={'fields': merged})
    legacy = [m for m in methods if m.get('name') == 'Offer letter details' and m['method_id'] != mid]
    legacy_ids = {m['method_id'] for m in legacy}
    definition = deepcopy(current['definition'])
    changed = False
    for state in definition['states']:
        refs = [r for r in state.get('method_refs', []) if r['method_id'] not in legacy_ids | {mid}]
        refs.append({'method_id': mid, 'version_id': detail['version']['version_id']})
        changed = changed or refs != state.get('method_refs', [])
        state['method_refs'] = refs
    if not changed:
        return {'template_id': template['template_id'], 'workflow': current}
    for transition in definition['transitions']:
        if transition.get('from') == definition['initial_state'] or transition['to_state'] == 'Approved':
            present = {f['field'] for f in transition.get('required_fields', [])}
            for key, typ in [('offer_pdf', 'document'), ('offer_document_hash', 'string')]:
                if key not in present:
                    transition.setdefault('required_fields', []).append({'field': key, 'type': typ, 'required': True})
    draft = api('POST', f'/workflow-state-machines/{machine}/draft')
    result = api('POST', f"/workflow-state-machines/{draft['id']}/publish", json={'definition': definition, 'canvas_metadata': current.get('canvas_metadata')})
    # Historical workflow versions still reference FR-39; archive it rather
    # than destroying the form versions those records depend on.
    for obsolete in legacy:
        api('POST', f"/method-library/methods/{obsolete['method_id']}/archive")
    return {'template_id': template['template_id'], 'workflow': result['state_machine']}
