"""Address convenience for native employee profile fields; no permission bypass."""
from .errors import AppError

SAME_ADDRESS = 'permanent_same_as_current'
ADDRESS_PARTS = ('address_line_1', 'address_line_2', 'city', 'state', 'postal_code', 'country')


def copy_current_address(fields, values, current):
    configured = {f['field']: f for f in fields}
    if SAME_ADDRESS not in configured or values.get(SAME_ADDRESS, current.get(SAME_ADDRESS)) is not True:
        return values
    merged = {**current, **values}
    result = dict(values)
    for part in ADDRESS_PARTS:
        source, target = 'current_' + part, 'permanent_' + part
        if source not in configured or target not in configured:
            raise AppError(422, 'The configured form needs both current and permanent address fields to use the same-address option')
        if configured[target].get('read_only'):
            raise AppError(403, 'You cannot copy into a read-only permanent address field')
        result[target] = merged.get(source) or ''
    return result
