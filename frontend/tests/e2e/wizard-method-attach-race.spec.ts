import { expect, test, type APIRequestContext } from '@playwright/test';

import { getPageToken } from './helpers/api-fixtures';

const BACKEND_URL = process.env.VITE_DEV_PROXY_TARGET ?? 'http://localhost:8001';
// A real, pre-existing entity type that has at least one registered form —
// the race only reproduces when the delayed formSchemas.list() response is
// non-empty (an empty response is a no-op in the effect, race or not).
const RACE_ENTITY_TYPE = 'perkin_client';

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
  const fieldName = `E2E race field ${suffix}`;
  const methodName = `E2E race method ${suffix}`;
  const field = await api<{
    identity: { library_field_id: string };
    version: { version_id: string };
  }>(request, token, '/field-library/fields', 'POST', {
    name: fieldName,
    field_key: `e2e_race_${suffix}`,
    field_type: 'text',
    description: 'Regression fixture for the Wizard method-attach race condition.',
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

// Deliberately slow: this test injects a 4s delay on /forms/config and then
// waits past it to force the race ordering, so it cannot fit the 30s default.
test.setTimeout(120_000);

test('Wizard: a Method attached while the entity-type form-schema fetch is still in flight survives Save as draft', async ({
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

    // The bug is a race: FunnelBuilder's form-schema re-sync effect (fired when
    // BasicsStep's entity-type picker changes) closes over the document as of
    // that render, and if the user attaches a Method before that fetch
    // resolves, its stale `onChange` overwrites the attach. Delaying the
    // response makes this deterministic instead of a timing gamble.
    await page.route('**/forms/config**', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await route.continue();
    });

    const workflow = await api<{ id: string }>(
      request,
      token,
      '/workflow-state-machines/draft',
      'POST',
      { name: `E2E race workflow ${suffix}` },
    );
    workflowId = workflow.id;

    await page.goto(`/funnel/${workflowId}/edit?view=wizard`);

    // Basics: pick a real entity type — this is what fires the form-schema
    // re-sync effect (a brand-new draft's default sentinel entity_type skips
    // it entirely, so this step is required to reproduce the race).
    await expect(
      page.locator(`#entity-type option[value="${RACE_ENTITY_TYPE}"]`),
    ).toBeAttached({ timeout: 15000 });
    const formsConfigResponse = page.waitForResponse((r) => r.url().includes('/forms/config'), {
      timeout: 20000,
    });
    await page.locator('#entity-type').selectOption(RACE_ENTITY_TYPE);

    // Move to States and attach the method immediately — well before the
    // deliberately-delayed forms/config response resolves.
    await page.getByRole('button', { name: 'States', exact: true }).click();
    const section = page
      .locator('section')
      .filter({ has: page.getByText('Method Library', { exact: true }) })
      .first();
    await expect(section).toBeVisible();
    await section.locator('select').nth(1).selectOption({ label: fixture.methodName });
    await section.getByRole('button', { name: 'Add', exact: true }).click();
    await expect(section.getByText(fixture.methodName, { exact: true }).first()).toBeVisible();

    // Let the delayed effect actually resolve before saving — the bug is that
    // its stale `onChange` fires and reverts the attach sometime after it
    // lands, not necessarily the instant the response arrives, so give the
    // resulting re-render a moment to settle too.
    await formsConfigResponse;
    await page.waitForTimeout(300);

    const saveRequest = page.waitForRequest(
      (req) =>
        req.url().includes(`/workflow-state-machines/${workflowId}/draft`) &&
        req.method() === 'PUT',
    );
    const saveResponse = page.waitForResponse(
      (response) =>
        response.url().includes(`/workflow-state-machines/${workflowId}/draft`) &&
        response.request().method() === 'PUT',
    );
    await page.getByRole('button', { name: 'Save as draft' }).click();

    // The actual outgoing payload, not just what the UI renders — this is
    // the whole point of the bug: the UI can look right while the request
    // body sent to the server is already wrong.
    const request_ = await saveRequest;
    const body = request_.postDataJSON() as {
      definition: { states: Array<{ name: string; method_refs?: Array<{ method_id: string }> }> };
    };
    expect((await saveResponse).ok()).toBeTruthy();

    const initialState = body.definition.states.find((s) => s.name === 'INITIAL');
    expect(initialState?.method_refs).toEqual([
      expect.objectContaining({ method_id: methodId }),
    ]);

    // The artificial delay has served its purpose (forcing the race during the
    // attach). Drop it before reloading so hydration runs at normal speed —
    // leaving it armed makes the reload's own forms/config fetch hang.
    await page.unroute('**/forms/config**');

    // Hard reload — real hydration from scratch, not a same-session tab switch.
    await page.reload();
    await page.getByRole('button', { name: 'States', exact: true }).click();
    const reopenedSection = page
      .locator('section')
      .filter({ has: page.getByText('Method Library', { exact: true }) })
      .first();
    // The method itself being rendered after a from-scratch reload is the
    // assertion that matters: it can only be there if the ref survived the
    // save. The "N selected" badge is derived from the same array, so
    // asserting it too adds no coverage and only adds selector flake.
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
