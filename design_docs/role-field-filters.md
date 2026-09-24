# Role Field Filteration

This settings tab narrows a role's **view** permission for each entity type. It does not change create/edit/delete permissions or workflow transition guards.

## Behavior

Each row has a field, comparison operator and value. Add AND/OR rows to build an expression. AND takes precedence: `A AND B OR C` means `(A AND B) OR C`. Removing a row also removes the connector preceding it. The first row has no connector. Up to 50 conditions are supported, with up to 256 characters per input.

| Operator | Behavior |
| --- | --- |
| Equals / Not equals | Existing scalar comparison behavior is preserved. |
| Is one of (`in`) | A scalar matches any listed value; a multi-select array matches if any selection is listed. |
| Is not one of (`not_in`) | A scalar must not be listed; a multi-select array must have no listed selections. |

Membership inputs are comma-separated. Spaces around entered values and empty entries are ignored; duplicates are harmless. Lists with no usable values cannot be saved. Text comparisons are exact and case-sensitive: `North` differs from `north`. Record text itself is not trimmed. A comma is a separator, not CSV quoting syntax; a literal value containing a comma cannot be expressed with these membership operators.

Numbers stored as numbers compare numerically (including exponent notation); strings remain exact strings. Boolean fields retain the existing `True` / `False` spelling. Missing values, JSON null, empty strings and arrays with no non-empty selections satisfy neither membership operator. Null/empty selections are ignored when other selections exist. Structured objects or nested arrays fail closed, including under `not_in`.

Conditions within one role remain grouped. An unconditional granting role still provides full read access, and separate granting roles still combine using OR. Inherited-field resolution gathers every field used in the expression before evaluating it.

Regex is not included.

## Code map

- `frontend/src/pages/settings/components/role/field-permission/entity-condition-row.tsx`: editor and operator labels.
- `frontend/src/lib/entity-data.ts`: editor completeness validation.
- `frontend/src/pages/settings/components/role/detail/role-payload.ts`: load legacy/saved filters and build save payloads.
- `frontend/src/core/types/rbac.ts`: API/editor contracts.
- `backend/roles/models/request.py` and `backend/roles/manager.py`: shape, operator, value and field validation.
- `backend/roles/db_models.py`: persistence, duplication and per-role policy compilation.
- `backend/common/protocols.py`: expression compilation and authoritative record evaluation.
- `backend/common/condition_values.py`: shared membership parsing.
- `backend/common/condition_sql.py`: equivalent PostgreSQL membership predicates, using a scalar fast path or one aggregate scan per array.
- `backend/workflow/db_models.py`: SQL expression composition for workflow list reads.

The workflow manager's `_normalize_field_filter_scalar` is for separate search filters, not role visibility filters.

## Storage and compatibility

Migration `202609170001` adds nullable JSON `role_permissions.read_filter`. Existing scalar condition columns remain readable without a data migration. New filters use `{ "conditions": [...] }`; each row after the first carries its preceding `conjunction` (`AND` or `OR`). Supplying both legacy and compound formats is rejected. Turning filtering off clears the expression. Downgrade refuses to drop populated compound filters, because that could silently widen access.

Membership values and numeric forms are parsed once per compiled condition and reused across records. Field-schema lookup occurs once per compound-filter validation, rather than once per row. SQL filters are parameterized. Inherited-field conditions retain the existing resolved-row path instead of incorrectly filtering only stored child data.

## Local development

From the repository root, start the containerized backend, PostgreSQL and Redis with the actual environment file:

```sh
docker compose --env-file backend/etc/.env -f docker-compose.local.yml up -d --build modular-db modular-redis modular-backend
```

In another terminal:

```sh
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5111
```

Open http://localhost:5111. Backend API documentation is at http://localhost:8001/docs. Backend code is mounted into the container; restart `modular-backend` after Python changes. Frontend changes reload automatically.

The local setup uses ignored `backend/etc/.env` and `frontend/.env` files. Development login credentials are in `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD`; no production credentials are needed. A local, unassigned **Filter Demo Analyst** role and **FilterDemo.Application** entity were created for manual verification. Find them under Settings → Roles → Field Filteration.

## Verification

```sh
docker compose --env-file backend/etc/.env -f docker-compose.local.yml exec -T modular-backend python -m pytest tests/test_role_membership_filters.py tests/test_compound_role_read_filters.py tests/test_workflow_module.py tests/test_inherited_field_rbac_matrix.py -q
cd frontend
npm test -- --run src/pages/settings/components/role
npm run build
```

Coverage includes positive/negative membership, multi-select overlap, empty and malformed values, whitespace, duplicates, exact casing, Unicode, punctuation, numbers/booleans, SQL/Python agreement, mixed precedence, legacy compatibility, validation, create/update/duplicate/clear persistence, inherited fields, role union semantics, real workflow pagination, identifier options and editor save/reload behavior.

Existing unrelated failures were reproduced against unchanged HEAD: nine tests in `test_roles_module.py` (outdated authentication/method assumptions), and `test_stat414_local_500_enrollment_benchmark` (query count exceeds its existing threshold). These are not suppressed by the new tests.
