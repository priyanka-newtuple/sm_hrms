"""Read runtime workflow presentation from the record's enrolled native version."""
from .errors import AppError


def configured_workflow_rows(platform, rows):
    if not rows:
        return rows
    ids = {r['entity_id'] for r in rows}
    enrollments, offset = {}, 0
    while True:
        page = platform.call('GET', '/workflow-enrollments', params={'limit': 200, 'offset': offset})
        if page.get('scan_truncated'):
            raise AppError(502, 'Workflow configuration result was truncated')
        for enrollment in page['items']:
            if enrollment['organization_id'] != platform.org:
                raise AppError(502, 'Workflow configuration belongs to another organization')
            if enrollment['entity_id'] in ids:
                if enrollment['entity_id'] in enrollments:
                    raise AppError(409, 'HRMS requires one workflow enrollment per record')
                enrollments[enrollment['entity_id']] = enrollment
        if not page['has_more']:
            break
        if not page['items']:
            raise AppError(502, 'Workflow configuration page is incomplete')
        offset += len(page['items'])
    definitions = {}
    result = []
    for row in rows:
        enrollment = enrollments.get(row['entity_id'])
        if not enrollment:
            raise AppError(409, 'The HRMS record has no workflow enrollment')
        key = (enrollment['machine_name'], enrollment['machine_version'])
        if key not in definitions:
            native = platform.call('GET', f'/workflow-state-machines/{key[0]}/{key[1]}')
            if native['organization_id'] != platform.org:
                raise AppError(502, 'Workflow definition belongs to another organization')
            definition = native['definition']
            definitions[key] = {
                'name': definition['name'], 'version': key[1], 'machine_name': key[0],
                'states': [dict(name=s['name'], label=s.get('description') or s['name'].replace('_', ' ').title(),
                                terminal='terminal' in s.get('tags', [])) for s in sorted(definition['states'], key=lambda s:s.get('order') or 999999)],
                'transitions': [dict(trigger=t['trigger'], label=t.get('label') or t['trigger'],
                                     from_state=t.get('from', t.get('from_state')), to_state=t['to_state'])
                                for t in definition['transitions']],
            }
        config = definitions[key]
        state = enrollment['current_state']
        metadata = next((s for s in config['states'] if s['name'] == state), None)
        if metadata is None:
            raise AppError(409, 'The current state is missing from the enrolled workflow version')
        transition_labels = {t['trigger'].replace('_', ' '): t['label'] for t in config['transitions'] if t['from_state'] == state}
        next_action = ', '.join(transition_labels.get(a, a) for a in row.get('next_action', '').split(', '))
        result.append({**row, 'next_action': next_action, 'current_state': state, 'state_label': metadata['label'],
                       'is_terminal': metadata['terminal'], 'workflow_label': config['name'],
                       'workflow_configuration': config})
    return result
