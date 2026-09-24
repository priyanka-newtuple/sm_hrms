import { expect, test, type APIRequestContext } from '@playwright/test';

import { BASELINE } from './helpers/baseline-seed';
import { getPageToken } from './helpers/api-fixtures';

const BACKEND_URL = process.env.VITE_DEV_PROXY_TARGET ?? 'http://localhost:8001';

async function api<T>(
  request: APIRequestContext,
  token: string,
  path: string,
  method = 'GET',
  body?: Record<string, unknown>,
): Promise<T> {
  const response = await request.fetch(`${BACKEND_URL}/v1/api${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}` },
    data: body,
  });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBeTruthy();
  return response.json() as Promise<T>;
}

async function createMethod(
  request: APIRequestContext,
  token: string,
  suffix: string,
  name: string,
) {
  const field = await api<{
    identity: { library_field_id: string };
    version: { version_id: string };
  }>(request, token, '/field-library/fields', 'POST', {
    name: `${name} field`,
    field_key: `e2e_records_${suffix}_${name.toLowerCase().replaceAll(' ', '_')}`,
    field_type: 'text',
    settings: { required: false },
  });
  const method = await api<{ identity: { method_id: string } }>(
    request,
    token,
    '/method-library/methods',
    'POST',
    {
      name,
      entity_types: [BASELINE.entityType],
      fields: [{
        library_field_id: field.identity.library_field_id,
        version_id: field.version.version_id,
        label: `${name} field`,
        position: 0,
      }],
    },
  );
  return { fieldId: field.identity.library_field_id, methodId: method.identity.method_id };
}

async function publishWorkflow(
  request: APIRequestContext,
  token: string,
  name: string,
  initialState: string,
  methodId?: string,
): Promise<{ draftId: string; publishedId: string; machineName: string }> {
  const draft = await api<{ id: string; machine_name: string }>(
    request,
    token,
    '/workflow-state-machines/draft',
    'POST',
    { name },
  );
  const published = await api<{ state_machine: { id: string } }>(
    request,
    token,
    `/workflow-state-machines/${draft.id}/publish`,
    'POST',
    {
      definition: {
        machine_key: draft.machine_name,
        name,
        entity_type: BASELINE.entityType,
        entity_schema: { entity_type: BASELINE.entityType, fields: [] },
        states: [
          {
            name: initialState,
            tags: ['initial'],
            order: 1,
            method_refs: methodId ? [{ method_id: methodId }] : [],
          },
          { name: `DONE_${initialState}`, tags: ['terminal'], order: 2, method_refs: [] },
        ],
        initial_state: initialState,
        transitions: [{
          key: 'finish',
          trigger: 'FINISH',
          label: 'Finish',
          from: initialState,
          to_state: `DONE_${initialState}`,
        }],
      },
    },
  );
  return { draftId: draft.id, publishedId: published.state_machine.id, machineName: draft.machine_name };
}

test.setTimeout(180_000);

test('Records scopes forms to the selected workflow initial state', async ({ page, request }) => {
  await page.goto('/settings');
  const token = await getPageToken(page);
  const suffix = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  const methodAName = `E2E Records form A ${suffix}`;
  const methodBName = `E2E Records form B ${suffix}`;
  const workflowName = `E2E Records workflow ${suffix}`;
  const emptyWorkflowName = `E2E Records empty workflow ${suffix}`;
  let methodA: Awaited<ReturnType<typeof createMethod>> | null = null;
  let methodB: Awaited<ReturnType<typeof createMethod>> | null = null;
  let workflow: Awaited<ReturnType<typeof publishWorkflow>> | null = null;
  let emptyWorkflow: Awaited<ReturnType<typeof publishWorkflow>> | null = null;

  try {
    methodA = await createMethod(request, token, suffix, methodAName);
    methodB = await createMethod(request, token, suffix, methodBName);
    workflow = await publishWorkflow(request, token, workflowName, `INITIAL_${suffix}`, methodA.methodId);
    emptyWorkflow = await publishWorkflow(request, token, emptyWorkflowName, `EMPTY_${suffix}`);

    await page.goto(`/records/${encodeURIComponent(BASELINE.entityType)}`);
    await page.getByRole('button', { name: `Add ${BASELINE.entityType}`, exact: true }).click();
    await expect(page.getByRole('button', { name: methodAName, exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: methodBName, exact: true })).toBeVisible();

    const workflowSelect = page.locator('#workflow-select');
    await workflowSelect.selectOption({ label: workflowName });
    await expect(page.getByText(methodAName, { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: methodBName, exact: true })).not.toBeVisible();

    await workflowSelect.selectOption({ label: emptyWorkflowName });
    await expect(
      page.getByText('No forms are configured for this workflow’s initial state.'),
    ).toBeVisible();
    await expect(page.getByRole('button', { name: 'Create', exact: true })).toBeEnabled();
  } finally {
    for (const item of [workflow, emptyWorkflow]) {
      if (item) {
        await api(request, token, `/workflow-state-machines/${item.draftId}`, 'DELETE').catch(() => {});
        await api(request, token, `/workflow-state-machines/${item.publishedId}`, 'DELETE').catch(() => {});
      }
    }
    for (const item of [methodA, methodB]) {
      if (item) {
        await api(request, token, `/method-library/methods/${item.methodId}`, 'DELETE').catch(() => {});
        await api(request, token, `/field-library/fields/${item.fieldId}/hard`, 'DELETE').catch(() => {});
      }
    }
  }
});
