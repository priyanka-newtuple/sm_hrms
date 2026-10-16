"""Configure native onboarding returns through the human-authenticated Settings API.

Requires HRMS_SETTINGS_TOKEN and an explicit tenant/machine; never edits platform tables.
Published enrollments are not migrated or reset.
"""
import argparse
import copy
import json
import os
from pathlib import Path

import httpx


def configure(base_url, token, organization_id, machine_name, backup_dir):
    client = httpx.Client(base_url=base_url.rstrip('/') + '/', headers={'Authorization': 'Bearer ' + token}, timeout=60)
    def api(method, path, **kwargs):
        response = client.request(method, path.lstrip('/'), **kwargs)
        response.raise_for_status()
        return response.json()
    assert api('GET', '/organizations/current')['id'] == organization_id, 'Wrong tenant'
    backup = Path(backup_dir)
    backup.mkdir(parents=True, exist_ok=True)
    workflow = next(w for w in api('GET', '/workflow-state-machines', params={'scope': 'published'})['published_items'] if w['machine_name'] == machine_name and w['is_active'])
    def save(name, value):
        path = backup / name
        if not path.exists():
            path.write_text(json.dumps(value, indent=2), encoding='utf-8')
    save('workflow-before.json', workflow)
    definition = copy.deepcopy(workflow['definition'])
    states = {s['name']: s for s in definition['states']}
    verification = 'Onboarding Verification'
    profile = 'Profile Completion Pending'
    provisioning = 'IT & Workspace Provisioning'
    assert all(s in states for s in [verification, profile, provisioning])
    verification_form = api('GET', '/method-library/methods/' + states[verification]['method_refs'][0]['method_id'])
    reason = next(f for f in verification_form['fields'] if f['field_key'] == 'hr_verification_notes')
    for state_name in [verification, profile, provisioning, 'Onboarding Completed']:
        ref = states[state_name]['method_refs'][0]
        form = api('GET', '/method-library/methods/' + ref['method_id'])
        # Refuse to replace unpublished form edits made by an administrator.
        assert form['version']['version_id'] == ref['version_id'], f'{state_name}: review newer form version first'
        save('form-before-' + ref['method_id'] + '.json', form)
        fields = list(form['fields'])
        if not any(f['field_key'] == 'hr_verification_notes' for f in fields):
            fields.append(reason)
        inputs = [{'library_field_id': f['library_field_id'], 'version_id': f['field_version_id'],
                   'label': 'Verification notes / correction reason' if f['field_key'] == 'hr_verification_notes' else f['label'],
                   'placeholder': 'Explain the verification outcome or corrections required.' if f['field_key'] == 'hr_verification_notes' else f.get('placeholder'),
                   'required': f['required'], 'position': i,
                   **{key: f.get(key) for key in ['source_entity_type', 'source_field_key', 'inherit_from', 'ownership']}} for i, f in enumerate(fields)]
        updated = api('PUT', '/method-library/methods/' + ref['method_id'] + '/fields', json={'fields': inputs})
        ref['version_id'] = updated['version']['version_id']
    for key, destination, label in [('request_profile_changes', profile, 'Request employee corrections'), ('request_provisioning_changes', provisioning, 'Request Office Admin corrections')]:
        transition = next((t for t in definition['transitions'] if t['key'] == key), None)
        if transition is None:
            transition = {'key': key, 'trigger': key, 'from': verification, 'guards': [], 'required_fields': []}
            definition['transitions'].append(transition)
        transition.update(to_state=destination, label=label)
        transition['required_fields'] = [f for f in transition['required_fields'] if f['field'] != 'hr_verification_notes'] + [{'field': 'hr_verification_notes', 'type': 'text', 'required': True}]
        transition['guards'] = [g for g in transition['guards'] if not (g['field'] == 'hr_verification_notes' and g['type'] == 'field_present')] + [{'type': 'field_present', 'field': 'hr_verification_notes', 'message': 'Enter a correction reason before returning this task.'}]
    definition['method_schemas'] = []
    draft = api('POST', f'/workflow-state-machines/{machine_name}/draft', json={'definition': definition})
    save('draft.json', draft)
    api('PUT', '/workflow-state-machines/' + draft['id'] + '/draft', json={'definition': definition})
    normalized = api('GET', '/workflow-state-machines/' + draft['id'])['definition']
    report = api('POST', '/workflow-state-machines/validate', json={'machine_name': machine_name, 'definition': normalized})
    if not report['can_publish']:
        raise RuntimeError(json.dumps(report['validation_report']))
    published = api('POST', f"/workflow-state-machines/{draft['id']}/publish", json={'definition': normalized})['state_machine']
    save('published.json', published)
    configure_roles(api, save, published)
    print(json.dumps({'workflow_id': published['id'], 'version': published['version'], 'machine_name': machine_name}))
    client.close()


def configure_roles(api, save, published):
    machine_name = published['machine_name']
    verification, profile, provisioning = 'Onboarding Verification', 'Profile Completion Pending', 'IT & Workspace Provisioning'
    destinations = {'hrms_hr_full': verification, 'hrms_office_admin': provisioning, 'hrms_onboarding_employee': profile}
    for role in api('GET', '/roles'):
        if role['name'] not in destinations:
            continue
        detail = api('GET', '/roles/' + role['id'])
        save('role-before-' + role['name'] + '.json', detail)
        tp = [{k: p[k] for k in ['machine_name', 'transition_key']} for p in detail['transition_permissions']]
        for t in published['definition']['transitions']:
            grant = {'machine_name': machine_name, 'transition_key': t['key']}
            if t['from'] == destinations[role['name']] and grant not in tp:
                tp.append(grant)
        fp = [{k: p[k] for k in ['entity_type', 'field_name', 'can_view', 'can_edit', 'mask_value']} for p in detail['field_permissions'] if not (p['entity_type'] == 'HRMS.Employee' and p['field_name'] == 'hr_verification_notes')]
        fp.append({'entity_type': 'HRMS.Employee', 'field_name': 'hr_verification_notes', 'can_view': True, 'can_edit': role['name'] == 'hrms_hr_full', 'mask_value': False})
        api('PUT', '/roles/' + role['id'], json={'transition_permissions': tp, 'field_permissions': fp})



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--organization-id', required=True)
    parser.add_argument('--machine-name', required=True)
    parser.add_argument('--backup-dir', required=True)
    args = parser.parse_args()
    configure(args.base_url, os.environ['HRMS_SETTINGS_TOKEN'], args.organization_id, args.machine_name, args.backup_dir)
