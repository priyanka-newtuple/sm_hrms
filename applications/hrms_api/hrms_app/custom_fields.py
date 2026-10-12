"""Fields an organization adds in Settings → Fields/Forms, on HRMS screens built around fixed fields.

The screen keeps its own fields and rules. Anything else on the entity type's configured form is a
custom field: shown on the screen, checked here against its configured type, options and required
flag, and stored on the record next to the built-in fields.
"""
from datetime import date, datetime
import time

from .catalog import pack_by_type
from .errors import AppError
from .form_config import configured_form

SKIP = {'hrms_operation_key', 'identifier'}
TEXT = {'string', 'str', 'text', 'phone', 'email', 'url'}
WHOLE = {'integer', 'int', 'number', 'timer_duration'}
DECIMAL = {'float', 'decimal'}
# Kept only for reading which keys to fetch; checks always use the current form.
KEYS_TTL_SECONDS = 60
_keys = {}


def custom_fields(platform, entity_type):
    """The configured fields the HRMS screen does not already have, in form order."""
    built_in = {f['field'] for f in pack_by_type(entity_type).fields} | SKIP
    return [f for f in configured_form(platform, entity_type)['fields'] if f['field'] not in built_in]


def custom_keys(platform, entity_type):
    """Custom field names to fetch with a type's records (briefly cached: lists read them often)."""
    cache_key = (id(platform), entity_type)
    cached = _keys.get(cache_key)
    if cached and time.monotonic() - cached[0] < KEYS_TTL_SECONDS:
        return cached[1]
    try:
        keys = [f['field'] for f in custom_fields(platform, entity_type)]
    except AppError:
        keys = []  # No readable form: the screen still works with its own fields.
    _keys[cache_key] = (time.monotonic(), keys)
    return keys


def custom_values(data, keys):
    return {k: data[k] for k in keys if data.get(k) not in (None, '')}


def check_custom(platform, entity_type, values, current=None):
    """Checked custom values to store. Editing keeps saved values that are not sent again; a
    read-only field keeps whatever it holds."""
    fields = {f['field']: f for f in custom_fields(platform, entity_type)}
    unknown = sorted(set(values) - set(fields))
    if unknown:
        raise AppError(422, f"Not on the configured form: {', '.join(unknown)}")
    current = current or {}
    result = {}
    for key, field in fields.items():
        label = field.get('description') or key.replace('_', ' ').capitalize()
        value = current.get(key) if field.get('read_only') or key not in values else values[key]
        if value in (None, ''):
            if field.get('required') and not field.get('read_only'):
                raise AppError(422, f'{label} is required')
            continue
        result[key] = _typed(label, field, value)
    return result


def _typed(label, field, value):
    kind = str(field.get('type') or 'string').lower()
    options = field.get('enum_values')
    if options and value not in options:
        raise AppError(422, f'{label} must be one of the configured options')
    if kind in TEXT or kind == 'enum':
        if not isinstance(value, str):
            raise AppError(422, f'{label} must be text')
        return value
    if kind in WHOLE:
        if isinstance(value, bool) or not isinstance(value, int):
            raise AppError(422, f'{label} must be a whole number')
        return value
    if kind in DECIMAL:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise AppError(422, f'{label} must be a number')
        return float(value)
    if kind in {'boolean', 'bool'}:
        if not isinstance(value, bool):
            raise AppError(422, f'{label} must be yes or no')
        return value
    if kind in {'date', 'datetime'}:
        try:
            (date if kind == 'date' else datetime).fromisoformat(value)
        except (TypeError, ValueError):
            raise AppError(422, f'{label} must be a date') from None
        return value
    return value  # json, documents and other types the screen shows but does not edit
