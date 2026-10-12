"""Verify the original platform source remains unchanged by the HRMS overlay."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

BASELINE = 'e583a69f7adb0fc5f87a93cd161590ee54bb2ca3'
ROOT = Path(__file__).resolve().parents[1]


def main():
    paths = subprocess.check_output(
        ['git', 'ls-tree', '-r', '--name-only', BASELINE, 'backend', 'frontend/src'], cwd=ROOT
    ).decode().splitlines()
    approved = json.loads((ROOT / 'scripts/platform-approved-extensions.json').read_text())['files']
    for name, expected in approved.items():
        path = ROOT / name
        actual = hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() if path.is_file() else None
        if actual != expected:
            sys.exit(f'FAIL: approved generic extension changed: {name}')
    # Compare Git-normalized contents so Windows checkout line endings do not hide changes.
    result = subprocess.run(
        ['git', '-c', 'core.safecrlf=false', 'diff', '--quiet', BASELINE, '--',
         'backend', 'frontend/src', ':(exclude)backend/hrms',
         ':(exclude)frontend/src/skins/hrms', ':(exclude)frontend/src/skins/hrms_native',
         *[f':(exclude){name}' for name in approved]], cwd=ROOT
    )
    if result.returncode:
        print('FAIL: tracked core files differ from the original platform baseline')
        sys.exit(result.returncode)
    print(f'PASS: core matches {BASELINE[:12]} except {len(approved)} explicitly approved, hash-verified generic extension files')


if __name__ == '__main__':
    main()
