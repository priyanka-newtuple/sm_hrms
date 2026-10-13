"""Shared validation of human input against the tenant's native form.

Operational parameters (approvers, concurrency tokens) are explicit; they never
make system fields writable. Business contracts still validate dates and limits.
"""
from pydantic import ValidationError
from .errors import AppError
from .catalog import pack_by_type
from .form_config import configured_form
from .custom_fields import _typed


def editable_values(platform, kind, values, *, excluded=(), current=None, aliases=None):
    aliases = aliases or {}
    fields = {aliases.get(f['field'], f['field']): f for f in configured_form(platform, kind)['fields']
              if f['field'] not in {'identifier', 'hrms_operation_key', *excluded}}
    unknown = set(values) - set(fields)
    if unknown:
        raise AppError(422, 'Not on the configured form: ' + ', '.join(sorted(unknown)))
    current = current or {}
    result = {}
    for key, field in fields.items():
        label = field.get('description') or key.replace('_', ' ').capitalize()
        if field.get('read_only'):
            if key in values and values[key] != current.get(key):
                raise AppError(422, f'{label} is read-only')
            continue
        value = values.get(key, current.get(key))
        if value in (None, ''):
            if field.get('required'):
                raise AppError(422, f'{label} is required')
            if key in values:
                result[key] = value
        elif key in values:
            result[key] = value if key in current and value == current[key] else _typed(label, field, value)
    return result


def record_input(platform, kind, model, data, *, excluded=(), operational=(), current=None):
    # A form attachment never grants permission to edit a generated domain attribute.
    protected={f['field'] for f in pack_by_type(kind).fields} - set(model.model_fields)
    excluded=set(excluded) | protected
    record = {k:v for k,v in data.items() if k not in operational}
    checked = editable_values(platform, kind, record, excluded=excluded, current=current)
    own = {k:v for k,v in data.items() if k in model.model_fields}
    # An edit preserves values outside the form, including historical retired fields.
    previous = {k:v for k,v in (current or {}).items() if k in model.model_fields and k not in own}
    try:
        parsed = model.model_validate({**previous, **own}).model_dump(mode='json')
    except ValidationError as exc:
        raise AppError(422, '; '.join(f"{'.'.join(map(str,e['loc']))}: {e['msg']}" for e in exc.errors())) from exc
    # Do not reintroduce removed fields through contract defaults.
    fields = {f['field'] for f in configured_form(platform, kind)['fields'] if not f.get('read_only')}
    return {**{k:v for k,v in parsed.items() if k in fields or k in operational}, **{k:v for k,v in checked.items() if k not in parsed}}
