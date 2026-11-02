"""Operational adapters for the simplified native offboarding configuration.

Forms, required answers and clearance decisions belong to the published graph.
Old enrollments retain their old rules.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
import os
from .errors import AppError

TAG = 'hrms:offboarding-v4'
ROUTING = {'offboarding_project_manager_id', 'offboarding_office_admin_id', 'offboarding_access_admin_id'}

def enabled(workflow):
    return any(TAG in (s.get('description') or '') for s in workflow['definition'].get('states', []))

def departure_due(values, now):
    try:
        day = datetime.fromisoformat(str(values['confirmed_last_day']).replace('Z', '+00:00')).date()
        today = now.astimezone(ZoneInfo(os.environ.get('HRMS_TIMEZONE', 'Asia/Kolkata'))).date()
    except (KeyError, ValueError):
        raise AppError(422, 'Enter a valid last working day')
    if day > today:
        raise AppError(409, 'Disable HRMS access on or after the last working day')

def role_grants(platform, actor):
    """Resolve native grants for a relationship-scoped projection, never role names."""
    fields, transitions, workflows = {}, set(), set()
    for membership in platform.call('GET', f'/roles/users/{actor.user_id}/roles'):
        if membership['organization_id'] != actor.organization_id:
            raise AppError(403, 'Invalid role scope')
        role = platform.call('GET', f"/roles/{membership['role_id']}")
        if role['organization_id'] != actor.organization_id:
            raise AppError(403, 'Invalid role scope')
        workflows.update(p['machine_name'] for p in role['workflow_permissions'])
        transitions.update((p['machine_name'], p['transition_key']) for p in role['transition_permissions'])
        for f in role['field_permissions']:
            if f['entity_type'] != 'HRMS.Offboarding':
                continue
            view, edit = fields.get(f['field_name'], (False, False))
            fields[f['field_name']] = (view or (f['can_view'] and not f.get('mask_value')), edit or (f['can_view'] and f['can_edit'] and not f.get('mask_value')))
    return fields, transitions, workflows
