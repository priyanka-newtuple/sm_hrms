"""Exercise the pending-operation query with real PostgreSQL parameter typing."""
import ast
import inspect
import os
import textwrap

import psycopg
import pytest

from hrms_app.assets import AssetService


def test_pending_asset_query_accepts_new_asset_and_preserves_scope():
    dsn = os.environ.get('HRMS_TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('Set HRMS_TEST_DATABASE_URL for PostgreSQL regression coverage')
    tree = ast.parse(textwrap.dedent(inspect.getsource(AssetService._execute)))
    query = next(node.value for node in ast.walk(tree)
                 if isinstance(node, ast.Constant) and isinstance(node.value, str)
                 and node.value.startswith('SELECT operation_key FROM operations'))
    # A session-local table shadows the real journal; no business data is touched.
    with psycopg.connect(dsn) as db:
        db.execute('CREATE TEMP TABLE operations (organization_id text, operation_key text, result jsonb, progress jsonb)')
        def pending(target=None, key='new'):
            return db.execute(query, ('tenant-a', key, target, target)).fetchone()
        assert pending() is None
        db.execute("INSERT INTO operations VALUES ('tenant-b','foreign',NULL,'{\"asset_plan\":{\"name\":\"x\"}}')")
        assert pending() is None
        db.execute("INSERT INTO operations VALUES ('tenant-a','unfinished',NULL,'{\"asset_plan\":{\"name\":\"x\"},\"asset_target\":\"asset-1\"}')")
        assert pending() == ('unfinished',)
        assert pending('asset-1') == ('unfinished',)
        assert pending('asset-2') is None
        assert pending(key='unfinished') is None
        db.execute("UPDATE operations SET result='{}' WHERE organization_id='tenant-a'")
        assert pending() is None
