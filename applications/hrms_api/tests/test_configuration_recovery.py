from copy import deepcopy

import pytest

from hrms_app.configuration_package import ConfigurationError, digest
from hrms_app.configuration_promotion import inspection, resume_reviewed
from hrms_app.configuration_native import NativeConfiguration
from types import SimpleNamespace
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


def test_reviewed_corrective_package_checks_original_completed_values():
    p, native, journal, _ = checkpoint()
    corrected = package(obj(options=['corrected']), obj('Second'))
    review, _, _ = inspection(native, corrected, {'baseline': {}})
    result = resume_reviewed(native, corrected, review, journal, original_package=p)
    assert result['status'] == 'applied'
    assert native.writes == ['Departments', 'Second']


@pytest.mark.parametrize('version,changed', [(0, False), (1, False), (0, True)])
def test_pending_owned_draft_requires_exact_unpublished_review(version, changed):
    wf = {'key': 'workflow:Employee', 'kind': 'workflow', 'match': 'Employee',
          'payload': {'definition': {'name': 'Employee'}}}
    p = package(wf)
    native = FakeNative()
    draft = {'id': 'draft-id', 'version': version, 'machine_name': 'family'}
    native.get = lambda _: draft
    journal = MemoryJournal({'status': 'failed', 'package_checksum': digest(p), 'baseline': {},
                             'completed': [], 'pending': {'key': wf['key'], 'draft_id': 'draft-id',
                                                          'machine_name': 'family', 'before': digest(None)}})
    review, _, _ = inspection(native, p, {'baseline': {}})
    checksum = 'stale' if changed else digest(draft)
    if version or changed:
        with pytest.raises(ConfigurationError):
            resume_reviewed(native, p, review, journal, draft_review=checksum)
        assert not journal.writes and not native.writes
    else:
        result = resume_reviewed(native, p, review, journal, draft_review=checksum)
        assert result['status'] == 'applied'
        assert native.recovery_drafts[wf['key']]['id'] == 'draft-id'


def test_adapter_reuses_only_exact_reviewed_draft():
    calls = []
    native = NativeConfiguration(SimpleNamespace(org='tenant-a', call=lambda *a, **k: calls.append(a)))
    draft = {'id': 'draft-id', 'version': 0, 'machine_name': 'family'}
    native.get = lambda _: deepcopy(draft)
    native.recovery_drafts = {'workflow:Employee': {'id': 'draft-id', 'checksum': digest(draft)}}
    item = {'kind': 'workflow', 'key': 'workflow:Employee', 'match': 'Employee'}
    native.write(item, {'definition': {'name': 'Employee'}}, {}, lambda _: None)
    assert calls == [('POST', '/workflow-state-machines/draft-id/publish')]
    calls.clear()
    draft['version'] = 1
    with pytest.raises(ConfigurationError):
        native.write(item, {'definition': {'name': 'Employee'}}, {}, lambda _: None)
    assert not calls


@pytest.mark.parametrize('changed', [False, True])
def test_pending_intent_can_resume_only_when_native_object_is_unchanged(changed):
    p, native, journal, _ = checkpoint()
    journal.state['pending'] = {'key': 'Second', 'before': digest(None)}
    if changed:
        native.rows['Second'] = obj('Second', options=['unexpected'])
    review, _, _ = inspection(native, p, journal.read())
    if changed:
        with pytest.raises(ConfigurationError, match='Pending configuration changed'):
            resume_reviewed(native, p, review, journal)
        assert not journal.writes and not native.writes
    else:
        assert resume_reviewed(native, p, review, journal)['status'] == 'applied'
        assert native.writes == ['Second']


@pytest.mark.parametrize('changed', [False, True])
def test_published_pending_workflow_requires_exact_reviewed_payload_and_identity(changed):
    wf = {'key': 'workflow:Employee', 'kind': 'workflow', 'match': 'Employee',
          'payload': {'definition': {'name': 'Employee'}}}
    p = package(wf)
    native = FakeNative({wf['key']: wf})
    journal = MemoryJournal({'status': 'failed', 'package_checksum': digest(p), 'baseline': {},
        'completed': [], 'pending': {'key': wf['key'], 'draft_id': wf['key'], 'before': digest(None)}})
    if changed: native.rows[wf['key']]['payload']['definition']['name'] = 'Changed'
    review, _, _ = inspection(native, p, journal.read())
    if changed:
        with pytest.raises(ConfigurationError): resume_reviewed(native, p, review, journal)
        assert not journal.writes
    else:
        assert resume_reviewed(native, p, review, journal)['status'] == 'applied'
    assert not native.writes


@pytest.mark.parametrize('changed', [False, True])
def test_native_publication_with_separate_immutable_row_checks_retained_draft(changed):
    wf = {'key': 'workflow:Employee', 'kind': 'workflow', 'match': 'Employee',
          'payload': {'definition': {'name': 'Employee'}}}
    p = package(wf)
    native = FakeNative({wf['key']: wf})
    native.read = lambda item: (deepcopy(wf['payload']), {'id': 'published-row', 'machine_name': 'family'})
    draft = {'id': 'draft-row', 'version': 0, 'machine_name': 'family'}
    native.get = lambda path: deepcopy(draft)
    journal = MemoryJournal({'status': 'failed', 'package_checksum': digest(p), 'baseline': {},
        'completed': [], 'pending': {'key': wf['key'], 'draft_id': 'draft-row', 'machine_name': 'family', 'before': digest(None)}})
    review, _, _ = inspection(native, p, journal.read())
    if changed:
        with pytest.raises(ConfigurationError): resume_reviewed(native, p, review, journal, draft_review='stale')
        assert not journal.writes
    else:
        assert resume_reviewed(native, p, review, journal, draft_review=digest(draft))['status'] == 'applied'
    assert not native.writes
