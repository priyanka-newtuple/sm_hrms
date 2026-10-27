"""Asset inventory configuration, installed into the native platform."""
ASSET = 'HRMS.Asset'
TYPES = frozenset({ASSET})


def asset_packs(pack):
    return (pack(entity_type=ASSET, label='Asset', identifier_prefix='AST', fields=(
        {'field': 'asset_tag', 'type': 'string', 'required': False},
        {'field': 'asset_name', 'type': 'string', 'required': True},
        {'field': 'asset_category', 'type': 'enum', 'required': True},
        {'field': 'serial_number', 'type': 'string'},
        {'field': 'manufacturer', 'type': 'string'},
        {'field': 'model', 'type': 'string'},
        {'field': 'asset_location', 'type': 'string'},
        {'field': 'purchase_date', 'type': 'date'},
        {'field': 'warranty_expiry', 'type': 'date'},
        {'field': 'asset_condition', 'type': 'enum', 'required': True},
        {'field': 'asset_notes', 'type': 'text'},
        {'field': 'issued_employee_id', 'type': 'string'},
        {'field': 'issued_date', 'type': 'date'},
        {'field': 'issued_by', 'type': 'string'},
        {'field': 'issue_note', 'type': 'text'},
    ), initial_state='available', states=('available', 'issued'),
        terminal_states=frozenset({'issued'}), transitions=(('available', 'issue', 'issued'),)),)
