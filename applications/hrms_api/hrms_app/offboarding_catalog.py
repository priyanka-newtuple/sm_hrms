"""Native offboarding seed; subsequent tenant edits remain authoritative."""
ENTITY = 'HRMS.Offboarding'
MACHINE = 'hrms_offboarding'

def field(key, label, kind='string', **extra):
    # Native field-library date controls compile to the datetime engine type.
    return dict(field=key, description=label, type='enum' if 'enum_values' in extra else 'datetime' if kind == 'date' else kind, **extra)

SECTIONS = {
    'Exit details': [
        field('employee_id', 'Employee', required=True),
        field('exit_type', 'Exit type', enum_values=['Resignation', 'Termination', 'Contract ended', 'Retirement', 'Other']),
        field('notified_date', 'Date notified', 'date'),
        field('requested_last_day', 'Requested last working day', 'date'),
        field('confirmed_last_day', 'Confirmed last working day', 'date'),
        field('exit_reason', 'Exit reason', 'text'),
        field('supporting_documents', 'Supporting documents', 'document'),
        field('hr_notes', 'HR notes', 'text'),
        field('change_reason', 'Change / cancellation reason', 'text'),
        field('offboarding_approver_id', 'Exit approver', required=True),
        field('offboarding_coordinator_id', 'HR coordinator', required=True),
        field('employee_notification_email', 'Employee-approved personal email for exit updates', 'email', required=True),
        field('notification_email_confirmed', 'Employee has confirmed this contact address', enum_values=['Yes'], required=True),
    ],
    'Handover and clearances': [
        field('handover_owner', 'Handover owner / contact'),
        field('handover_status', 'Handover', enum_values=['Pending', 'In progress', 'Completed', 'Not applicable']),
        field('handover_notes', 'Handover evidence and replacement manager / approver', 'text'),
        field('asset_status', 'Asset clearance', enum_values=['Pending', 'Completed', 'Exception approved', 'Not applicable']),
        field('asset_notes', 'Asset return details / exception approval', 'text'),
        field('external_access_status', 'External email, VPN and application access', enum_values=['Pending', 'Completed', 'Not applicable']),
        field('external_access_notes', 'External access removal evidence', 'text'),
        field('access_cutoff', 'HRMS access cutoff (include timezone)', 'datetime'),
        field('ownership_status', 'Projects, allocations and pending approvals', enum_values=['Pending', 'Completed', 'Not applicable']),
        field('ownership_notes', 'Ownership transfer evidence / not applicable reason', 'text'),
    ],
    'Final HR review': [
        field('settlement_status', 'Settlement confirmation', enum_values=['Pending', 'Confirmed', 'Not applicable']),
        field('settlement_notes', 'Settlement reference / notes', 'text'),
        field('exit_interview_notes', 'Exit interview notes', 'text'),
        field('final_documents', 'Relieving / experience letter and final documents', 'document'),
        field('final_notes', 'Final review notes', 'text'),
    ],
    'Employee handover': [
        field('employee_handover_notes', 'Work handover details', 'text', required=True),
        field('employee_asset_notes', 'Assets to return / return arrangements', 'text', required=True),
        field('employee_questions', 'Questions or assistance needed', 'text'),
        field('employee_handover_confirmed', 'I have provided my handover information', enum_values=['Yes'], required=True),
    ],
}
# Native field permissions (service edit only), not schema read_only: the app
# must write these after verifying effects; schema read_only locks everyone.
SYSTEM_FIELDS = [field(k, label) for k, label in [
    ('notice_verified', 'Notice recorded'), ('departure_verified', 'HRMS access removed'),
    ('withdrawal_verified', 'Notice withdrawn'), ('clearance_verified', 'Clearances verified'), ('approved_at', 'Approved at'),
    ('departed_at', 'Departure confirmed at'), ('completed_at', 'Completed at'),
    ('offboarding_employee_user_id', 'Linked employee account')]]
FIELDS = [f for fields in SECTIONS.values() for f in fields] + SYSTEM_FIELDS

def definition():
    states = ['Draft', 'Pending approval', 'Changes requested', 'Notice & handover',
              'Departure confirmed', 'Final clearance', 'Completed', 'Cancelled']
    transitions = []
    def add(source, trigger, target, required=(), guards=()):
        transitions.append({'key': trigger + '_' + str(len(transitions)), 'trigger': trigger,
            'label': trigger.replace('_', ' ').capitalize(), 'from': source, 'to_state': target,
            'required_fields': [dict(next(f for f in FIELDS if f['field'] == k), required=True) for k in required],
            'guards': list(guards)})
    def equals(k, value):
        return dict(type='field_exact_match', field=k, value=value)
    required = ['exit_type', 'notified_date', 'requested_last_day', 'exit_reason']
    add('Draft', 'submit_for_approval', 'Pending approval', required)
    add('Changes requested', 'resubmit', 'Pending approval', required)
    add('Pending approval', 'request_changes', 'Changes requested', ['change_reason'])
    add('Pending approval', 'approve_exit', 'Notice & handover', ['confirmed_last_day', 'access_cutoff', 'handover_owner'], [equals('notice_verified', 'yes')])
    add('Notice & handover', 'confirm_departure', 'Departure confirmed', guards=[equals('departure_verified', 'yes')])
    add('Departure confirmed', 'start_final_clearance', 'Final clearance')
    add('Final clearance', 'complete_offboarding', 'Completed', ['final_notes'], [equals('departure_verified', 'yes'), equals('clearance_verified', 'yes')])
    for s in states[:3]:
        add(s, 'cancel_request', 'Cancelled', ['change_reason'])
    add('Notice & handover', 'approve_withdrawal', 'Cancelled', ['change_reason'], [equals('withdrawal_verified', 'yes')])
    return dict(machine_key=MACHINE, name='Employee offboarding', entity_type=ENTITY,
        entity_schema=dict(entity_type=ENTITY, fields=FIELDS), initial_state='Draft',
        states=[dict(name=s, order=i+1, tags=['initial'] if i == 0 else ['terminal'] if s in {'Completed','Cancelled'} else []) for i,s in enumerate(states)],
        transitions=transitions)
