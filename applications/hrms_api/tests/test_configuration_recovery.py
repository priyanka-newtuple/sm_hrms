from copy import deepcopy

import pytest

from hrms_app.configuration_package import ConfigurationError, digest
from hrms_app.configuration_promotion import inspection, resume_reviewed
from test_configuration_promotion import FakeNative, MemoryJournal, obj, package


def checkpoint():
    p = package(obj(), obj('Second'))
    native = FakeNative({'Departments': obj()})
    journal = MemoryJournal({'status': 'failed', 'package_checksum': digest(p),
                             'baseline': {}, 'completed': ['Departments'], 'pending': None})
    review, _, _ = inspection(native, p, {'baseline': {}})
    return p, native, journal, review


def test_recovery_only_writes_remaining_and_retains_history():
    p, native, journal, review = checkpoint()
    result = resume_reviewed(native, p, review, journal)
    assert result['status'] == 'applied'
    assert native.writes == ['Second']
    assert result['recovery_history'][0]['completed'] == ['Departments']


@pytest.mark.parametrize('change', ['pending', 'package', 'completed', 'stale', 'tenant'])
def test_recovery_rejects_uncertain_or_changed_checkpoint_without_writes(change):
    p, native, journal, review = checkpoint()
    if change == 'pending':
        journal.state['pending'] = {'key': 'Second'}
    elif change == 'package':
        journal.state['package_checksum'] = 'different'
    elif change == 'completed':
        native.rows['Departments'] = obj(options=['manual change'])
        review, _, _ = inspection(native, p, {'baseline': {}})
    elif change == 'stale':
        native.rows['Second'] = obj('Second', options=['manual change'])
    else:
        review = deepcopy(review)
        review['organization'] = 'another-tenant'
    with pytest.raises(ConfigurationError):
        resume_reviewed(native, p, review, journal)
    assert not native.writes
    assert not journal.writes


def test_recovery_fully_applied_checkpoint_is_verified():
    p, native, journal, review = checkpoint()
    native.rows['Second'] = obj('Second')
    review, _, _ = inspection(native, p, {'baseline': {}})
    assert resume_reviewed(native, p, review, journal)['status'] == 'applied'
    assert not native.writes
