import pytest

from hrms_app import custom_fields


@pytest.fixture(autouse=True)
def no_custom_fields(request, monkeypatch):
    """Fake platforms do not serve form configuration: screens see no custom fields unless a test
    marked `custom_fields` supplies them."""
    custom_fields._keys.clear()
    if 'custom_fields' not in request.keywords:
        monkeypatch.setattr(custom_fields, 'custom_fields', lambda platform, entity_type: [])


def pytest_configure(config):
    config.addinivalue_line('markers', 'custom_fields: the test supplies configured custom fields itself')
