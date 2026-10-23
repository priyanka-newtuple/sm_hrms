"""Permission-scoped HRMS projection for the platform's reusable workflow table."""
from .errors import AppError
from .service import LEAVE, LEAVE_FIELDS, LeaveApprovers, name


def employee_workflow_rows(platform, actor):
    """Use the same permission-scoped native tracker as HR Cockpit, including terminal work."""
    from .policy import capabilities
    from .employee_work import onboarding_tracker
    if 'onboarding:view' not in capabilities(actor):
        return []
    return [dict(
        entity_id=item['entity_id'], entity_type='HRMS.Employee',
        title=item['title'], identifier=item['identifier'],
        current_state=item['current_state'], state_label=item['current_state'],
        is_terminal=item['completed'], workflow_label=item['workflow_label'],
        owner_name=item.get('assigned_to') or item.get('started_by') or '',
        next_action=', '.join(a.get('label') or a['trigger'] for a in item['actions']),
        progress='', due_date=item['due_date'], employee_work=item,
        workflow_configuration=item.get('workflow_configuration'),
        leave=None, leave_view=None,
    ) for item in onboarding_tracker(platform, actor)]


def workflow_rows(service, actor):
    rows = []
    employees = service.employees()
    own = [e for e in employees if e['data'].get('platform_user_id') == actor.user_id]
    if not own:
        return rows  # Bootstrap administrators have no personal leave profile.
    if len(own) != 1:
        raise AppError(409, 'Your account has multiple employee profiles; reconciliation is required')
    own = own[0]
    by_id = {e['entity_id']: e for e in employees}
    names = {e['data']['platform_user_id']: name(e) for e in employees if e['data'].get('platform_user_id')}
    approvers = LeaveApprovers(service.platform, employees)
    states = service.platform.states('hrms_leaverequest')
    for record in service.platform.records(LEAVE, LEAVE_FIELDS):
        employee = by_id.get(record['data'].get('employee_id'))
        if not employee:
            continue
        data = record['data']
        deciders = approvers(employee, data['start_date'], data['end_date'])
        if employee['entity_id'] != own['entity_id'] and actor.user_id not in deciders:
            continue
        state = states.get(record['entity_id'], 'not_enrolled')
        leave = dict(entity_id=record['entity_id'], identifier=data.get('identifier') or '',
                     employee_name=name(employee), start_date=data['start_date'],
                     end_date=data['end_date'], leave_type=data['leave_type'],
                     reason=data.get('reason'), state=state)
        rows.append(dict(
            entity_id=record['entity_id'], entity_type=LEAVE, title=name(employee),
            identifier=leave['identifier'], current_state=state, workflow_label='Leave request',
            owner_name=', '.join(sorted(names[u] for u in deciders if u in names)) if state == 'pending' else '',
            next_action='Manager approval' if state == 'pending' else '',
            progress=f"{data['start_date']} to {data['end_date']}", due_date=None,
            leave=leave, leave_view='mine' if employee['entity_id'] == own['entity_id'] else 'approvals'))
    return sorted(rows, key=lambda row: (row['title'].casefold(), row['workflow_label'], row['entity_id']))
