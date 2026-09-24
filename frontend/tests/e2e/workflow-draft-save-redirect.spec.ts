import { expect, test, type APIRequestContext, type Locator, type Page } from '@playwright/test';

import { getPageToken } from './helpers/api-fixtures';
import { BASELINE } from './helpers/baseline-seed';

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

async function createFieldAndMethod(request: APIRequestContext, token: string, suffix: string) {
  const fieldName = `E2E redirect field ${suffix}`;
  const methodName = `E2E redirect method ${suffix}`;
  const field = await api<{
    identity: { library_field_id: string };
    version: { version_id: string };
  }>(request, token, '/field-library/fields', 'POST', {
    name: fieldName,
    field_key: `e2e_redirect_${suffix}`,
    field_type: 'text',
    description: 'Regression fixture for Save-as-draft URL redirect.',
    settings: { required: false },
  });
  const method = await api<{ identity: { method_id: string } }>(
    request,
    token,
    '/method-library/methods',
    'POST',
    {
      name: methodName,
      fields: [
        {
          library_field_id: field.identity.library_field_id,
          version_id: field.version.version_id,
          label: fieldName,
          position: 0,
        },
      ],
    },
  );
  return {
    fieldId: field.identity.library_field_id as string,
    methodId: method.identity.method_id as string,
    methodName,
  };
}

async function attachMethod(section: Locator, methodName: string) {
  await section.locator('select').nth(1).selectOption({ label: methodName });
  await section.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(section.getByText(methodName, { exact: true }).first()).toBeVisible();
}

async function openCanvasStateInspector(page: Page, stateName: string) {
  const stateNode = page.getByText(stateName, { exact: true }).first();
  await expect(stateNode).toBeVisible();
  // Click to select (isActive, persistent) rather than hover (isHover, transient) —
  // CanvasNode.tsx only mounts the "Edit state" button while isHover || isActive.
  await stateNode.click();
  await page.getByTitle('Edit state').first().click();
  await expect(page.getByText('Actions on entry', { exact: true })).toBeVisible();
}

function methodLibrarySection(page: Page) {
  return page.locator('section').filter({ has: page.getByText('Method Library', { exact: true }) });
}

/** Create a version-0 draft, then immediately publish it as version 1 via the
 *  raw API — leaving both rows behind, with DIFFERENT ids, exactly as any
 *  real "publish a workflow, then reopen it later" flow does. */
async function publishFixtureWorkflow(
  request: APIRequestContext,
  token: string,
  suffix: string,
  initialState: string,
  terminalState: string,
): Promise<{ draftId: string; publishedId: string }> {
  const draft = await api<{ id: string; machine_name: string }>(
    request,
    token,
    '/workflow-state-machines/draft',
    'POST',
    { name: `E2E redirect workflow ${suffix}` },
  );
  const published = await api<{ state_machine: { id: string } }>(
    request,
    token,
    `/workflow-state-machines/${draft.id}/publish`,
    'POST',
    {
      definition: {
        machine_key: draft.machine_name,
        name: `E2E redirect workflow ${suffix}`,
        entity_type: BASELINE.entityType,
        entity_schema: {
          entity_type: BASELINE.entityType,
          fields: [
            { field: 'title', type: 'string', required: true, description: 'Title' },
            { field: 'description', type: 'text', required: false, description: 'Description' },
          ],
        },
        states: [
          { name: initialState, tags: ['initial'], order: 1 },
          { name: terminalState, tags: ['terminal'], order: 2 },
        ],
        initial_state: initialState,
        transitions: [
          {
            key: 'finish',
            trigger: 'FINISH',
            label: 'Finish',
            from: initialState,
            to_state: terminalState,
          },
        ],
      },
    },
  );
  return { draftId: draft.id, publishedId: published.state_machine.id };
}

test.describe('Save as draft follows the row it actually wrote to', () => {
  // Each case drives a full create -> publish -> attach -> save -> hard-reload
  // cycle against a live stack, which does not reliably fit the 30s default.
  test.setTimeout(120_000);

  test('Canvas: an already-published workflow keeps its Method after Save as draft + a hard reload', async ({
    page,
    request,
  }) => {
    await page.goto('/settings');
    const token = await getPageToken(page);
    const suffix = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const stateName = `START_${suffix}`;
    const terminalName = `END_${suffix}`;
    let draftId: string | null = null;
    let publishedId: string | null = null;
    let methodId: string | null = null;
    let fieldId: string | null = null;

    try {
      const fixture = await createFieldAndMethod(request, token, suffix);
      methodId = fixture.methodId;
      fieldId = fixture.fieldId;

      const wf = await publishFixtureWorkflow(request, token, suffix, stateName, terminalName);
      draftId = wf.draftId;
      publishedId = wf.publishedId;

      // Open the PUBLISHED row for editing — exactly how reopening a workflow
      // from the Funnels list behaves (useFunnelList.ts selectWorkflow always
      // navigates via the published row's id for a workflow that's been
      // published at least once).
      await page.goto(`/funnel/${publishedId}/edit?view=canvas`);
      await openCanvasStateInspector(page, stateName);
      await expect(methodLibrarySection(page)).toBeVisible();
      await attachMethod(methodLibrarySection(page), fixture.methodName);

      const saveResponse = page.waitForResponse(
        (response) =>
          response.url().includes(`/workflow-state-machines/${draftId}/draft`) &&
          response.request().method() === 'PUT',
      );
      await page.getByRole('button', { name: 'Save as draft' }).click();
      expect((await saveResponse).ok()).toBeTruthy();

      // The URL must follow the draft row that was actually written to, not
      // stay on the published row the page was opened from.
      await expect.poll(() => page.url()).toContain(draftId);
      expect(page.url()).not.toContain(publishedId);

      await page.reload();
      await openCanvasStateInspector(page, stateName);
      await expect(methodLibrarySection(page).getByText(fixture.methodName, { exact: true }).first()).toBeVisible();
    } finally {
      if (draftId) {
        await api(request, token, `/workflow-state-machines/${draftId}`, 'DELETE').catch(() => {});
      }
      if (publishedId) {
        await api(request, token, `/workflow-state-machines/${publishedId}`, 'DELETE').catch(() => {});
      }
      if (methodId) {
        await api(request, token, `/method-library/methods/${methodId}`, 'DELETE').catch(() => {});
      }
      if (fieldId) {
        await api(request, token, `/field-library/fields/${fieldId}/hard`, 'DELETE').catch(() => {});
      }
    }
  });

  test('Wizard: an already-published workflow keeps its Method after Save as draft + a hard reload', async ({
    page,
    request,
  }) => {
    await page.goto('/settings');
    const token = await getPageToken(page);
    const suffix = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const stateName = `START_${suffix}`;
    const terminalName = `END_${suffix}`;
    let draftId: string | null = null;
    let publishedId: string | null = null;
    let methodId: string | null = null;
    let fieldId: string | null = null;

    try {
      const fixture = await createFieldAndMethod(request, token, suffix);
      methodId = fixture.methodId;
      fieldId = fixture.fieldId;

      const wf = await publishFixtureWorkflow(request, token, suffix, stateName, terminalName);
      draftId = wf.draftId;
      publishedId = wf.publishedId;

      await page.goto(`/funnel/${publishedId}/edit?view=wizard`);
      await page.getByRole('button', { name: 'States', exact: true }).click();

      const section = methodLibrarySection(page).first();
      await expect(section).toBeVisible();
      await attachMethod(section, fixture.methodName);

      const saveResponse = page.waitForResponse(
        (response) =>
          response.url().includes(`/workflow-state-machines/${draftId}/draft`) &&
          response.request().method() === 'PUT',
      );
      await page.getByRole('button', { name: 'Save as draft' }).click();
      expect((await saveResponse).ok()).toBeTruthy();

      await expect.poll(() => page.url()).toContain(draftId);
      expect(page.url()).not.toContain(publishedId);

      await page.reload();
      await page.getByRole('button', { name: 'States', exact: true }).click();
      const reopenedSection = methodLibrarySection(page).first();
      await expect(reopenedSection.getByText(fixture.methodName, { exact: true }).first()).toBeVisible();
    } finally {
      if (draftId) {
        await api(request, token, `/workflow-state-machines/${draftId}`, 'DELETE').catch(() => {});
      }
      if (publishedId) {
        await api(request, token, `/workflow-state-machines/${publishedId}`, 'DELETE').catch(() => {});
      }
      if (methodId) {
        await api(request, token, `/method-library/methods/${methodId}`, 'DELETE').catch(() => {});
      }
      if (fieldId) {
        await api(request, token, `/field-library/fields/${fieldId}/hard`, 'DELETE').catch(() => {});
      }
    }
  });

  test('Wizard: a brand-new draft keeps its Method after Save as draft + a hard reload', async ({
    page,
    request,
  }) => {
    await page.goto('/settings');
    const token = await getPageToken(page);
    const suffix = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    let workflowId: string | null = null;
    let methodId: string | null = null;
    let fieldId: string | null = null;

    try {
      const fixture = await createFieldAndMethod(request, token, suffix);
      methodId = fixture.methodId;
      fieldId = fixture.fieldId;

      const workflow = await api<{ id: string }>(
        request,
        token,
        '/workflow-state-machines/draft',
        'POST',
        { name: `E2E redirect brand-new draft ${suffix}` },
      );
      workflowId = workflow.id;

      await page.goto(`/funnel/${workflowId}/edit?view=wizard`);
      await page.getByRole('button', { name: 'States', exact: true }).click();

      const section = methodLibrarySection(page).first();
      await expect(section).toBeVisible();
      await attachMethod(section, fixture.methodName);

      const saveResponse = page.waitForResponse(
        (response) =>
          response.url().includes(`/workflow-state-machines/${workflowId}/draft`) &&
          response.request().method() === 'PUT',
      );
      await page.getByRole('button', { name: 'Save as draft' }).click();
      expect((await saveResponse).ok()).toBeTruthy();

      // A brand-new draft's URL is already the draft row's own id — Save as
      // draft must not move it elsewhere. This must keep passing both before
      // and after the fix (no regression for the already-working case).
      expect(page.url()).toContain(workflowId);

      await page.reload();
      await page.getByRole('button', { name: 'States', exact: true }).click();
      const reopenedSection = methodLibrarySection(page).first();
      await expect(reopenedSection.getByText(fixture.methodName, { exact: true }).first()).toBeVisible();
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
});
