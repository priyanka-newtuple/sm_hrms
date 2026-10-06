"""Tenant-installed WFH entities, forms and workflows; no core changes."""
POLICY = 'HRMS.WorkFromHomePolicy'
REQUEST = 'HRMS.WorkFromHomeRequest'
TYPES = (POLICY, REQUEST)


def wfh_packs(cls):
    return (
        cls(POLICY, 'Work from home policy', 'WFP', (
            {'field': 'year', 'type': 'integer', 'required': True},
            {'field': 'annual_days', 'type': 'integer', 'required': True, 'description': 'Annual WFH allowance (full days)'},
            {'field': 'notice_days', 'type': 'integer', 'required': True, 'description': 'Minimum notice (calendar days)'},
            {'field': 'revision', 'type': 'integer'},
        ), 'draft', ('draft', 'active'), frozenset({'active'}), (('draft', 'activate', 'active'),)),
        cls(REQUEST, 'Work from home request', 'WFH', (
            {'field': 'employee_id', 'type': 'string', 'required': True},
            {'field': 'policy_id', 'type': 'string', 'required': True},
            {'field': 'year', 'type': 'integer', 'required': True},
            {'field': 'dates', 'type': 'text', 'required': True, 'description': 'Work from home dates'},
            {'field': 'reason', 'type': 'text', 'description': 'Note for HR (optional)'},
        ), 'pending', ('pending', 'approved', 'rejected', 'cancelled'),
            frozenset({'rejected', 'cancelled'}), (
                ('pending', 'approve', 'approved'), ('pending', 'reject', 'rejected'),
                ('pending', 'cancel', 'cancelled'), ('approved', 'cancel', 'cancelled'),
            )),
    )
