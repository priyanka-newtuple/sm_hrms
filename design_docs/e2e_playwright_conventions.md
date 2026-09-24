# E2E Playwright Testing Conventions

## Selector Priority (in order)

| Priority | Selector | When to use |
|---|---|---|
| 1 | `getByRole('button', { name: /label/i })` | All interactive elements — buttons, tabs, links |
| 2 | `getByLabel(/label/i)` | Form inputs with associated labels |
| 3 | `getByPlaceholder(/text/i)` | Inputs without labels |
| 4 | `getByTestId('my-element')` | Non-interactive elements with no role (chips, badges, counters) |
| 5 | `getByText(/regex/i)` | **User-generated content only** (entity names, comments) |

**Never** use `getByText('Exact Label')` for UI labels — these break when a fork renames the label.

## When to add `data-testid`

Add `data-testid` to a component **in the same PR** as the test that uses it.

```tsx
// src component — add when writing the test
<span data-testid="pipeline-entity-count">{count}</span>

// spec — use it
await expect(page.getByTestId('pipeline-entity-count')).toBeVisible();
```

Only needed for elements with no natural ARIA role. If `getByRole` works, use that instead.

## Test Structure Rules

### 1. Each test is self-sufficient

Tests must not depend on prior test state. Never use `beforeAll` to create shared mutable state.

```ts
// Bad — test 2 depends on test 1 having run
test('create entity', async ({ page }) => { /* creates entity */ });
test('edit entity', async ({ page }) => { /* assumes entity exists */ });

// Good — each test creates what it needs
test('edit entity', async ({ page }) => {
  const { identifier, cleanup } = await createBaselineEntity();
  try {
    // ...
  } finally { await cleanup(); }
});
```

### 2. Mutable data is unique per test run

Use `Date.now()` for any name that must be unique:

```ts
await nameInput.fill(`E2E Role ${Date.now()}`);
```

### 3. Cleanup always runs

Wrap entity-creating tests in `try/finally`:

```ts
const { identifier, cleanup } = await createBaselineEntity();
try {
  // test body
} finally {
  await cleanup(); // always runs even if test fails
}
```

### 4. Stable baseline data is OK

Static data (seeded once in `global-setup`) is fine for read-only tests. The baseline seed (`tests/e2e/helpers/baseline-seed.ts`) provides:
- Workflow: **E2E Baseline Workflow**
- Entity type: **E2EBaseline**
- States: OPEN, IN_PROGRESS, DONE
- Form: identifier + title fields

### 5. Use regex for baseline references

Match baseline names with case-insensitive regex so minor renames don't break tests:

```ts
// Good
page.getByRole('button', { name: /E2E Baseline Workflow/i })
page.getByRole('button', { name: /add e2ebaseline/i })

// Bad
page.getByText('E2E Baseline Workflow')
```

## Pending Improvements (future work)

These brittle `getByText` calls should be replaced with `getByRole` when touching those spec files:

| Spec | Brittle selector | Replace with |
|---|---|---|
| entity detail tests | `getByText('Comments')` | `getByRole('tab', { name: /comments/i })` |
| entity detail tests | `getByText('Activity')` | `getByRole('tab', { name: /activity/i })` |
| dashboard tests | `getByText('Add widget')` | `getByRole('button', { name: /add widget/i })` |
| dashboard tests | `getByText('Editing')` | `getByRole('status')` or `getByText(/editing/i)` |
| settings tests | `getByText('Form Configuration')` | `getByRole('heading', { name: /form configuration/i })` |
| dashboard widget titles | `getByText('Active Entities')` | Add `data-testid="widget-active-entities"` to widget |
| dashboard widget titles | `getByText('SLA Breaches')` | Add `data-testid="widget-sla-breaches"` to widget |
| dashboard widget titles | `getByText('Recent Events')` | Add `data-testid="widget-recent-events"` to widget |
| dashboard widget titles | `getByText('Pipeline by State')` | Add `data-testid="widget-pipeline-by-state"` to widget |

Do these replacements when the relevant spec file is being modified for another reason — not as a standalone refactor.
