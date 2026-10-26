"""Resolve tenant-native onboarding form identities without copying local UUIDs."""
import os

from .errors import AppError

FORMS = {
    'HRMS_EMPLOYEE_APPROVAL_FORM_ID': 'Employee Account Approval',
    'HRMS_EMPLOYEE_PROFILE_FORM_ID': 'Employee Profile Completion',
    'HRMS_EMPLOYEE_SIGNOFF_FORM_ID': 'Employee Final HR Sign-off',
    'HRMS_EMPLOYEE_COMPLETE_FORM_ID': 'Employee Details',
}


def resolve(platform):
    methods, offset = [], 0
    while True:
        page = platform.call('GET', '/method-library/methods', params={'limit': 200, 'offset': offset})
        if page.get('organization_id') != platform.org:
            raise AppError(502, 'Onboarding form organization mismatch')
        methods.extend(page['items'])
        if len(methods) >= page['total']:
            break
        if not page['items']:
            raise AppError(502, 'Incomplete onboarding form listing')
        offset += len(page['items'])
    result = {}
    for variable, name in FORMS.items():
        explicit = os.getenv(variable)
        matches = [m for m in methods if m['method_id'] == explicit and not m.get('is_archived')] if explicit else [m for m in methods if m['name'] == name and not m.get('is_archived')]
        if len(matches) != 1:
            raise AppError(409, f'Configure one native onboarding form: {name}')
        result[variable] = matches[0]['method_id']
    return result


def initialize(platform):
    bindings = resolve(platform)
    # Existing consumers use these form IDs for own-profile and sign-off checks.
    # Publish only after every binding is validated; partial configuration is unsafe.
    os.environ.update(bindings)
    return bindings
