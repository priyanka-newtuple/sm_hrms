"""Tenant-scoped asset inventory and issuance; native records/workflows own the state."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .asset_catalog import ASSET
from .custom_fields import _typed
from .errors import AppError
from .form_config import configured_form
from .form_values import editable_values
from .policy import capabilities, require


class AssetCommand(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['create', 'edit', 'issue']
    data: dict = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=8, max_length=128)


ISSUE_FIELDS = {'issued_employee_id', 'issued_date', 'issued_by', 'issue_note'}
INTERNAL = {'identifier', 'hrms_operation_key'}


class AssetService:
    def __init__(self, service):
        self.service = service
        self.platform, self.journal = service.platform, service.journal

    def rows(self):
        fields = [f['field'] for f in configured_form(self.platform, ASSET)['fields']]
        return self.platform.records(ASSET, list(dict.fromkeys([*fields, *INTERNAL])))

    def board(self, actor):
        if not {'asset:view', 'asset:manage'} & capabilities(actor):
            raise AppError(403, 'Asset access is required')
        manager = 'asset:manage' in capabilities(actor)
        employees = self.service.employees()
        own = {r['entity_id'] for r in employees if r['data'].get('platform_user_id') == actor.user_id}
        states = self.platform.states('hrms_asset')
        names = {r['entity_id']: ' '.join(str(r['data'].get(k, '')) for k in ('first_name', 'last_name')).strip() for r in employees}
        items = []
        for row in self.rows():
            data = row['data']
            if not manager and (data.get('issued_employee_id') not in own or states.get(row['entity_id']) != 'issued'):
                continue
            state = states.get(row['entity_id'])
            actions = []
            if manager:
                actions.append('edit')
                if state == 'available' and not data.get('issued_employee_id'):
                    available = self.platform.call('GET', f"/entities/{row['entity_id']}/transitions/available")
                    if any(t['trigger'] == 'issue' or t.get('to_state') == 'issued' for t in available.get('available_transitions', [])):
                        actions.append('issue')
            # Employees see issuance details, never private inventory notes or custom fields.
            visible = {k: v for k, v in data.items() if k not in INTERNAL} if manager else {
                k: data.get(k) for k in ('asset_tag', 'asset_name', 'asset_category', 'serial_number', 'manufacturer', 'model', 'issued_date', 'issue_note')}
            items.append({'id': row['entity_id'], 'data': visible, 'state': state or 'not_started',
                'employee_name': names.get(data.get('issued_employee_id'), ''), 'actions': actions})
        return {'items': items, 'can_manage': manager, 'employees': [
            {'id': r['entity_id'], 'label': names[r['entity_id']]} for r in employees
            if manager and r['data'].get('employment_status') == 'active']}

    def inventory_data(self, incoming, previous):
        fields = {f['field']: f for f in configured_form(self.platform, ASSET)['fields']}
        allowed = set(fields) - ISSUE_FIELDS - INTERNAL
        if set(incoming) - allowed:
            raise AppError(422, 'Only configured inventory fields can be edited')
        result = dict(previous)
        for key in allowed:
            field = fields[key]
            value = incoming.get(key, previous.get(key))
            if isinstance(value, str):
                value = value.strip()
            if field.get('read_only') and value != previous.get(key):
                raise AppError(422, f'{key} is read-only')
            if value in (None, ''):
                if field.get('required'):
                    raise AppError(422, f'{key} is required')
                result.pop(key, None)
            else:
                if field.get('type') == 'enum' and value not in (field.get('enum_values') or []):
                    raise AppError(422, f'{key} must be one of the configured picklist options')
                result[key] = _typed(key, field, value)
        if not result.get('asset_tag') or not result.get('asset_name'):
            raise AppError(422, 'Asset tag and name are required')
        if result.get('purchase_date') and result.get('warranty_expiry') and result['warranty_expiry'] < result['purchase_date']:
            raise AppError(422, 'Warranty expiry cannot precede purchase date')
        return result

    def execute(self, actor, entity_id, command):
        require(actor, 'asset:manage')
        with self.journal.lock(actor.organization_id) as db:
            op = self.journal.operation(db, actor, command.idempotency_key,
                {'asset_id': entity_id, **command.model_dump(mode='json')})
            if op.result is not None:
                return op.result
            pending = db.execute("SELECT operation_key FROM operations WHERE organization_id=%s AND operation_key<>%s AND result IS NULL AND progress->'asset_plan' IS NOT NULL AND progress->'asset_plan' <> 'null'::jsonb LIMIT 1",
                (actor.organization_id, command.idempotency_key)).fetchone()
            if pending:
                raise AppError(409, 'An asset operation is incomplete. Retry it before making another change.')
            rows = self.rows()
            if not op.progress.get('asset_plan'):
                row = next((r for r in rows if r['entity_id'] == entity_id), None)
                if command.action != 'create' and row is None:
                    raise AppError(404, 'Asset was not found')
                if command.action == 'create' and entity_id is not None:
                    raise AppError(422, 'Create does not accept an asset ID')
                data = row['data'] if row else {}
                if command.action == 'issue':
                    if set(command.data) - {'issued_employee_id', 'issued_date', 'issue_note'}:
                        raise AppError(422, 'Invalid issue fields')
                    editable_values(self.platform, ASSET, command.data, current=data, excluded={f['field'] for f in configured_form(self.platform, ASSET)['fields'] if f['field'] not in {'issued_employee_id','issued_date','issue_note'}})
                    employee = next((r for r in self.service.employees() if r['entity_id'] == command.data.get('issued_employee_id')
                        and r['data'].get('employment_status') == 'active'), None)
                    if employee is None:
                        raise AppError(422, 'Choose an active employee in this organization')
                    if self.platform.states('hrms_asset').get(entity_id) != 'available' or data.get('issued_employee_id'):
                        raise AppError(409, 'Only an available asset can be issued')
                    offered = self.platform.call('GET', f'/entities/{entity_id}/transitions/available')
                    if not any(t['trigger'] == 'issue' or t.get('to_state') == 'issued' for t in offered.get('available_transitions', [])):
                        raise AppError(409, 'The configured workflow does not allow issue')
                    try:
                        issued = date.fromisoformat(command.data.get('issued_date', ''))
                    except (ValueError, TypeError):
                        raise AppError(422, 'A valid issue date is required') from None
                    if issued > date.today():
                        raise AppError(422, 'Issue date cannot be in the future')
                    note = command.data.get('issue_note', '')
                    if not isinstance(note, str) or len(note) > 2000:
                        raise AppError(422, 'Issue note must be text of at most 2000 characters')
                    data = {**data, 'issued_employee_id': employee['entity_id'], 'issued_date': issued.isoformat(),
                        'issued_by': actor.user_id, 'issue_note': note}

                else:
                    data = self.inventory_data(command.data, data)
                    for other in rows:
                        if other['entity_id'] == entity_id:
                            continue
                        for key in ('asset_tag', 'serial_number'):
                            if data.get(key) and str(other['data'].get(key, '')).casefold() == str(data[key]).casefold():
                                raise AppError(409, f'An asset with this {key.replace("_", " ")} already exists')
                op.checkpoint(asset_plan=data, asset_before=row['data'] if row else {})
            data = op.progress['asset_plan']
            if command.action == 'create':
                marker = 'asset:' + command.idempotency_key
                row = self.service._create_once(op, 'asset', ASSET, {**data, 'hrms_operation_key': marker},
                    actor.user_id, rows, marker)
                entity_id = row['entity_id']
                self.platform.enroll(entity_id, 'hrms_asset')
            else:
                self.platform.call('PUT', f'/entity-records/{entity_id}', json={'data': data})
                if command.action == 'issue':
                    try:
                        self.platform.call('POST', f'/entities/{entity_id}/transitions', json={
                            'entity_id': entity_id, 'trigger': 'issue', 'idempotency_key': 'asset:' + command.idempotency_key})
                    except AppError as exc:
                        # Definite rejection can be corrected. Unknown network outcomes stay reserved for replay.
                        if exc.status < 500 and self.platform.states('hrms_asset').get(entity_id) == 'available':
                            self.platform.call('PUT', f'/entity-records/{entity_id}', json={'data': op.progress['asset_before']})
                            op.checkpoint(asset_plan=None)
                        raise
            self.journal.audit(db, actor, 'asset.' + command.action, entity_id, command.idempotency_key)
            result = {'entity_id': entity_id}
            op.finish(result)
            return result
