"""Explicit native configuration surface; never use the HRMS service credential."""
from .errors import AppError
from .policy import require


def configuration_route(method, path, organization_id):
    if any(part in path for part in ('..', '%', '\\', '//')):
        return False
    parts = path.split('/')
    root = parts[0]
    if root == 'users' and len(parts) > 1 and parts[1] == 'me':
        return False
    if root in {'entity-types', 'field-library', 'method-library', 'email-templates',
                'connectors', 'roles', 'users', 'invitations', 'workflow-board-display-fields'}:
        return True
    if path == 'forms/config' or path.startswith('forms/config/'):
        return True
    if root == 'config':
        return True
    if root == 'workflow-state-machines':
        return 'enrollments' not in parts and 'entities' not in parts and 'transitions' not in parts
    if root == 'organizations':
        return len(parts) > 1 and parts[1] in {'current', organization_id}
    if root == 'integrations':
        return not (len(parts) > 2 and parts[1] == 'organizations' and parts[2] != organization_id)
    if root == 'agent' and len(parts) > 1:
        return parts[1] == 'definitions' or (method == 'GET' and parts[1] in {'runs', 'sessions', 'tools', 'models'})
    if root == 'remote-mcp':
        return method == 'GET' or (parts[-1] not in {'invoke', 'call'})
    if root == 'schedules':
        return parts[-1] != 'run-now'
    if root == 'mcp' and parts[-1] == 'configuration':
        return method in {'GET', 'PATCH'}
    if path == 'analytics/flexible':
        return method == 'POST'
    return method == 'GET' and root in {'permissions', 'action-definitions', 'agent-traces', 'logs', 'audit', 'audit-events', 'events', 'analytics', 'mcp'}


def authorize_configuration(actor, query, payload=None):
    require(actor, 'platform:configure')
    for key in ('organization_id', 'org_id'):
        values = query.getlist(key)
        if payload and isinstance(payload, dict) and key in payload:
            values.append(payload[key])
        if any(value is not None and str(value) != actor.organization_id for value in values):
            raise AppError(403, 'Settings are restricted to your HRMS organization')
