/**
 * Baseline Seed — deterministic, idempotent reference data.
 *
 * Creates stable baseline data (entity type, workflow, form config)
 * that tests can rely on. Runs once in global-setup after auth.
 * Skips creation if data already exists — safe for repeated runs.
 *
 * This is NOT mutable test data — individual tests create their own
 * entities via api-fixtures.ts and clean up after themselves.
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const BACKEND_URL = process.env.VITE_DEV_PROXY_TARGET ?? 'http://localhost:8001';

/** Well-known names — deterministic across all orgs/runs. */
export const BASELINE = {
  entityType: 'E2EBaseline',
  entityTypeDisplayName: 'E2E Baseline',
  workflowKey: 'e2e_baseline_workflow',
  workflowName: 'E2E Baseline Workflow',
  formKey: 'ebaseline__default',
  states: ['OPEN', 'IN_PROGRESS', 'DONE'] as const,
} as const;

export interface BaselineInfo {
  entityTypeId: string;
  entityTypeName: string;
  machineName: string | null;
}

// Defined before seedBaseline so the reference is clear at the call site.
const BASELINE_INFO_PATH = resolve(__dirname, '../.auth/baseline-info.json');

/** Read the token from superadmin storage state — searches all saved origins. */
function getToken(): string {
  const statePath = resolve(__dirname, '../.auth/superadmin.json');
  const stateJson = JSON.parse(readFileSync(statePath, 'utf-8'));
  for (const origin of stateJson.origins ?? []) {
    const token = (origin?.localStorage ?? []).find(
      (item: { name: string; value: string }) => item.name === 'ats_access_token',
    )?.value;
    if (token) return token;
  }
  throw new Error('No auth token found in superadmin storageState (searched all origins)');
}

async function api(
  method: string,
  path: string,
  token: string,
  body?: unknown,
): Promise<{ ok: boolean; status: number; data: unknown }> {
  const backendPath = path.startsWith('/api/') ? `/v1/api${path.slice(4)}` : path;
  const res = await fetch(`${BACKEND_URL}${backendPath}`, {
    method,
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => null);
  return { ok: res.ok, status: res.status, data };
}

// ─── Sub-steps ────────────────────────────────────────────────────────────────

async function seedEntityType(token: string): Promise<string> {
  const etGet = await api('GET', `/api/entity-types/${BASELINE.entityType}`, token);
  if (etGet.ok) {
    const et = etGet.data as { entity_type_id?: string; id?: string };
    console.log(`Baseline: entity type "${BASELINE.entityType}" already exists`);
    return et.entity_type_id ?? et.id ?? '';
  }
  const etCreate = await api('POST', '/api/entity-types', token, {
    name: BASELINE.entityType,
    display_name: BASELINE.entityTypeDisplayName,
    description: 'Stable baseline for E2E tests — do not delete',
    features: { has_lifecycle: true, has_form: false, has_projection: false },
  });
  if (!etCreate.ok) {
    throw new Error(`Baseline: failed to create entity type (HTTP ${etCreate.status})`);
  }
  const et = etCreate.data as { entity_type_id?: string; id?: string };
  console.log(`Baseline: created entity type "${BASELINE.entityType}"`);
  return et.entity_type_id ?? et.id ?? '';
}

async function seedWorkflow(token: string): Promise<string | null> {
  const wfList = await api('GET', '/api/workflow-state-machines', token);
  const wfData = wfList.data as Record<string, unknown>;
  const wfItems = Array.isArray(wfData)
    ? wfData
    : ((wfData?.published_items ?? wfData?.items ?? []) as unknown[]);
  const existing = (
    wfItems as Array<{ machine_key: string; machine_name: string; is_active: boolean }>
  ).find((w) => w.machine_key === BASELINE.workflowKey && w.is_active);

  if (existing) {
    console.log(`Baseline: workflow "${BASELINE.workflowKey}" already active`);
    return existing.machine_name;
  }

  // Create draft
  const draft = await api('POST', '/api/workflow-state-machines/draft', token, {
    name: BASELINE.workflowName,
    description: 'Stable baseline for E2E tests',
  });

  if (draft.status === 409) {
    // Draft already exists but wasn't published — use whatever is there
    const allWf = wfItems as Array<{ machine_name: string; is_active: boolean }>;
    console.log('Baseline: workflow draft already exists, using existing');
    return allWf[allWf.length - 1]?.machine_name ?? null;
  }
  if (!draft.ok) {
    throw new Error(`Baseline: failed to create workflow draft (HTTP ${draft.status})`);
  }

  const draftData = draft.data as { id: string; machine_name: string };
  const pub = await api(
    'POST',
    `/api/workflow-state-machines/${draftData.id}/publish`,
    token,
    {
      definition: {
        machine_key: BASELINE.workflowKey,
        name: BASELINE.workflowName,
        entity_type: BASELINE.entityType,
        entity_schema: {
          entity_type: BASELINE.entityType,
          fields: [
            { field: 'title', type: 'string', required: true, description: 'Title' },
            { field: 'description', type: 'text', required: false, description: 'Description' },
          ],
        },
        states: [
          { name: 'OPEN', tags: ['initial'], order: 1 },
          { name: 'IN_PROGRESS', tags: [], order: 2 },
          { name: 'DONE', tags: ['terminal'], order: 3 },
        ],
        initial_state: 'OPEN',
        transitions: [
          { key: 'start', trigger: 'START', label: 'Start', from: 'OPEN', to_state: 'IN_PROGRESS' },
          { key: 'finish', trigger: 'FINISH', label: 'Finish', from: 'IN_PROGRESS', to_state: 'DONE' },
          { key: 'reopen', trigger: 'REOPEN', label: 'Reopen', from: 'IN_PROGRESS', to_state: 'OPEN' },
        ],
      },
    },
  );

  if (!pub.ok) {
    throw new Error(
      `Baseline: workflow publication failed (HTTP ${pub.status}) — setup cannot continue without an active baseline workflow`,
    );
  }
  console.log(`Baseline: published workflow "${BASELINE.workflowKey}"`);
  return draftData.machine_name;
}

async function seedFormConfig(token: string): Promise<void> {
  const formGet = await api('GET', `/api/forms/config/${BASELINE.formKey}`, token);
  if (formGet.ok) {
    console.log(`Baseline: form "${BASELINE.formKey}" already exists`);
    return;
  }
  const formCreate = await api('POST', '/api/forms/config', token, {
    schema_key: BASELINE.formKey,
    name: 'Default',
    entity_type: BASELINE.entityType,
    fields: [
      { field: 'title', type: 'string', required: true, description: 'Title' },
      { field: 'description', type: 'text', required: false, description: 'Description' },
    ],
    is_active: true,
  });
  if (formCreate.ok || formCreate.status === 409) {
    console.log(`Baseline: form "${BASELINE.formKey}" created`);
  } else {
    console.warn(`Baseline: failed to create form (HTTP ${formCreate.status}) — tests may miss form fields`);
  }
}

// ─── Orchestrator ─────────────────────────────────────────────────────────────

/**
 * Provision stable baseline data. Idempotent — each step checks
 * if the resource already exists before creating.
 *
 * Returns the baseline info needed by tests.
 */
export async function seedBaseline(): Promise<BaselineInfo> {
  const token = getToken();
  const entityTypeId = await seedEntityType(token);
  const machineName = await seedWorkflow(token);
  await seedFormConfig(token);
  const info: BaselineInfo = { entityTypeId, entityTypeName: BASELINE.entityType, machineName };
  writeFileSync(BASELINE_INFO_PATH, JSON.stringify(info, null, 2));
  return info;
}

/** Read baseline info persisted by seedBaseline (called from test workers). */
export function getBaselineInfo(): BaselineInfo | null {
  try {
    return JSON.parse(readFileSync(BASELINE_INFO_PATH, 'utf-8')) as BaselineInfo;
  } catch {
    return null;
  }
}
