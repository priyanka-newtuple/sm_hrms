import { expect, test, type APIRequestContext } from '@playwright/test';

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

test("Wizard Guards field picker is scoped to each state's own attached Method Block", async ({
  page,
  request,
}) => {
  await page.goto('/settings');
  const token = await getPageToken(page);
  const suffix = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

  const field1Name = `E2E scope field A ${suffix}`;
  const field1Key = `e2e_scope_a_${suffix}`;
  const field2Name = `E2E scope field B ${suffix}`;
  const field2Key = `e2e_scope_b_${suffix}`;
  const method1Name = `E2E scope method A ${suffix}`;
  const method2Name = `E2E scope method B ${suffix}`;
  const s1 = `S1_${suffix}`;
  const s2 = `S2_${suffix}`;
  const s3 = `S3_${suffix}`;

  let workflowId: string | null = null;
  let method1Id: string | null = null;
  let method2Id: string | null = null;
  let field1Id: string | null = null;
  let field2Id: string | null = null;

  try {
    const field1 = await api<{
      identity: { library_field_id: string };
      version: { version_id: string };
    }>(request, token, '/field-library/fields', 'POST', {
      name: field1Name,
      field_key: field1Key,
      field_type: 'text',
      description: 'Regression fixture for Guards state scoping.',
      settings: { required: false },
    });
    field1Id = field1.identity.library_field_id;

    const field2 = await api<{
      identity: { library_field_id: string };
      version: { version_id: string };
    }>(request, token, '/field-library/fields', 'POST', {
      name: field2Name,
      field_key: field2Key,
      field_type: 'text',
      description: 'Regression fixture for Guards state scoping.',
      settings: { required: false },
    });
    field2Id = field2.identity.library_field_id;

    const method1 = await api<{ identity: { method_id: string } }>(
      request,
      token,
      '/method-library/methods',
      'POST',
      {
        name: method1Name,
        fields: [
          {
            library_field_id: field1Id,
            version_id: field1.version.version_id,
            label: field1Name,
            position: 0,
          },
        ],
      },
    );
    method1Id = method1.identity.method_id;

    const method2 = await api<{ identity: { method_id: string } }>(
      request,
      token,
      '/method-library/methods',
      'POST',
      {
        name: method2Name,
        fields: [
          {
            library_field_id: field2Id,
            version_id: field2.version.version_id,
            label: field2Name,
            position: 0,
          },
        ],
      },
    );
    method2Id = method2.identity.method_id;

    const workflow = await api<{ id: string; machine_key: string }>(
      request,
      token,
      '/workflow-state-machines/draft',
      'POST',
      { name: `E2E scope workflow ${suffix}` },
    );
    workflowId = workflow.id;

    // 3 states + 2 transitions, so each of the first two states has its own
    // outgoing transition to check Guards scoping against: S1 -> S2 -> S3.
    await api(request, token, `/workflow-state-machines/${workflowId}/draft`, 'PUT', {
      definition: {
        machine_key: workflow.machine_key,
        name: `E2E scope workflow ${suffix}`,
        description: null,
        entity_type: 'entity',
        entity_schema: { entity_type: 'entity', fields: [] },
        states: [
          { name: s1, description: '', tags: ['initial'], order: 1, on_state_actions: [], sla_seconds: null, method_refs: [] },
          { name: s2, description: '', tags: [], order: 2, on_state_actions: [], sla_seconds: null, method_refs: [] },
          { name: s3, description: '', tags: ['terminal'], order: 3, on_state_actions: [], sla_seconds: null, method_refs: [] },
        ],
        initial_state: s1,
        transitions: [
          {
            key: 'advance', trigger: 'advance', label: 'Advance', from: s1, to_state: s2,
            required_fields: [], guards: [], pre_transition_tasks: [], post_transition_tasks: [],
            auto_transition: null, description: '',
          },
          {
            key: 'complete', trigger: 'complete', label: 'Complete', from: s2, to_state: s3,
            required_fields: [], guards: [], pre_transition_tasks: [], post_transition_tasks: [],
            auto_transition: null, description: '',
          },
        ],
      },
    });

    await page.goto(`/funnel/${workflowId}/edit?view=wizard`);
    await page.getByRole('button', { name: 'States', exact: true }).click();

    // Attach method1 to S1, method2 to S2, via the Wizard's new Method Library
    // control (StateMethodsSection, reused the same way as StateActionsSection).
    const methodSections = page.locator('section').filter({
      has: page.getByText('Method Library', { exact: true }),
    });
    await expect(methodSections).toHaveCount(3);

    const sectionS1 = methodSections.nth(0);
    await sectionS1.locator('select').nth(1).selectOption({ label: method1Name });
    await sectionS1.getByRole('button', { name: 'Add', exact: true }).click();
    await expect(sectionS1.getByText(method1Name, { exact: true }).first()).toBeVisible();

    const sectionS2 = methodSections.nth(1);
    await sectionS2.locator('select').nth(1).selectOption({ label: method2Name });
    await sectionS2.getByRole('button', { name: 'Add', exact: true }).click();
    await expect(sectionS2.getByText(method2Name, { exact: true }).first()).toBeVisible();

    // The field preview (Step 3) should also reflect the scoped list — the
    // field key is unique to this test run, so a page-wide check is unambiguous.
    await expect(page.getByText(field1Key, { exact: false }).first()).toBeVisible();

    const saveResponse = page.waitForResponse(
      (response) =>
        response.url().includes(`/workflow-state-machines/${workflowId}/draft`) &&
        response.request().method() === 'PUT',
    );
    await page.getByRole('button', { name: 'Save as draft' }).click();
    expect((await saveResponse).ok()).toBeTruthy();

    // Guards tab: S1 -> S2's field picker must offer only field1; S2 -> S3's
    // must offer only field2 — never both, never the other state's field.
    await page.getByRole('button', { name: 'Guards', exact: true }).click();

    await page.getByText(`${s1} → ${s2}`, { exact: true }).click();
    await page.getByRole('button', { name: 'Field is present', exact: true }).click();
    const fieldSelectS1 = page
      .locator('select')
      .filter({ has: page.locator(`option[value="${field1Key}"]`) });
    await expect(fieldSelectS1).toHaveCount(1);
    await expect(fieldSelectS1.locator('option')).toHaveCount(2); // placeholder + field1 only

    await page.getByText(`${s2} → ${s3}`, { exact: true }).click();
    await page.getByRole('button', { name: 'Field is present', exact: true }).click();
    const fieldSelectS2 = page
      .locator('select')
      .filter({ has: page.locator(`option[value="${field2Key}"]`) });
    await expect(fieldSelectS2).toHaveCount(1);
    await expect(fieldSelectS2.locator('option')).toHaveCount(2); // placeholder + field2 only
  } finally {
    if (workflowId) {
      await api(request, token, `/workflow-state-machines/${workflowId}`, 'DELETE').catch(() => {});
    }
    if (method1Id) {
      await api(request, token, `/method-library/methods/${method1Id}`, 'DELETE').catch(() => {});
    }
    if (method2Id) {
      await api(request, token, `/method-library/methods/${method2Id}`, 'DELETE').catch(() => {});
    }
    if (field1Id) {
      await api(request, token, `/field-library/fields/${field1Id}/hard`, 'DELETE').catch(() => {});
    }
    if (field2Id) {
      await api(request, token, `/field-library/fields/${field2Id}/hard`, 'DELETE').catch(() => {});
    }
  }
});
