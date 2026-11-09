"""Native collaboration through the same HRMS record visibility as its detail view."""
from .errors import AppError
from .policy import entity_allowed


def authorize_record(platform, actor, entity_id, rows):
    if not any(str(row.get('entity_id') or row.get('id')) == entity_id for row in rows):
        raise AppError(404, 'This record is not available to your account')
    record = platform.request('GET', f'/entity-records/{entity_id}', token=actor.token)
    if record['organization_id'] != actor.organization_id:
        raise AppError(403, 'Record organization mismatch')
    if ('hrms_onboarding_employee' in actor.roles
            and record['data'].get('platform_user_id') != actor.user_id):
        raise AppError(403, 'You can access only your own onboarding')
    return record


def comment_path(platform, actor, entity_id, comment_id=None, operation=None):
    """Resolve IDs through visible native comments, never trust a browser-supplied binding."""
    root = f'/entities/{entity_id}/comments'
    if not comment_id:
        return root
    comments = platform.request('GET', root, token=actor.token)['comments']
    if not any(c['id'] == comment_id for c in comments):
        found = False
        for parent in comments:
            if not parent.get('reply_count'):
                continue
            replies = platform.request('GET', f"/comments/{parent['id']}/replies", token=actor.token)
            if any(c['id'] == comment_id and c['entity_id'] == entity_id for c in replies['comments']):
                found = True
                break
        if not found:
            raise AppError(404, 'Comment is not available on this record')
    return f'/comments/{comment_id}' + (f'/{operation}' if operation else '')


def metadata(platform, actor, record, rows, workflow_id=None):
    """Presentation capabilities only; native writes recheck permission on every request."""
    entity_id = str(record['entity_id'])
    candidates = [r for r in rows if str(r.get('entity_id') or r.get('id')) == entity_id]
    row = next((r for r in candidates if not workflow_id or r.get('workflow_id') == workflow_id), {})
    # Module rows differ in shape; the native record is the authority for its type.
    kind = row.get('entity_type') or next(
        (t['name'] for t in platform.call('GET', '/entity-types')['items']
         if t['entity_type_id'] == record['entity_type_id']), None)
    def permitted(action):
        return bool(kind) and entity_allowed(actor, kind, action)
    return dict(entity_id=entity_id, current_state=row.get('current_state') or row.get('state'),
                state_entered_at=row.get('state_entered_at'), due_date=record.get('due_date'),
                created_at=record.get('created_at'), updated_at=record.get('updated_at'),
                assignee_id=record.get('assignee_id'), assignee_name=row.get('assignee_name'),
                can_edit_due_date=permitted('edit'), can_archive=permitted('delete'))


def authorize_document(platform, actor, method, path, query, offboarding):
    """Route by the native file's owner, not by unrelated module permissions."""
    from .employee_work import authorize_employee_file
    if method == 'GET' and path == 'config/file-types':
        return authorize_employee_file(platform, actor, method, path, query)
    if method == 'POST' and path == 'filehandler/upload':
        entity_id = query.get('owner_entity_id')
    elif method == 'GET' and path.startswith('filehandler/') and len(path.split('/')) in {2, 3}:
        parts = path.split('/')
        if len(parts) == 3 and parts[2] not in {'download', 'download-url'}:
            raise AppError(403, 'Unsupported document operation')
        document = platform.request('GET', '/filehandler/' + parts[1], token=actor.token)
        entity_id = document.get('owner_entity_id')
    else:
        raise AppError(403, 'Use the configured document field')
    if not entity_id:
        raise AppError(403, 'Document has no accessible owner record')
    record = platform.request('GET', '/entity-records/' + str(entity_id), token=actor.token)
    if record['organization_id'] != actor.organization_id:
        raise AppError(403, 'Document organization mismatch')
    # Schema lookup only; all record/file reads and the eventual download use the human token.
    employee_type = platform.call('GET', '/entity-types/HRMS.Employee')
    if record['entity_type_id'] == employee_type['entity_type_id']:
        return authorize_employee_file(platform, actor, method, path, query)
    if not offboarding.authorize_file(actor, method, path, query):
        raise AppError(403, 'Document is not available in this workflow')
