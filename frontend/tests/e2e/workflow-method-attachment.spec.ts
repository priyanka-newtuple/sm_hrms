import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

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

async function openStateInspector(page: Page, workflowId: string, stateName: string) {
  await page.goto(`/funnel/${workflowId}/edit?view=canvas`);
  const stateNode = page.getByText(stateName, { exact: true }).first();
  await expect(stateNode).toBeVisible();
  // Click to select (isActive, persistent) rather than hover (isHover, transient) —
  // CanvasNode.tsx only mounts the "Edit state" button while isHover || isActive,
  // and a hover-then-separately-query-and-click sequence races the mouse leaving
  // the hover region before the second locator resolves.
  await stateNode.click();
  await page.getByTitle('Edit state').first().click();
  await expect(page.getByText('Actions on entry', { exact: true })).toBeVisible();
}

test('an attached Method survives draft save and a fresh workflow reload', async ({
  page,
  request,
}) => {
  await page.goto('/settings');
  const token = await getPageToken(page);
  const suffix = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  const fieldName = `E2E attachment field ${suffix}`;
  const methodName = `E2E attachment method ${suffix}`;
  let workflowId: string | null = null;
  let methodId: string | null = null;
  let fieldId: string | null = null;

  try {
    const field = await api<{
      identity: { library_field_id: string };
      version: { version_id: string };
    }>(request, token, '/field-library/fields', 'POST', {
      name: fieldName,
      field_key: `e2e_attachment_${suffix}`,
      field_type: 'text',
      description: 'Regression fixture for workflow Method attachment.',
      settings: { required: false },
    });
    fieldId = field.identity.library_field_id;

    const method = await api<{
      identity: { method_id: string };
      version: { version_id: string };
    }>(request, token, '/method-library/methods', 'POST', {
      name: methodName,
      fields: [
        {
          library_field_id: fieldId,
          version_id: field.version.version_id,
          label: fieldName,
          position: 0,
        },
      ],
    });
    methodId = method.identity.method_id;

    const workflow = await api<{
      id: string;
      definition: { states: Array<{ name: string; method_refs?: unknown[] }> };
    }>(request, token, '/workflow-state-machines/draft', 'POST', {
      name: `E2E Method attachment ${suffix}`,
    });
    workflowId = workflow.id;
    const stateName = workflow.definition.states[0].name;

    await openStateInspector(page, workflowId, stateName);
    const methodSection = page.locator('section').filter({
      has: page.getByText('Method Library', { exact: true }),
    });
    await expect(methodSection).toBeVisible();
    await methodSection.locator('select').nth(1).selectOption({ label: methodName });
    await methodSection.getByRole('button', { name: 'Add', exact: true }).click();
    await expect(methodSection.getByText(methodName, { exact: true }).first()).toBeVisible();

    const saveResponse = page.waitForResponse(
      (response) =>
        response.url().includes(`/workflow-state-machines/${workflowId}/draft`) &&
        response.request().method() === 'PUT',
    );
    await page.getByRole('button', { name: 'Save as draft' }).click();
    expect((await saveResponse).ok()).toBeTruthy();

    const persisted = await api<{
      definition: { states: Array<{ name: string; method_refs?: Array<{ method_id: string }> }> };
    }>(request, token, `/workflow-state-machines/${workflowId}`);
    expect(persisted.definition.states[0].method_refs).toEqual([
      expect.objectContaining({ method_id: methodId }),
    ]);

    await page.goto('/settings');
    await openStateInspector(page, workflowId, stateName);
    await expect(page.getByText(methodName, { exact: true }).first()).toBeVisible();
  } finally {
    if (workflowId) {
      await api(request, token, `/workflow-state-machines/${workflowId}`, 'DELETE').catch(() => {});
    }
    if (methodId) {
      await api(request, token, `/method-library/methods/${methodId}`, 'DELETE').catch(() => {});
    }
    if (fieldId) {
      await api(request, token, `/field-library/fields/${fieldId}/hard`, 'DELETE').catch(() => {});
    }
  }
});
