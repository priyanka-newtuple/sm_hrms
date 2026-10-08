"""Verify the original platform source remains unchanged by the HRMS overlay."""
from pathlib import Path
import subprocess
import sys

BASELINE = 'e583a69f7adb0fc5f87a93cd161590ee54bb2ca3'
ROOT = Path(__file__).resolve().parents[1]
OVERLAY = [':(exclude)backend/hrms', ':(exclude)frontend/src/skins/hrms', ':(exclude)frontend/src/skins/hrms_native']

# Reviewed platform patches, each pinned to the commit that approved it: the file must
# match that commit exactly, so a later edit fails here just like any other core change.
APPROVED_PATCHES = {
    # Forms -> Field Library migration: Decimal type, plain-JSON pin fix, date mapping.
    'e8c0c9e0ddddf0c83c0bd1e986c80275ce3fbb20': [
        'backend/alembic/versions/2026_10_08_0001_add_decimal_field_type.py',
        'backend/scripts/data_repairs/restore_hrms_project_decimal_fields.py',
        'backend/scripts/migrate_forms_to_method_blocks.py',
        'backend/tests/test_forms_migration_type_mapping.py',
        'backend/workflow/manager.py',
        'backend/workflow/models/interface.py',
    ],
}


def _differs(commit, *pathspec):
    # Compare Git-normalized contents so Windows checkout line endings do not hide changes.
    return subprocess.run(
        ['git', '-c', 'core.safecrlf=false', 'diff', '--quiet', commit, '--', *pathspec], cwd=ROOT
    ).returncode


def main():
    paths = subprocess.check_output(
        ['git', 'ls-tree', '-r', '--name-only', BASELINE, 'backend', 'frontend/src'], cwd=ROOT
    ).decode().splitlines()
    approved = [path for files in APPROVED_PATCHES.values() for path in files]
    if _differs(BASELINE, 'backend', 'frontend/src', *OVERLAY, *(f':(exclude){p}' for p in approved)):
        print('FAIL: tracked core files differ from the original platform baseline')
        sys.exit(1)
    for commit, files in APPROVED_PATCHES.items():
        if _differs(commit, *files):
            print(f'FAIL: approved platform patch files differ from {commit[:12]}')
            sys.exit(1)
    print(f'PASS: {len(paths)} tracked backend/frontend core files match {BASELINE[:12]}'
          f' plus {len(approved)} approved patch files')


if __name__ == '__main__':
    main()
