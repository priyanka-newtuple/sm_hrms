"""Native collaboration through the same HRMS record visibility as its detail view."""
from .errors import AppError


def authorize_record(platform, actor, entity_id, rows):
    if not any(str(row.get('entity_id') or row.get('id')) == entity_id for row in rows):
        raise AppError(404, 'This record is not available to your account')
    record = platform.request('GET', f'/entity-records/{entity_id}', token=actor.token)
    if record['organization_id'] != actor.organization_id:
        raise AppError(403, 'Record organization mismatch')
    if ('hrms_onboarding_employee' in actor.roles
            and record['data'].get('platform_user_id') != actor.user_id):
        raise AppError(403, 'You can access only your own onboarding')


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
