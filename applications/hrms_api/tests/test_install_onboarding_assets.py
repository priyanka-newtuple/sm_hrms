from types import SimpleNamespace
import pytest
from hrms_app.errors import AppError
from hrms_app.install_onboarding_assets import install


def test_relationship_created_once_without_changing_forms_or_workflows(monkeypatch):
    monkeypatch.setenv('HRMS_ASSET_EMPLOYEE_RELATION', 'ISSUED_TO')
    rows, writes = [], []
    def call(method, path, **kwargs):
        if path == '/organizations/current': return {'id': 'org'}
        if path == '/entity-types/HRMS.Asset': return {'entity_type_id': 'asset'}
        if path == '/entity-types/HRMS.Employee': return {'entity_type_id': 'employee'}
        assert path == '/entity-types/asset/relations'
        if method == 'POST':
            rows.append(kwargs['json']); writes.append(kwargs['json'])
        return {'items': rows}
    api = SimpleNamespace(org='org', call=call)
    install(api); install(api)
    assert writes == [{'to_entity_type_id': 'employee', 'relation_name': 'ISSUED_TO'}]


def test_disabled_configuration_does_not_call_platform(monkeypatch):
    monkeypatch.setenv('HRMS_ASSET_EMPLOYEE_RELATION', '')
    install(SimpleNamespace(call=lambda *a: pytest.fail('Disabled integration must not write')))


def test_wrong_tenant_fails_before_any_write(monkeypatch):
    monkeypatch.setenv('HRMS_ASSET_EMPLOYEE_RELATION', 'ISSUED_TO')
    api = SimpleNamespace(org='org', call=lambda method, path: {'id': 'other'})
    with pytest.raises(AppError, match='organization mismatch'):
        install(api)
