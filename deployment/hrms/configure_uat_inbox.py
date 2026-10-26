"""Validate deployment switches without emitting any email credentials."""
import json
import sys


def switches(values):
    mode = str(values.get('HRMS_EMAIL_MODE') or 'capture').strip().lower()
    flag = str(values.get('HRMS_UAT_INBOX_ENABLED') or 'false').strip().lower()
    if mode not in {'capture', 'live'} or flag not in {'true', 'false'}:
        raise ValueError('Invalid UAT inbox or email mode switch')
    return mode, 'true' if mode == 'capture' and flag == 'true' else 'false'


if __name__ == '__main__':
    try:
        print(' '.join(switches(json.load(sys.stdin))))
    except Exception:
        raise SystemExit('Invalid email/inbox deployment switches') from None
