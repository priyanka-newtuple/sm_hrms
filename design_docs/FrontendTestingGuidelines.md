# Frontend Testing Guidelines (Playwright E2E)

Use this file as the single source of truth for writing Playwright E2E tests in frontend projects.

## How to use this guideline in prompts

When asking AI or engineers to write tests, reference this file explicitly:

`Follow /Users/mac/super-msp/root/docs/frontend/FrontendTestingGuidlines.MD for Playwright structure and standards.`

## Goals

- Keep test structure consistent across projects.
- Reduce flaky tests.
- Keep scenarios business-focused (user behavior, not implementation details).
- Make failures easy to debug.

## Folder and file conventions

- Test root: `tests/e2e/`
- One feature per file.
- File naming: `<feature>.spec.ts`
- Group related checks using `test.describe("<Feature>")`.
- Add tags in test titles when needed: `@smoke`, `@regression`, `@critical`.

Example:

```text
tests/e2e/
  auth.spec.ts
  invitations.spec.ts
  customer-portfolio.spec.ts
```

## Required test structure

Every test should follow this order:

1. `Arrange`: prepare state/data.
2. `Act`: perform user actions.
3. `Assert`: verify user-visible outcomes.

Minimal template:

```ts
import { test, expect } from "@playwright/test";

test.describe("Feature Name", () => {
  test("does expected behavior @smoke", async ({ page }) => {
    // Arrange
    await page.goto("/");

    // Act
    await page.getByRole("button", { name: "Sign in with Microsoft" }).click();

    // Assert
    await expect(page).toHaveURL(/microsoft/i);
  });
});
```

## Selector policy (strict)

Use selectors in this priority order:

1. `getByRole(...)`
2. `getByLabel(...)`
3. `getByPlaceholder(...)`
4. `getByText(...)` (only if stable and unique)
5. `getByTestId(...)` (when accessibility selectors are not practical)

Avoid:

- CSS selectors tied to styling classes.
- `nth()` unless there is no better option.
- Arbitrary sleeps (`waitForTimeout`) except temporary debugging.

## Assertions policy

- Always assert outcomes, not only actions.
- Use web-first assertions (`await expect(...).toBeVisible()` etc.).
- Assert URL, important text, and key CTA visibility for major flows.
- For forms, assert both success and validation error states.

## Network and data handling

- Prefer real integration for critical flows.
- Mock only when external dependency is unstable/costly/unavailable.
- If mocking, use `page.route()` and keep fixtures in `tests/fixtures/`.
- Keep test data deterministic and unique when needed (timestamp suffix).

## Stability rules

- Do not share mutable state between tests.
- Each test must be independently runnable.
- Use `beforeEach` only for common safe setup.
- Clean up created entities when applicable.
- Keep retries as safety net, not as a fix for flaky logic.

## Authentication guidance

- Prefer login through UI for one smoke path.
- For wider suites, use saved auth state (if project supports it) to reduce runtime.
- Never hardcode secrets in test files.
- Read credentials from environment variables.

## Debug and reporting

- Enable trace/video/screenshot on failure via Playwright config.
- Add clear assertion messages where helpful.
- Keep steps logically separated for easier trace reading.

## PR checklist for E2E tests

- Uses the required Arrange/Act/Assert structure.
- Uses selector policy correctly.
- Has meaningful assertions.
- No flaky waits.
- Passes locally and in CI.
- Test names clearly describe behavior.

## Project command examples

```bash
npx  playwright test --ui
npx  playwright test --headed
npx  playwright test
```

## Definition of done for a new E2E scenario

- Added in correct file under `tests/e2e/`.
- Covers happy path and at least one failure/validation path.
- Stable in at least 3 consecutive local runs.
- Included in CI pipeline where appropriate.
