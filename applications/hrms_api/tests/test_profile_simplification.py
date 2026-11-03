import pytest
from hrms_app.custom_fields import _typed
from hrms_app.errors import AppError
from hrms_app.profile_address import copy_current_address, ADDRESS_PARTS


def address_fields():
    return [{'field': 'permanent_same_as_current'}] + [{'field': prefix + part} for prefix in ('current_', 'permanent_') for part in ADDRESS_PARTS]


def test_address_copy_tracks_edits_and_unchecking_preserves_separate_address():
    fields = address_fields()
    saved = {'permanent_same_as_current': True, 'current_city': 'Pune', 'current_country': 'India'}
    result = copy_current_address(fields, {'current_city': 'Mumbai'}, saved)
    assert result['permanent_city'] == 'Mumbai'
    assert result['permanent_country'] == 'India'
    values = {'permanent_same_as_current': False, 'permanent_city': 'Delhi'}
    assert copy_current_address(fields, values, saved) == values


def test_address_copy_respects_native_form_and_permissions():
    values = {'permanent_same_as_current': True, 'current_city': 'Pune'}
    assert copy_current_address([], values, {}) == values
    fields = address_fields()
    with pytest.raises(AppError):
        copy_current_address(fields[:-1], values, {})
    fields[-1]['read_only'] = True
    with pytest.raises(AppError):
        copy_current_address(fields, values, {})


def test_multi_select_validates_each_value_and_preserves_order():
    field = {'type': 'multi_select', 'enum_values': ['Python', 'SQL']}
    assert _typed('Skills', field, ['Python', 'SQL', 'Python']) == ['Python', 'SQL']
    assert _typed('Skills', field, []) == []
    for value in ('Python', ['Other'], [1], {'Python': True}):
        with pytest.raises(AppError):
            _typed('Skills', field, value)


