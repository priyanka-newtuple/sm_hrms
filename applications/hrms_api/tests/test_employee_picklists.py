from copy import deepcopy

from hrms_app.install_employee_picklists import install_employee_picklists
from hrms_app.service import HrmsService
from test_employees import StaffPlatform, hr
from employee_form_fixture import ROUTES


def test_employee_options_follow_native_picklists_and_never_recover_removed_values():
    api = StaffPlatform()
    original = api.call
    choices = [{'value': 'eng', 'label': 'Engineering team'}]
    def call(method, path, **kwargs):
        if path == '/forms/config':
            form = deepcopy(ROUTES[path])
            form['items'][0]['fields'][0]['picklist_id'] = 'departments'
            return form
        if path == '/config/picklists':
            return {'items': [{'id': 'departments', 'options': choices}]}
        return original(method, path, **kwargs)
    api.call = call
    service = HrmsService(api, None, 'newtuple.com')
    options = service.form_options(hr())
    assert options['departments'] == ['eng']
    assert options['department_labels'] == {'eng': 'Engineering team'}
    choices.clear()
    assert service.form_options(hr())['departments'] == []  # not the employee's old Engineering value


class InstallAPI:
    def __init__(self, methods=False):
        self.methods = methods
        self.lists = []
        self.form = deepcopy(ROUTES['/forms/config']['items'][0])
        self.form['fields'][0].pop('enum_values')
        self.fields = [{'id': k, 'library_field_id': k, 'field_key': k, 'settings': {}}
                       for k in ('department', 'designation')]
        self.versions = {}
        self.writes = []
    def records(self, *args):
        return [{'data': {'department': 'Existing department', 'designation': 'Existing title'}}]
    def call(self, method, path, **kwargs):
        if method != 'GET': self.writes.append((method, path))
        if path == '/config/picklists':
            if method == 'GET': return {'items': deepcopy(self.lists)}
            result = {'id': str(len(self.lists)), **kwargs['json']}
            self.lists.append(result)
            return result
        if path == '/method-library/methods': return {'items': [{'method_id': 'm'}] if self.methods else []}
        if path == '/field-library/field-types': return {'items': [{'code': 'select', 'engine_type': 'enum'}]}
        if path == '/method-library/methods/m': return {'fields': deepcopy(self.fields)}
        if path.startswith('/field-library/fields/'):
            key = path.split('/')[3]
            self.versions[key] = kwargs['json']['settings']
            return {'version_id': key}
        if method == 'PATCH':
            field = next(f for f in self.fields if f['id'] == path.split('/')[5])
            field['settings'] = self.versions[kwargs['json']['version_id']]
            return {}
        if path == '/forms/config': return {'items': [deepcopy(self.form)]}
        if method == 'PUT': self.form['fields'] = kwargs['json']['fields']; return {}
        raise AssertionError(path)


def test_legacy_install_preserves_existing_values_and_does_not_refill_empty_list():
    api = InstallAPI()
    install_employee_picklists(api)
    assert any(o['value'] == 'Existing department' for o in api.lists[0]['options'])
    api.lists[0]['options'] = []
    writes = len(api.writes)
    install_employee_picklists(api)
    assert len(api.writes) == writes
    assert api.lists[0]['options'] == []


def test_method_fields_receive_native_bindings_once():
    api = InstallAPI(methods=True)
    install_employee_picklists(api)
    assert all(f['settings']['picklist_id'] for f in api.fields)
    writes = len(api.writes)
    install_employee_picklists(api)
    assert len(api.writes) == writes
