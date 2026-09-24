import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Page } from '@playwright/test';

import { BASELINE, getBaselineInfo } from './baseline-seed';

const __dirname = dirname(fileURLToPath(import.meta.url));

/**
 * API fixture helper for E2E tests.
 *
 * Each test creates its own isolated data via API (not UI), tests the UI
 * behavior, then cleans up. No shared mutable state between tests.
 */

/** Read auth token from saved storageState. */
export function getAuthToken(role: 'admin' | 'superadmin' = 'superadmin'): string {
  const statePath = resolve(__dirname, `../.auth/${role}.json`);
  const stateJson = JSON.parse(readFileSync(statePath, 'utf-8'));
  const origin = stateJson.origins?.find(
    (o: { origin: string }) => o.origin.includes('localhost'),
  );
  const token = origin?.localStorage?.find(
    (item: { name: string; value: string }) => item.name === 'ats_access_token',
  )?.value;
  if (!token) throw new Error(`No auth token in ${role} storageState`);
  return token;
}

/** Get auth token from a live page's localStorage. */
export async function getPageToken(page: Page): Promise<string> {
  const token = await page.evaluate(() => localStorage.getItem('ats_access_token'));
  if (!token) throw new Error('No auth token in page localStorage');
  return token;
}

// API calls go directly to the backend — not through the Vite dev proxy.
// The proxy only runs inside the browser; Node-side fetch needs the backend URL.
const BACKEND_URL = process.env.VITE_DEV_PROXY_TARGET ?? 'http://localhost:8001';

interface ApiOptions {
  method?: string;
  body?: Record<string, unknown>;
  token: string;
}

/** Make an API request. Returns parsed JSON. */
async function api<T = unknown>(path: string, opts: ApiOptions): Promise<T> {
  // Rewrite /api/... to /v1/api/... (matching the Vite proxy rewrite rule)
  const backendPath = path.startsWith('/api/') ? `/v1/api${path.slice(4)}` : path;
  const res = await fetch(`${BACKEND_URL}${backendPath}`, {
    method: opts.method ?? 'GET',
    headers: {
      Authorization: `Bearer ${opts.token}`,
      'Content-Type': 'application/json',
    },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`API ${opts.method ?? 'GET'} ${path} failed (${res.status}): ${text}`);
  }
  return res.json() as Promise<T>;
}

/** Create a test entity via API with a unique identifier. Returns entity_id. */
export async function createTestEntity(opts: {
  token: string;
  entityTypeId: string;
  identifier?: string;
  data?: Record<string, unknown>;
}): Promise<{ entityId: string; identifier: string }> {
  const identifier = opts.identifier ?? `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  const result = await api<{ entity_id: string }>('/api/entity-records', {
    method: 'POST',
    token: opts.token,
    body: {
      entity_type_id: opts.entityTypeId,
      data: { identifier, title: identifier, ...opts.data },
    },
  });
  return { entityId: result.entity_id, identifier };
}

/** Delete a test entity via API. Silently ignores 404. */
export async function deleteTestEntity(token: string, entityId: string): Promise<void> {
  try {
    await fetch(`${BACKEND_URL}/v1/api/entity-records/${entityId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    // ignore — entity may already be deleted
  }
}

/** Enroll an entity into a workflow. */
export async function enrollEntity(token: string, machineName: string, entityId: string): Promise<void> {
  await api(`/api/workflow-state-machines/${machineName}/enrollments`, {
    method: 'POST',
    token,
    body: { entity_id: entityId },
  });
}

/** Get the entity type ID by name. */
export async function getEntityTypeId(token: string, name: string): Promise<string> {
  const result = await api<{ entity_type_id?: string; id?: string }>(`/api/entity-types/${name}`, {
    token,
  });
  return result.entity_type_id ?? result.id ?? '';
}

/** Get the first active workflow's machine_name. */
export async function getWorkflowMachineName(token: string): Promise<string | null> {
  const result = await api<Record<string, unknown>>(
    '/api/workflow-state-machines',
    { token },
  );
  const items = (Array.isArray(result) ? result : (result as Record<string, unknown>).published_items ?? (result as Record<string, unknown>).items ?? []) as Array<{ machine_name: string; is_active: boolean }>;
  const active = items.find((w) => w.is_active);
  return active?.machine_name ?? null;
}

/** Execute a transition on an entity. */
export async function executeTransition(
  token: string,
  entityId: string,
  trigger: string,
): Promise<void> {
  await api('/api/workflow/transitions', {
    method: 'POST',
    token,
    body: { entity_id: entityId, trigger },
  });
}

/** Get entity type name from the first active workflow. */
export async function getWorkflowEntityType(token: string): Promise<string | null> {
  const result = await api<Record<string, unknown>>(
    '/api/workflow-state-machines',
    { token },
  );
  const items = (Array.isArray(result) ? result : (result as Record<string, unknown>).published_items ?? (result as Record<string, unknown>).items ?? []) as Array<{ entity_type: string; is_active: boolean }>;
  return items.find((w) => w.is_active)?.entity_type ?? null;
}

/** Create a test entity enrolled in a workflow. Cleanup function returned. */
export async function createEnrolledEntity(opts: {
  token: string;
  entityTypeName: string;
  data?: Record<string, unknown>;
}): Promise<{ entityId: string; identifier: string; cleanup: () => Promise<void> }> {
  const entityTypeId = await getEntityTypeId(opts.token, opts.entityTypeName);
  const machineName = await getWorkflowMachineName(opts.token);
  const { entityId, identifier } = await createTestEntity({
    token: opts.token,
    entityTypeId,
    data: opts.data,
  });
  if (machineName) {
    try {
      await enrollEntity(opts.token, machineName, entityId);
    } catch (err) {
      console.warn('Enrollment failed (non-fatal):', err);
    }
  }
  return {
    entityId,
    identifier,
    cleanup: () => deleteTestEntity(opts.token, entityId),
  };
}

/**
 * Create a test entity using the baseline entity type + workflow.
 * Uses the exact machine_name from baseline seed — not a random active workflow.
 */
export async function createBaselineEntity(opts?: {
  token?: string;
  data?: Record<string, unknown>;
}): Promise<{ entityId: string; identifier: string; cleanup: () => Promise<void> }> {
  const token = opts?.token ?? getAuthToken('superadmin');
  const baseline = getBaselineInfo();
  const entityTypeId = baseline?.entityTypeId || await getEntityTypeId(token, BASELINE.entityType);
  const machineName = baseline?.machineName ?? await getWorkflowMachineName(token);
  const { entityId, identifier } = await createTestEntity({
    token,
    entityTypeId,
    data: opts?.data,
  });
  if (machineName) {
    try {
      await enrollEntity(token, machineName, entityId);
    } catch (err) {
      console.warn('Baseline enrollment failed (non-fatal):', err);
    }
  }
  return {
    entityId,
    identifier,
    cleanup: () => deleteTestEntity(token, entityId),
  };
}
