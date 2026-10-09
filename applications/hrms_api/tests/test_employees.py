from hrms_app.platform import Actor
from hrms_app.policy import capabilities
from hrms_app.service import HrmsService
from test_onboarding import Journal
from test_onboarding import Platform as OnboardingPlatform


def actor(user_id, role):
    return Actor(user_id, 'org', 'human', frozenset({role}), frozenset())


class DirectoryPlatform:
    """One employee created as a standard employee whose account was later made Finance in Settings."""
    org = 'org'

    def records(self, kind, fields):
        if kind != 'HRMS.Employee':
            return []
        return [dict(entity_id='e1', data=dict(first_name='Fin', last_name='Person', employee_code='E1',
                                               work_email='fin@newtuple.com', employment_status='active',
                                               platform_user_id='u1', hrms_role='hrms_employee'))]

    def users(self):
        return [dict(id='u1', role='hrms_finance', status='active', auth_type='local', organization_id='org')]

    def states(self, machine):
        return {}

    def call(self, method, path, **kwargs):
        assert path == '/roles/users/u1/roles'
        return [dict(role_name='hrms_finance', organization_id='org')]


def test_hr_who_assigns_roles_can_add_office_admin_and_finance_staff():
    service = HrmsService(DirectoryPlatform(), None, 'newtuple.com')
    assert {'hrms_office_admin', 'hrms_finance'} <= set(service.form_options(actor('hr', 'hrms_hr_full'))['roles'])
    assert service.form_options(actor('hr', 'hrms_hr_basic'))['roles'] == ['hrms_employee']


def test_the_directory_shows_the_accounts_current_role():
    rows = HrmsService(DirectoryPlatform(), None, 'newtuple.com').directory(actor('hr', 'hrms_hr_full'))
    assert [(r['entity_id'], r['role']) for r in rows] == [('e1', 'hrms_finance')]


def test_onboarding_cases_need_onboarding_view_not_directory_read():
    service = HrmsService(OnboardingPlatform(), Journal(), 'newtuple.com')
    assert service.onboarding(actor('viewer-user', 'viewer')) == []        # viewer reads the directory only
    assert len(service.onboarding(actor('hr-user', 'hrms_hr_basic'))) == 1
    assert len(service.onboarding(actor('owner', 'hrms_employee'))) == 1   # a step owner still sees their case


def test_the_tenant_admin_can_activate_the_employees_it_creates():
    caps = capabilities(actor('admin-user', 'admin'))
    assert {'employee:create', 'employee:activate'} <= caps
