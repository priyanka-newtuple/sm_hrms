# Retire legacy credential stores: `email_configs` + `llm_api_keys`

**Type:** Tech-debt / cleanup
**Priority:** P2 (no functional gap; reduces confusion and dead surface area)
**Owner:** TBD
**Status:** Proposed

---

## 1. Summary

`organization_integrations` is the canonical, org-scoped store for integration
credentials. Two older per-capability tables still exist and are read only as
*fallbacks*:

- `email_configs` (mail module) — SMTP/SES credentials
- `llm_api_keys` (llm_config module) — LLM provider API keys

Neither is written by the product anymore (the Settings UI routes everything
through `unifiedIntegrations.ts` → `/integrations/...`). This ticket removes the
dead write surface, the fallback reads, and finally the tables, after backfilling
any residual data into `organization_integrations`.

## 2. Why now

- The email SMTP/SES send path historically read `email_configs` *without*
  preferring `organization_integrations`, which caused mention/comment emails to
  silently not send even when SMTP was "valid" in Settings → Integrations. That
  read path is now bridged (org_integrations first, legacy fallback), so the
  legacy tables no longer carry behaviour — only ambiguity.
- Two parallel config subsystems for the same data invite exactly the class of
  bug above. Collapsing to one store removes a whole category of "configured but
  not working."

## 3. Current state (verified)

### Reads (consumers)
- **Email** — `mail/manager.py::get_decrypted_credentials`
  - ACS, Microsoft Graph: `organization_integrations` (always)
  - SMTP, SES: `organization_integrations` → `email_configs` → env (SMTP only)
- **LLM** — `llm/manager.py::_resolve_provider_credentials`
  - `organization_integrations` → `llm_api_keys` (`get_api_key_for_model`)

### Writes (product)
- Frontend writes **only** to `/integrations/...` via `unifiedIntegrations.ts`.
- Legacy `emailConfig.ts` client: re-exported but **called by zero components**.
- No frontend calls to `/config/llm-keys` at all.

### Dead-but-mounted backend endpoints
- Mail (`mail/controller.py`): `/config/email/providers`, `/config/email`
  (GET/POST), `/config/email/{provider}` (DELETE), `/config/email/validate`,
  `/config/email/test`
- llm_config (`llm_config/controller.py`): `/config/llm-keys/providers`,
  `/config/llm-keys` (GET/POST), `/config/llm-keys/{provider}` (DELETE),
  `/config/llm-keys/validate`

### Data
- ATS2 (`state-machine-ats2`): `email_configs = 0`, `llm_api_keys = 0`,
  `organization_integrations = 2`. Clean.
- **Unknown for other deployments** (e.g. legacy `ai_ats`, older orgs). This is
  the primary precondition — see §5.

## 4. Goal / end state

- One credential store: `organization_integrations`.
- `mail` module keeps `email_templates` and `inbound_emails` (still required —
  mention/comment emails render from templates). Only the `email_configs`
  credential table and its endpoints are removed.
- `llm_config` module's key table and endpoints removed; `llm/manager.py` reads
  credentials solely from `organization_integrations`.

## 5. Preconditions & risks

1. **Residual data in other DBs.** Before dropping anything, confirm every live
   DB has `email_configs` and `llm_api_keys` empty, or backfill non-empty rows
   into `organization_integrations` first. Do **not** drop the fallback reads
   until this is verified per environment.
2. **Two Alembic heads currently exist** (`202607180001`, `202607280001`). A
   drop migration needs a single `down_revision`; add a **merge migration**
   first (or branch off the correct head) per
   `backend/alembic/versions/migration_guidelines.MD`. Runtime uses
   `alembic upgrade heads` (plural) so both apply, but new revisions must not
   fork further.
3. **Test-send capability.** `/config/email/test` (send a test email) is genuine
   functionality. Preserve an equivalent under the integrations surface (it can
   reuse `send_email`, which now resolves from `organization_integrations`)
   before deleting the legacy endpoint, so admins keep a "send test" button.
4. **Env-SMTP fallback** (`_smtp_credentials_from_env`): **removed.** Product
   decision — email providers are configured exclusively via Settings →
   Integrations (`organization_integrations`), so SMTP credentials are no longer
   read from environment/app config. (The LLM env-key fallback is retained.)
5. **External API consumers.** The legacy endpoints are unused by our UI but
   could theoretically be called by scripts. Low risk; announce removal.

## 6. Plan (waves)

Waves are ordered by dependency; each is independently shippable and reversible.

### Wave 1 — Backfill + audit (no deletions)
- Add a one-off script/management command (or Alembic data migration) that copies
  any `email_configs` / `llm_api_keys` rows into `organization_integrations`
  (re-encrypting secrets under the same key; mapping SMTP `username/password`,
  SES `aws_access_key_id/aws_secret_access_key`, LLM `encrypted_key` → provider
  `api_key`). Idempotent; skips providers already present.
- Run against every live environment; record row counts before/after.
- **Exit criteria:** all environments show `email_configs`/`llm_api_keys` fully
  represented in `organization_integrations`.
- Files: new `backend/alembic/versions/<date>_backfill_legacy_email_llm_into_org_integrations.py`
  (data-only) **or** a `bootstrap/` script if you prefer non-migration backfill.

### Wave 2 — Remove dead write/read surface (backend)
- Delete legacy endpoints:
  - `mail/controller.py`: the six `/config/email*` routes (keep all
    `/email-templates*`).
  - `llm_config/controller.py`: all `/config/llm-keys*` routes.
- Drop the fallback branches:
  - `mail/manager.py::get_decrypted_credentials` — remove the `email_configs`
    (`get_config`) read for SMTP/SES; keep env fallback if §5.4 says so.
  - `llm/manager.py` — remove the `get_api_key_for_model` (`llm_api_keys`)
    fallback; org_integrations becomes the sole source.
- Preserve the test-send capability per §5.3.
- Prune now-unused code: `EmailConfig` write helpers in `mail/manager.py`,
  `llm_config/manager.py` + `llm_config/db_models.py::LlmConfigModelService`
  write paths, and wiring in `backend/main.py`.
- Update `test_architecture_constraints.py` / module tests as needed.
- Frontend: delete unused `core/services/api/emailConfig.ts` and its re-exports;
  confirm nothing imports it (already the case).

### Wave 3 — Drop the tables (migration)
- After Wave 1 backfill is confirmed in all envs and Wave 2 has shipped:
  - Merge migration to collapse the two heads (if still split).
  - `DROP TABLE email_configs;` and `DROP TABLE llm_api_keys;` with a
    reversible `downgrade()` that recreates the schemas (data not restored).
- Keep `email_templates`, `inbound_emails`, `mcp_*`, and
  `integration_capability_defaults` untouched.

## 7. Rollback

- Waves are independent. Wave 2 is a code revert. Wave 3's `downgrade()`
  recreates empty tables; combined with reverting Wave 2, the fallback reads
  return — but rows are gone, so rollback is only meaningful *before* Wave 1
  data is trusted. Treat Wave 3 as the point of no return and gate it on
  sign-off that backfill is complete everywhere.

## 8. Verification

- Backend: `cd backend && DATABASE_URL=... uv run pytest tests/test_mail_module.py tests/test_integrations_module.py tests/test_architecture_constraints.py -q`
- Functional: configure SMTP + LLM via Settings → Integrations only; confirm
  (a) mention/comment email sends, (b) an LLM-backed agent call resolves a key —
  both with `email_configs`/`llm_api_keys` empty.
- Grep: no remaining references to `EmailConfig`, `email_configs`, `LLMApiKey`,
  `llm_api_keys`, `/config/email`, `/config/llm-keys` outside the drop migration.

## 9. Out of scope (track separately)

- **Encryption-key hardening.** `organization_integrations` secrets are
  Fernet-encrypted with a key derived via `SHA256(master_key)`, where
  `master_key = ENCRYPTION_KEY or JWT_SECRET_KEY`. On ATS2, `ENCRYPTION_KEY` is
  unset, so the JWT secret doubles as the encryption key (key reuse). Separate
  ticket: set a dedicated high-entropy `ENCRYPTION_KEY`, add a proper KDF and a
  re-encrypt/rotation path. Note a key change would orphan existing ciphertext,
  so it needs its own migration.
- Calendar (`google_calendar`/`outlook`/`ics`) and push
  (`azure_notification_hub`) providers are registry-defined but unconsumed —
  finish or remove in a different ticket.

## 10. Agent Feedback

- **Started:** —
- **Completed:** —
- **Notes:** Origin of the split traced to commit `9b1fe845` (2026-05-21,
  "added email template library and integrations module with ACS support"),
  which introduced `organization_integrations` and wired only ACS to read from
  it. SMTP/SES read-path bridge landed on branch
  `fix/smtp-ses-read-from-org-integrations`; this ticket is the follow-up to
  retire the now-redundant stores.
