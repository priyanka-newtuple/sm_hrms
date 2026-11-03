"""Write a private Compose environment file from the encrypted deployment payload."""
import json
import re
import sys
from pathlib import Path


def configure(payload, destination):
    mode = payload.get('HRMS_RAZORPAY_MODE') or 'disabled'
    if mode not in {'disabled', 'mock', 'live'}:
        raise ValueError('Payroll mode must be disabled, mock or live. Payroll sandbox is not verified.')
    identity = payload.get('HRMS_RAZORPAY_API_ID', '') if mode == 'live' else ''
    key = payload.get('HRMS_RAZORPAY_API_KEY', '') if mode == 'live' else ''
    if mode == 'live' and (not re.fullmatch(r'[0-9]+', identity) or not re.fullmatch(r'[A-Za-z0-9_-]+', key)):
        raise ValueError('Live Payroll requires a numeric API ID and valid Payroll API key')
    values = {'HRMS_RAZORPAY_MODE': mode, 'HRMS_RAZORPAY_API_ID': identity, 'HRMS_RAZORPAY_API_KEY': key}
    destination.write_text(''.join(f"{k}='{v}'\n" for k, v in values.items()), encoding='utf-8')
    destination.chmod(0o600)


if __name__ == '__main__':
    try:
        configure(json.load(sys.stdin), Path(sys.argv[1]))
    except (ValueError, OSError):
        sys.exit('Payroll configuration failed. Check the mode and Payroll-specific credentials.')
