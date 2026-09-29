"""Permission-scoped HRMS projection for the platform's reusable workflow table."""
from .errors import AppError
from .service import LEAVE, LEAVE_FIELDS, name


def workflow_rows(service, actor):
    rows = []
    for case in service.onboarding(actor):
        ready = [s for s in case['steps'] if s['readiness'] == 'ready']
        if case['state'] != 'in_progress':
            ready = []
        rows.append(dict(
            entity_id=case['entity_id'], entity_type='HRMS.OnboardingCase',
            title=case['employee_name'], identifier=case['identifier'],
            current_state=case['state'], workflow_label='Employee onboarding',
            owner_name=', '.join(dict.fromkeys(s['owner_name'] for s in ready)),
            next_action=' · '.join(s['title'] for s in ready) or (
                'Complete onboarding' if case['can_complete_case'] else ''),
            progress=f"{case['completed_steps']}/{case['total_steps']} steps",
            due_date=min((s['due_date'] for s in ready if s['due_date']), default=None),
            leave=None, leave_view=None))

    employees = service.employees()
    own = [e for e in employees if e['data'].get('platform_user_id') == actor.user_id]
    if not own:
        return rows  # Bootstrap administrators have no personal leave profile.
    if len(own) != 1:
        raise AppError(409, 'Your account has multiple employee profiles; reconciliation is required')
    own = own[0]
    code = own['data'].get('employee_code')
    visible = {e['entity_id']: e for e in employees if e['entity_id'] == own['entity_id'] or (
        code and e['data'].get('reports_to_employee_code') == code)}
    states = service.platform.states('hrms_leaverequest')
    for record in service.platform.records(LEAVE, LEAVE_FIELDS):
        employee = visible.get(record['data'].get('employee_id'))
        if not employee:
            continue
        data = record['data']
        manager = next((e for e in employees if e['data'].get('employee_code') ==
                        employee['data'].get('reports_to_employee_code') and
                        employee['data'].get('reports_to_employee_code')), None)
        state = states.get(record['entity_id'], 'not_enrolled')
        leave = dict(entity_id=record['entity_id'], identifier=data.get('identifier') or '',
                     employee_name=name(employee), start_date=data['start_date'],
                     end_date=data['end_date'], leave_type=data['leave_type'],
                     reason=data.get('reason'), state=state)
        rows.append(dict(
            entity_id=record['entity_id'], entity_type=LEAVE, title=name(employee),
            identifier=leave['identifier'], current_state=state, workflow_label='Leave request',
            owner_name=name(manager) if manager and state == 'pending' else '',
            next_action='Manager approval' if state == 'pending' else '',
            progress=f"{data['start_date']} to {data['end_date']}", due_date=None,
            leave=leave, leave_view='mine' if employee['entity_id'] == own['entity_id'] else 'approvals'))
    return sorted(rows, key=lambda row: (row['title'].casefold(), row['workflow_label'], row['entity_id']))
