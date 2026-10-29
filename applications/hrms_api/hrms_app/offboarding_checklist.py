"""Five-stage offboarding tenant configuration; legacy enrollments retain their graph."""
from .offboarding_catalog import field
from .errors import AppError

STAGES = ['Not Started', 'In Progress', 'Submitted', 'Pending Clearance', 'Completed']
DECLARATION = 'I confirm that the information provided in this offboarding form is accurate to the best of my knowledge and that I have disclosed any pending handover or clearance activities.'


def questions(items):
    result = []
    for key, label, options in items:
        result.extend([field(key, label, enum_values=options), field(key + '_remarks', 'Pending actions / remarks', 'text')])
    return result


CHECKLIST = {
    'Employee Information': [field('exit_employee_name', 'Employee name'), field('exit_employee_code', 'Employee ID'), field('exit_date_joined', 'Date of joining', 'date'), field('confirmed_last_day', 'Confirmed last working day', 'date')],
    'Knowledge Transfer & Handover': questions([
        ('exit_projects_handed_over', 'Have all ongoing projects been handed over to the concerned team members?', ['Yes','No']),
        ('exit_documents_shared', 'Have all necessary project documents, credentials, and notes been shared through approved channels?', ['Yes','No']),
        ('exit_tasks_updated', 'Have all pending tasks and deliverables been updated in the project management tool?', ['Yes','No']),
        ('exit_manager_confirmed', 'Has the Project Manager confirmed satisfactory knowledge transfer completion via email?', ['Yes','No']),
    ]),
    'Access & Asset Clearance': questions([
        ('exit_assets_returned', 'Have all company assets (laptop, charger, ID card, SIM card, etc.) been returned?', ['Yes','No']),
        ('exit_personal_data_removed', 'Has personal data been removed from company devices in accordance with company policy?', ['Yes','No']),
        ('exit_access_revoked', 'Has access to company systems (email, GitHub, Slack, Drive, etc.) been revoked or transferred?', ['Yes','No']),
    ]),
    'HR & Administration': questions([
        ('exit_resignation_acknowledged', 'Has the resignation letter been submitted and acknowledged?', ['Yes','No']),
        ('exit_interview_completed', 'Has the exit interview form been completed?', ['Yes','No']),
        ('exit_claims_cleared', 'Have all pending reimbursements, travel claims, or advances been cleared?', ['Yes','No']),
        ('exit_settlement_explained', 'Has the full and final settlement and relieving letter process been explained?', ['Yes','No']),
        ('exit_keys_returned', 'Have the office access card and keys been returned?', ['Yes','No','N/A']),
    ]),
    'Employee Feedback & Experience': [
        field('exit_enjoyed', 'What did you enjoy most about working at Newtuple Technologies?', 'text'),
        field('exit_improvements', 'What areas do you think can be improved (culture, processes, communication, etc.)?', 'text'),
        field('exit_rejoin', 'Would you consider rejoining Newtuple in the future?', enum_values=['Yes','No','Maybe']),
        field('exit_suggestions', 'Any suggestions for your team or management?', 'text'),
    ],
    'Declaration & Sign-Off': [field('exit_acknowledgment', DECLARATION, 'boolean')],
}
EMPLOYEE_KEYS = {f['field'] for title, fields in CHECKLIST.items() if title != 'Employee Information' for f in fields}
METADATA = [field(k, label) for k, label in [
    ('exit_employee_name','Employee name'),('exit_employee_code','Employee ID'),('exit_date_joined','Date of joining'),
    ('offboarding_coordinator_email','HR coordinator email'),('offboarding_workspace_url','MyHub tasks address'),('checklist_submitted_at','Checklist submitted at'),
    ('checklist_submitted_by','Checklist submitted by'),('checklist_revision','Submission revision'),
    ('checklist_verified','Submission validated'),('checklist_submission_history','Submission history'),
]]
SYSTEM_KEYS = {f['field'] for f in METADATA}
EMPLOYEE_TRIGGERS = {'start_checklist','submit_checklist','submit_employee_handover'}


def is_checklist(workflow):
    return workflow['definition'].get('initial_state') == 'Not Started'


def validate_values(fields, values, submitting=False):
    """Validate against the pinned native fields, permitting incomplete drafts."""
    for f in fields:
        value = values.get(f['field'])
        if value not in (None, ''):
            from .custom_fields import _typed
            _typed(f['description'], f, value)
        if value not in (None, '') and f.get('enum_values') and value not in f['enum_values']:
            raise AppError(422, 'Choose a configured answer: ' + f['description'])
        if f.get('type') == 'boolean' and value not in (None, '') and not isinstance(value, bool):
            raise AppError(422, 'Choose a valid acknowledgment')
        if submitting and f.get('required') and (value is None or value is False or not str(value).strip()):
            raise AppError(422, 'Complete ' + f['description'])


def definition(methods, templates):
    employee_forms = [methods[t] for t in CHECKLIST]
    states = []
    for index, name in enumerate(STAGES):
        assigned = 'offboarding_employee_user_id' if index < 2 else 'offboarding_coordinator_id'
        actions = [] if name == 'Completed' else [{'kind':'entity.assign_user','config':{'assignment_type':'user','user_id':'$entity.'+assigned}}]
        # Native audit events feed independent notification records. Their mail
        # actions cannot be cancelled by a later offboarding transition.
        from .offboarding_notifications import TAG
        states.append({'name':name,'order':index+1,'description':TAG,'tags':(['initial'] if index==0 else ['terminal'] if name=='Completed' else []),
                       'method_refs':[{'method_id':m} for m in [methods['Exit administration'],*employee_forms,methods['Clearance verification']]],'on_state_actions':actions})
    required = [dict(f, required=True) for t, fields in CHECKLIST.items() if t!='Employee Information' for f in fields if not f['field'].endswith('_remarks')]
    def transition(key, source, target, label, fields=(), guards=()):
        return dict(key=key,trigger=key,label=label,**{'from':source},to_state=target,required_fields=list(fields),guards=list(guards))
    transitions = [
        transition('start_checklist','Not Started','In Progress','Start checklist'),
        transition('submit_checklist','In Progress','Submitted','Submit checklist',required,[{'type':'field_exact_match','field':'checklist_verified','value':'yes'}]),
        transition('begin_clearance','Submitted','Pending Clearance','Begin clearance'),
        transition('request_checklist_corrections','Submitted','In Progress','Request corrections',[dict(field('change_reason','Reason for corrections','text'),required=True)]),
        transition('reopen_checklist','Pending Clearance','In Progress','Request corrections',[dict(field('change_reason','Reason for corrections','text'),required=True)]),
        transition('complete_offboarding','Pending Clearance','Completed','Finalize offboarding',[dict(field('final_notes','Final review notes','text'),required=True)],
                   [{'type':'field_exact_match','field':k,'value':'yes'} for k in ('departure_verified','clearance_verified')]),
    ]
    # HR can remove access even when paperwork is incomplete. A reason records
    # that exception; no employee acknowledgment or submission is fabricated.
    for name in STAGES[:-1]:
        exception = [dict(field('change_reason','Reason for proceeding before employee submission','text'),required=True)] if name in STAGES[:2] else []
        transitions.append(dict(transition('confirm_departure',name,'Pending Clearance','Confirm departure',fields=exception,guards=[{'type':'field_exact_match','field':'departure_verified','value':'yes'}]),key='departure_'+str(STAGES.index(name))))
    return dict(machine_key='hrms_offboarding',name='Employee offboarding',entity_type='HRMS.Offboarding',entity_schema={'entity_type':'HRMS.Offboarding','fields':[]},initial_state=STAGES[0],states=states,transitions=transitions)
