"""Application-owned operation journal. No platform tables or credentials."""
from contextlib import contextmanager
import hashlib
import json

import psycopg
from psycopg.types.json import Jsonb

from .errors import AppError


class Journal:
    def __init__(self, dsn):
        self.dsn = dsn

    def initialize(self):
        with psycopg.connect(self.dsn) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS operations (
                organization_id text NOT NULL, operation_key text NOT NULL,
                actor_id text NOT NULL, fingerprint text NOT NULL,
                progress jsonb NOT NULL DEFAULT '{}', result jsonb,
                updated_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (organization_id, operation_key))''')
            db.execute('''CREATE TABLE IF NOT EXISTS action_audit (
                id bigserial PRIMARY KEY, organization_id text NOT NULL,
                actor_id text NOT NULL, action text NOT NULL, target_id text NOT NULL,
                occurred_at timestamptz NOT NULL DEFAULT now())''')
            db.execute('ALTER TABLE action_audit ADD COLUMN IF NOT EXISTS operation_key text')

    @contextmanager
    def lock(self, organization_id):
        # Session advisory lock survives journal checkpoint commits; released on disconnect.
        # Serialize HRMS mutations per tenant, across workers, to protect prerequisite/overlap checks.
        with psycopg.connect(self.dsn, autocommit=True) as db:
            db.execute('SET lock_timeout = \'30s\'')
            db.execute('SELECT pg_advisory_lock(hashtextextended(%s, 0))', (organization_id,))
            try:
                yield db
            finally:
                db.execute('SELECT pg_advisory_unlock(hashtextextended(%s, 0))', (organization_id,))

    def operation(self, db, actor, key, payload):
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        db.execute('''INSERT INTO operations (organization_id, operation_key, actor_id, fingerprint)
                      VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
                   (actor.organization_id, key, actor.user_id, fingerprint))
        row = db.execute('''SELECT actor_id, fingerprint, progress, result FROM operations
                            WHERE organization_id=%s AND operation_key=%s''',
                         (actor.organization_id, key)).fetchone()
        if row[0] != actor.user_id or row[1] != fingerprint:
            raise AppError(409, 'Operation key was already used for another request or actor')
        return Operation(db, actor.organization_id, key, row[2], row[3])

    def audit(self, db, actor, action, target, operation_key=None):
        db.execute('''INSERT INTO action_audit (organization_id,actor_id,action,target_id,operation_key)
                      VALUES (%s,%s,%s,%s,%s)''',
                   (actor.organization_id, actor.user_id, action, target, operation_key))


class Operation:
    def __init__(self, db, org, key, progress, result):
        self.db, self.org, self.key = db, org, key
        self.progress, self.result = progress, result

    def checkpoint(self, **values):
        self.progress.update(values)
        self.db.execute('''UPDATE operations SET progress=%s, updated_at=now()
                           WHERE organization_id=%s AND operation_key=%s''',
                        (Jsonb(self.progress), self.org, self.key))

    def finish(self, result):
        self.db.execute('''UPDATE operations SET result=%s, updated_at=now()
                           WHERE organization_id=%s AND operation_key=%s''',
                        (Jsonb(result), self.org, self.key))
        self.result = result
