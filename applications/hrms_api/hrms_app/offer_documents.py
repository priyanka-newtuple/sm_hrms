"""Offer documents: native templates/records/files, with HRMS rendering orchestration."""
import hashlib
import html
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import UUID

from .errors import AppError
from .offers import is_offer
from .policy import require

OUTPUT_FIELDS = {'offer_pdf', 'offer_document_hash', 'offer_template_hash', 'offer_revision'}
TOKEN = re.compile(r'{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def input_values(data):
    return {k: v for k, v in data.items() if k not in OUTPUT_FIELDS}


def money(value):
    number = Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    whole, fraction = f'{number:.2f}'.split('.')
    tail, head = whole[-3:], whole[:-3]
    groups = []
    while head:
        groups.insert(0, head[-2:]); head = head[:-2]
    return ','.join(groups + [tail]) + ('.' + fraction if fraction != '00' else '')


def letter_values(data):
    values = dict(data)
    # FR-38 keeps the candidate/employee-compatible field names. Resolve the
    # letter placeholders without asking HR to enter the same information twice.
    if 'first_name' in data:
        values['candidate_full_name'] = ' '.join(str(data.get(k) or '').strip() for k in ('first_name', 'middle_name', 'last_name') if data.get(k))
        values['candidate_first_name'] = data.get('first_name', '')
    if 'personal_email' in data:
        values['candidate_email'] = data['personal_email']
    if 'current_address_line_1' in data:
        values['candidate_address'] = ', '.join(str(data.get(k) or '').strip() for k in ('current_address_line_1', 'current_address_line_2', 'current_city', 'current_state', 'current_postal_code', 'current_country') if data.get(k))
    try:
        annual = Decimal(str(data.get('ctc', data.get('annual_ctc', 0))))
        if not annual.is_finite() or annual <= 0:
            raise ValueError()
        ratios = [Decimal(str(data.get(key + '_percent', default))) for key, default in
                  [('basic', 50), ('hra', 12.5), ('special', 30), ('lta', 7.5)]]
        if any(not r.is_finite() or r < 0 for r in ratios) or sum(ratios) != 100:
            raise AppError(422, 'Salary component percentages must total 100')
        parts = [(annual * r / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) for r in ratios]
        parts[2] += annual - sum(parts)
        monthly = [(p / 12).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) for p in parts]
        monthly[2] += (annual / 12).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) - sum(monthly)
        for key, yearly, month in zip(['basic', 'hra', 'special', 'lta'], parts, monthly):
            values[key + '_yearly'] = money(yearly)
            values[key + '_monthly'] = money(month)
        values['annual_ctc_formatted'] = money(annual)
        values['monthly_total'] = money(sum(monthly))
        bonus = Decimal(str(data.get('joining_bonus') or 0))
        if not bonus.is_finite() or bonus < 0:
            raise ValueError()
        values['joining_bonus_formatted'] = money(bonus)
        values['joining_bonus_clause'] = (
            f"Joining Bonus: You will receive a joining bonus of INR {money(bonus)}, in addition to the annual compensation above, "
            f"{data.get('bonus_payment_terms') or 'with the first payroll that you are part of'}, subject to a minimum tenure of "
            f"{data.get('bonus_tenure_months') or 6} months. If the employee leaves or is terminated before completing this tenure, "
            'this bonus will be recovered or adjusted against the final settlement.' if bonus else '')
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise AppError(422, 'Enter valid positive annual compensation and non-negative bonus amounts') from exc
    for key in ('offer_date', 'joining_date'):
        try:
            values[key + '_formatted'] = date.fromisoformat(str(data[key])[:10]).strftime('%d %B %Y')
        except (KeyError, ValueError) as exc:
            raise AppError(422, f'Enter a valid {key.replace("_", " ")}') from exc
    return values


def render_letter(template, data):
    values = letter_values(data)
    missing = sorted({k for k in TOKEN.findall(template) if k not in values})
    if missing:
        raise AppError(422, 'Template fields are missing: ' + ', '.join(missing))
    rendered = TOKEN.sub(lambda m: html.escape(str(values[m.group(1)] if values[m.group(1)] is not None else '')), template)
    if '{{' in rendered or '{%' in rendered:
        raise AppError(422, 'Use simple {{field_name}} placeholders in the native template')
    return rendered


def pdf_bytes(markup):
    from weasyprint import HTML, default_url_fetcher
    def fetch(url, *args, **kwargs):
        # Templates cannot fetch network resources or read server files.
        if url.startswith('data:image/') and len(url) < 2_000_000:
            return default_url_fetcher(url, *args, **kwargs)
        raise ValueError('Only embedded template images are supported')
    return HTML(string=markup, url_fetcher=fetch).write_pdf()


class OfferDocuments:
    def __init__(self, platform, journal):
        self.platform, self.journal = platform, journal

    def call(self, actor, method, path, **kwargs):
        require(actor, 'cockpit:view')
        return self.platform.request(method, path, token=actor.token, **kwargs)

    def templates(self, actor):
        rows = self.call(actor, 'GET', '/email-templates')['items']
        return [t for t in rows if t.get('organization_id') == actor.organization_id and is_offer(t.get('entity_type'))]

    def workflow(self, actor, machine):
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', machine):
            raise AppError(400, 'Invalid workflow')
        w = self.call(actor, 'GET', f'/workflow-state-machines/{machine}/active')
        if not is_offer(w.get('entity_type')) or w.get('organization_id') != actor.organization_id:
            raise AppError(403, 'Select an offer workflow in your organization')
        return w

    def config(self, actor, machine):
        w = self.workflow(actor, machine)
        return {'workflow': w, 'fields': self.fields(actor, w),
                'templates': [{'template_id': t['template_id'], 'name': t['name']} for t in self.templates(actor)]}

    def fields(self, actor, workflow):
        # Defaults are native Field Library settings, omitted by the compiled
        # workflow schema. Only use settings from the workflow's pinned version.
        settings = {}
        seen = set()
        for method in workflow['definition'].get('method_schemas', []):
            if method['method_id'] in seen:
                continue
            seen.add(method['method_id'])
            detail = self.call(actor, 'GET', '/method-library/methods/' + method['method_id'])
            if detail['version']['version_id'] == method.get('version_id'):
                settings.update({f['field_key']: f.get('settings', {}) for f in detail['fields']})
        result = []
        for field in workflow['definition']['entity_schema']['fields']:
            extra = settings.get(field['field'], {})
            item = {**field, **{k: extra[k] for k in ('default', 'document_config') if k in extra}}
            if field['field'] in ('joining_date', 'offer_date') and field['type'] == 'datetime':
                item['type'] = 'date'
            result.append(item)
        return result

    def detail(self, actor, entity_id):
        UUID(entity_id)
        r = self.call(actor, 'GET', f'/entity-records/{entity_id}/with-states')
        entity = r['entity']
        if entity['organization_id'] != actor.organization_id:
            raise AppError(404, 'Offer not found')
        states = r.get('states', [])
        if len(states) != 1:
            raise AppError(409, 'Offer must have one workflow enrollment')
        state = states[0]
        w = self.call(actor, 'GET', f"/workflow-state-machines/{state['workflow_id']}")
        if not is_offer(w.get('entity_type')) or w.get('organization_id') != actor.organization_id:
            raise AppError(403, 'This is not an offer')
        available = self.call(actor, 'GET', f'/entities/{entity_id}/transitions/available', params={'workflow_id': state['workflow_id']})
        data = entity.get('data', {})
        valid = bool(data.get('offer_pdf')) and data.get('offer_document_hash') == digest({'values': input_values(data), 'template': data.get('offer_template_hash')})
        return {'entity_id': entity_id, 'values': data, 'workflow': w, 'state': state['current_state'],
                'fields': self.fields(actor, w), 'editable': state['current_state'] == w['definition']['initial_state'],
                'document_current': valid, 'actions': available.get('available_transitions', []),
                'templates': [{'template_id': t['template_id'], 'name': t['name']} for t in self.templates(actor)]}

    def save(self, actor, payload, entity_id=None):
        with self.journal.lock(actor.organization_id) as db:
            op = self.journal.operation(db, actor, payload['idempotency_key'], {'action': 'offer-save', 'entity': entity_id, 'payload': payload})
            if op.result:
                return op.result
            if entity_id:
                current = self.detail(actor, entity_id)
                if not current['editable']:
                    raise AppError(409, 'Return the offer to its creation state before editing')
                w = current['workflow']
                if payload.get('expected_hash') != digest(current['values']):
                    raise AppError(409, 'This offer changed. Reload before saving')
            else:
                w = self.workflow(actor, payload['machine_name'])
            fields = w['definition']['entity_schema']['fields']
            allowed = {f['field'] for f in fields if f['field'] not in OUTPUT_FIELDS and not f.get('read_only')}
            allowed.add('identifier')
            values = payload.get('values', {})
            if set(values) - allowed:
                raise AppError(422, 'Only configured offer inputs may be saved')
            for f in fields:
                if f['field'] in allowed and f.get('required') and values.get(f['field']) in (None, ''):
                    raise AppError(422, 'Complete ' + (f.get('description') or f['field']))
            if not any(t['template_id'] == values.get('offer_template_id') for t in self.templates(actor)):
                raise AppError(422, 'Choose an offer letter template')
            letter_values(values)
            if entity_id:
                self.call(actor, 'PUT', f'/entity-records/{entity_id}', json={'data': {**values, 'offer_document_hash': '', 'offer_pdf': []}})
            else:
                if not op.progress.get('entity_id'):
                    kind = self.call(actor, 'GET', '/entity-types/' + w['entity_type'])
                    result = self.call(actor, 'POST', '/entity-records', json={'entity_type_id': kind['entity_type_id'], 'data': values})
                    op.checkpoint(entity_id=result['entity_id'])
                entity_id = op.progress['entity_id']
                self.call(actor, 'POST', f"/workflow-state-machines/{w['machine_name']}/enrollments", json={'entity_id': entity_id})
            op.finish({'entity_id': entity_id})
            return op.result

    def generate(self, actor, entity_id, payload):
        with self.journal.lock(actor.organization_id) as db:
            op = self.journal.operation(db, actor, payload['idempotency_key'], {'action': 'offer-pdf', 'entity': entity_id, 'payload': payload})
            if op.result:
                return op.result
            item = self.detail(actor, entity_id)
            if not item['editable']:
                raise AppError(409, 'Only an offer in its creation state can be regenerated')
            data = item['values']
            if payload.get('expected_hash') != digest(data):
                raise AppError(409, 'The offer changed. Reload before generating')
            template = next((t for t in self.templates(actor) if t['template_id'] == data.get('offer_template_id')), None)
            if not template:
                raise AppError(422, 'The selected template is unavailable')
            template_hash = digest(template['body_html'])
            fingerprint = digest({'values': input_values(data), 'template': template_hash})
            if item['document_current'] and data.get('offer_template_hash') == template_hash:
                op.finish({'entity_id': entity_id}); return op.result
            revision = int(data.get('offer_revision') or 0) + 1
            if not op.progress.get('file_id'):
                content = pdf_bytes(render_letter(template['body_html'], data))
                uploaded = self.call(actor, 'POST', '/filehandler/upload',
                    params={'type_id': 'generic_document', 'owner_entity_id': entity_id,
                            'metadata': json.dumps({'field_key': 'offer_pdf', 'offer_revision': revision, 'offer_document_hash': fingerprint, 'template_id': template['template_id']})},
                    files={'file': (f'Offer-{entity_id[:8]}-v{revision}.pdf', content, 'application/pdf')})
                op.checkpoint(file_id=uploaded['file_id'])
            latest = self.detail(actor, entity_id)
            if not latest['editable'] or digest(latest['values']) != digest(data):
                raise AppError(409, 'The offer changed during generation. Reload and generate a new preview')
            self.call(actor, 'PUT', f'/entity-records/{entity_id}', json={'data': {'offer_pdf': [op.progress['file_id']],
                'offer_document_hash': fingerprint, 'offer_template_hash': template_hash, 'offer_revision': revision}})
            self.journal.audit(db, actor, 'offer.document.generated', entity_id, payload['idempotency_key'])
            op.finish({'entity_id': entity_id}); return op.result

    def transition(self, actor, entity_id, payload):
        with self.journal.lock(actor.organization_id) as db:
            op = self.journal.operation(db, actor, payload['idempotency_key'], {'action': 'offer-transition', 'entity': entity_id, 'payload': payload})
            if op.result:
                return op.result
            item = self.detail(actor, entity_id)
            if payload.get('expected_hash') != digest(item['values']):
                raise AppError(409, 'The offer changed. Reload before continuing')
            if not item['document_current']:
                raise AppError(422, 'Generate a current PDF preview before continuing')
            # A template edit after drafting also requires regenerating before submission.
            if item['editable']:
                template = next((t for t in self.templates(actor) if t['template_id'] == item['values'].get('offer_template_id')), None)
                if not template or digest(template['body_html']) != item['values'].get('offer_template_hash'):
                    raise AppError(409, 'The template changed. Generate a new preview')
            if payload['trigger'] not in {a['trigger'] for a in item['actions']}:
                raise AppError(403, 'This transition is not available')
            result = self.call(actor, 'POST', f'/entities/{entity_id}/transitions', json={
                'entity_id': entity_id, 'workflow_id': item['workflow']['id'], 'trigger': payload['trigger'],
                'idempotency_key': payload['idempotency_key']})
            op.finish(result)
            return result

    def download(self, actor, entity_id):
        item = self.detail(actor, entity_id)
        if not item['document_current']:
            raise AppError(409, 'Generate a current offer PDF first')
        file_id = item['values']['offer_pdf'][0]
        UUID(file_id)
        response = self.platform.http.get(f'filehandler/{file_id}/download', headers={'Authorization': f'Bearer {actor.token}'})
        if response.status_code != 200:
            raise AppError(response.status_code, 'Unable to open the offer PDF')
        return response.content
