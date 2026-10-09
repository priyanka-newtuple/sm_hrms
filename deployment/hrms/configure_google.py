"""Install Google credentials from CI stdin without logging their values."""
import json
import os
from pathlib import Path
import re
import sys
import tempfile


def configure(values, path):
    keys = ('GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET')
    if not any(values.get(key) for key in keys):
        return False  # Preserve existing server configuration on ordinary deployments.
    if not all(isinstance(values.get(key), str) and re.fullmatch(r'[A-Za-z0-9_.-]+', values[key]) for key in keys):
        raise ValueError('Set both valid GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET secrets.')
    text = path.read_text()
    lines = [line for line in text.splitlines() if line.split('=', 1)[0] not in keys]
    lines.extend(f'{key}={values[key]}' for key in keys)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.oauth-')
    try:
        os.chmod(name, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write('\n'.join(lines) + '\n')
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return True


if __name__ == '__main__':
    configure(json.load(sys.stdin), Path('/opt/newtuple-hrms/production.env'))
    print('Google configuration checked.')
