from contextlib import nullcontext
from copy import deepcopy

import pytest

from hrms_app.errors import AppError
from hrms_app.offer_documents import OfferDocuments, digest, input_values, letter_values, render_letter
from hrms_app.platform import Actor
from hrms_app.policy import permission_key


def values():
    return dict(annual_ctc=1200000, joining_bonus=0, offer_date='2026-10-19', joining_date='2026-11-01',
                candidate_full_name='<script>Test</script>', offer_template_id='template')


def test_salary_and_optional_bonus():
    result = letter_values(values())
    assert result['basic_yearly'] == '6,00,000'
    assert result['monthly_total'] == '1,00,000'
    assert result['joining_bonus_clause'] == ''
    result = letter_values({**values(), 'joining_bonus': 50000})
    assert '50,000' in result['joining_bonus_clause']
    assert 'in addition' in result['joining_bonus_clause']


def test_fr38_candidate_fields_supply_letter_without_duplicate_inputs():
    data = {**values(), 'first_name': 'Test', 'middle_name': 'Middle', 'last_name': 'Candidate',
            'personal_email': 'test@example.com', 'current_address_line_1': '1 Sample Road',
            'current_city': 'Pune', 'current_postal_code': '411001', 'ctc': '2400000'}
    result = letter_values(data)
    assert result['candidate_full_name'] == 'Test Middle Candidate'
    assert result['candidate_first_name'] == 'Test'
    assert result['candidate_email'] == 'test@example.com'
    assert result['candidate_address'] == '1 Sample Road, Pune, 411001'
    assert result['annual_ctc_formatted'] == '24,00,000'
    assert result['monthly_total'] == '2,00,000'


@pytest.mark.parametrize('change', [{'annual_ctc': -1}, {'annual_ctc': 'NaN'}, {'basic_percent': 60}, {'joining_bonus': -1}, {'offer_date': 'invalid'}])
def test_invalid_compensation_or_dates(change):
    with pytest.raises(AppError):
        letter_values({**values(), **change})


def test_template_escapes_hr_values_and_rejects_unknown_placeholders():
    assert render_letter('{{candidate_full_name}}', values()) == '&lt;script&gt;Test&lt;/script&gt;'
    with pytest.raises(AppError, match='missing'):
        render_letter('{{unknown}}', values())


class Op:
    result = None
    def __init__(self): self.progress = {}
    def checkpoint(self, **kw): self.progress.update(kw)
    def finish(self, result): self.result = result


class Journal:
    def __init__(self): self.ops = {}
    def lock(self, org): return nullcontext(None)
    def operation(self, db, actor, key, payload): return self.ops.setdefault(key, Op())
    def audit(self, *args): pass


@pytest.fixture
def setup():
    actor = Actor('hr', 'org', 'human', frozenset(), frozenset({permission_key('org', 'cockpit:view')}))
    service = OfferDocuments(None, Journal())
    data = values()
    data.update(offer_pdf=['file'], offer_template_hash=digest('letter'))
    data['offer_document_hash'] = digest({'values': input_values(data), 'template': data['offer_template_hash']})
    item = {'values': data, 'editable': True, 'document_current': True, 'workflow': {'id': 'workflow'}, 'actions': [{'trigger': 'review'}]}
    service.detail = lambda *args: deepcopy(item)
    service.templates = lambda *args: [{'template_id': 'template', 'body_html': 'letter'}]
    calls = []
    def call(*args, **kw): calls.append((args, kw)); return {'state': 'Review'}
    service.call = call
    return service, actor, item, calls


def test_transition_is_idempotent_and_passes_native_trigger(setup):
    service, actor, item, calls = setup
    payload = {'expected_hash': digest(item['values']), 'trigger': 'review', 'idempotency_key': 'test-key'}
    assert service.transition(actor, 'id', payload) == {'state': 'Review'}
    item['actions'] = []
    assert service.transition(actor, 'id', payload) == {'state': 'Review'}
    assert len(calls) == 1
    assert calls[0][1]['json']['workflow_id'] == 'workflow'


@pytest.mark.parametrize('reason', ['stale-data', 'missing-pdf', 'template-changed', 'unavailable-trigger'])
def test_transition_rejects_stale_preview_and_invalid_actions(setup, reason):
    service, actor, item, calls = setup
    payload = {'expected_hash': digest(item['values']), 'trigger': 'review', 'idempotency_key': 'test-key'}
    if reason == 'stale-data': item['values']['annual_ctc'] = 1
    if reason == 'missing-pdf': item['document_current'] = False
    if reason == 'template-changed': service.templates = lambda *args: [{'template_id': 'template', 'body_html': 'changed'}]
    if reason == 'unavailable-trigger': item['actions'] = []
    with pytest.raises(AppError): service.transition(actor, 'id', payload)
    assert not calls


def test_review_offer_cannot_be_edited_or_regenerated(setup):
    service, actor, item, calls = setup
    item['editable'] = False
    with pytest.raises(AppError): service.save(actor, {'idempotency_key': 'save-test'}, 'id')
    with pytest.raises(AppError): service.generate(actor, 'id', {'idempotency_key': 'pdf-test'})
    assert not calls


def test_human_token_and_tenant_boundary():
    class Platform:
        def request(self, method, path, token, **kw):
            assert token == 'human'
            return {'organization_id': 'other', 'entity_type': 'hrms_offer'}
    actor = Actor('hr', 'org', 'human', frozenset(), frozenset({permission_key('org', 'cockpit:view')}))
    with pytest.raises(AppError): OfferDocuments(Platform(), None).workflow(actor, 'offers')
    denied = Actor('hr', 'org', 'human', frozenset(), frozenset())
    with pytest.raises(AppError): OfferDocuments(Platform(), None).workflow(denied, 'offers')
