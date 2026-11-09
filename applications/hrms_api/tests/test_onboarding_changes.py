"""Creating an employee never creates or reassigns legacy onboarding steps."""
from hrms_app.service import HrmsService
from test_employee_access import Journal as AccessJournal
from test_employee_access import ProvisioningPlatform, employee_request
from test_performance import actor


def staff(platform, key, code, role, manager=None):
    platform.rows[key] = dict(entity_id=key, kind='HRMS.Employee', data=dict(
        first_name=key.title(), last_name='Staff', employee_code=code, platform_user_id=f'{key}-user',
        hrms_role=role, employment_status='active', reports_to_employee_code=manager))


def test_employee_creation_preserves_existing_steps_without_creating_new_ones():
    p = ProvisioningPlatform(existing=True)
    for key, code, role in (('busy', 'OA1', 'hrms_office_admin'), ('free', 'OA2', 'hrms_office_admin'),
                            ('lead', 'M1', 'hrms_manager'), ('people', 'HR1', 'hrms_hr_full')):
        staff(p, key, code, role)
    p.rows['old-step'] = dict(entity_id='old-step', kind='HRMS.OnboardingStep', data=dict(case_id='another-hire', sequence=1, assigned_to='busy-user'))
    accounts = p.users()
    p.users = lambda: accounts + [dict(id=f'{k}-user', status='active', role=None) for k in ('busy', 'free', 'lead', 'people')]
    result = HrmsService(p, AccessJournal(), 'newtuple.com').create_employee(
        actor('hr', 'hrms_hr_full'), employee_request(reports_to_entity_id='lead'))
    owners = {r['data']['sequence']: r['data']['assigned_to'] for r in p.rows.values()
              if r['kind'] == 'HRMS.OnboardingStep' and r['entity_id'] != 'old-step'}
    assert result['account_status'] == 'pending'
    assert owners == {}
    assert p.rows['old-step']['data']['assigned_to'] == 'busy-user'
