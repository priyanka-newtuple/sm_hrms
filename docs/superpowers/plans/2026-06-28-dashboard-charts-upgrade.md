# Dashboard Charts & KPI Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a themeable shadcn charting foundation, a workflow-ordered funnel with conversion %, and a full KPI suite (period delta, sparkline, gauge) to the customizable dashboard.

**Architecture:** Backend metrics are pure parameterized query functions in `backend/dashboard/metrics.py` returning untyped dict payloads (`series` / `scalar` / `rows`); we add a `gauge` payload and extend `scalar` with `prevValue` + `trend`. The frontend renders payloads through presentational components (`DashboardChart`, `DashboardStat`, new `DashboardGauge`) selected by `WidgetBody` in `DashboardPage.tsx`. Chart colors move from a hardcoded JS palette to CSS variables (`--chart-1..8`).

**Tech Stack:** Backend — FastAPI, SQLAlchemy 1.4, Pydantic, PostgreSQL, Python 3.12, pytest. Frontend — React 19, TypeScript (strict), Vite, Tailwind CSS v4, Recharts 3.6, shadcn/ui (base-mira style).

## Global Constraints

- **Do NOT `git add` or commit any changes.** Per the user's instruction on 2026-06-28, all new work stays in the working tree **unstaged** for the user to review. The files already staged before this plan must remain staged and untouched. Each task therefore ends with a **verification checkpoint**, not a commit.
- **Frontend has no unit-test runner** (the only script is `build`: `tsc -b && vite build`). Frontend "tests" = `cd frontend && npm run build` passing cleanly, plus a stated manual browser check. `tsc -b` (project-references build) is stricter than `tsc --noEmit` and catches Recharts type errors — always use the full `npm run build`.
- **Backend pure helpers get real pytest TDD.** DB-bound metric functions are verified by extracting their pure logic (ordering, window math) into unit-testable helpers; the integration test harness (`backend/tests/conftest.py`) uses a real Postgres schema and is out of scope for per-task TDD here.
- **Payload is an untyped passthrough** — no Pydantic response-schema changes. Only the frontend TS union in `frontend/src/core/types/index.ts` changes.
- **Org scoping:** every backend query filters by `organization_id`. Follow the existing pattern in `metrics.py`.
- **Backend test command:** `cd backend && python -m pytest tests/test_dashboard_metrics.py -v` (new file created in Task B1).

---

## File Structure

**Create:**
- `frontend/src/components/ui/chart.tsx` — shadcn chart primitives (vendored).
- `frontend/src/core/components/DashboardGauge.tsx` — radial gauge for bounded ratios.
- `backend/tests/test_dashboard_metrics.py` — unit tests for pure metric helpers.

**Modify:**
- `frontend/src/index.css` — extend `--chart-*` to 8 brand colors + theme tokens + dark variants.
- `frontend/src/core/components/DashboardChart.tsx` — palette from CSS vars; funnel conversion labels.
- `frontend/src/core/components/DashboardStat.tsx` — inline sparkline.
- `frontend/src/core/components/index.ts` — export `DashboardGauge`.
- `frontend/src/core/types/index.ts` — extend `DashboardWidgetData`, `DashboardViz`, `DashboardWidgetType`.
- `frontend/src/pages/DashboardPage.tsx` — `gauge` widget kind in builder + `WidgetBody`.
- `backend/dashboard/metrics.py` — funnel metric, prevValue, trend, gauge metric + helpers.

---

## Part A — shadcn charting foundation (frontend only)

### Task A1: Install chart primitives and extend the CSS palette

**Files:**
- Create: `frontend/src/components/ui/chart.tsx`
- Modify: `frontend/src/index.css` (`@theme inline` block ~line 24-28; `:root` ~line 220-224; `.dark` ~line 266-270)

**Interfaces:**
- Produces: `ChartContainer`, `ChartTooltip`, `ChartTooltipContent`, `ChartLegend`, `ChartLegendContent`, and the `ChartConfig` type, all exported from `@/components/ui/chart`. CSS color tokens `--color-chart-1 … --color-chart-8` resolvable in SVG fills/strokes.

- [ ] **Step 1: Vendor the shadcn chart component**

The project is already a shadcn project (`frontend/components.json`, style `base-mira`). Install the chart primitive via the CLI, which writes the canonical, Recharts-3-compatible file:

```bash
cd frontend && npx shadcn@latest add chart --yes
```

Expected: creates `src/components/ui/chart.tsx` exporting `ChartContainer`, `ChartTooltip`, `ChartTooltipContent`, `ChartLegend`, `ChartLegendContent`, and type `ChartConfig`. It may also append `--chart-*` vars to `index.css` — that's fine; Step 3/4 will set the exact values.

If the CLI cannot run offline, create `src/components/ui/chart.tsx` manually from https://ui.shadcn.com/docs/components/base/chart (the "Installation → Manual" tab) — it depends only on `recharts`, `react`, and `@/lib/utils` (`cn`), all already present.

- [ ] **Step 2: Verify the import surface**

Run: `cd frontend && grep -n "export" src/components/ui/chart.tsx`
Expected: lines exporting `ChartContainer`, `ChartTooltipContent`, `ChartLegendContent`, `ChartConfig` (names must match exactly; later tasks import these).

- [ ] **Step 3: Set the 8-color brand palette in `:root`**

In `frontend/src/index.css`, replace the five grayscale chart vars under `:root` (currently lines ~220-224):

```css
    --chart-1: oklch(0.87 0 0);
    --chart-2: oklch(0.556 0 0);
    --chart-3: oklch(0.439 0 0);
    --chart-4: oklch(0.371 0 0);
    --chart-5: oklch(0.269 0 0);
```

with the brand palette extended to eight colors:

```css
    --chart-1: #0047AB;
    --chart-2: #3730A3;
    --chart-3: #7C3AED;
    --chart-4: #F59E0B;
    --chart-5: #EA580C;
    --chart-6: #059669;
    --chart-7: #DC2626;
    --chart-8: #0EA5E9;
```

- [ ] **Step 4: Mirror the palette in `.dark` and register theme tokens**

In the `.dark` block (currently lines ~266-270), replace the five grayscale chart vars with the same eight values as Step 3 (the brand colors read acceptably on dark; a separate dark tuning is out of scope per the spec).

Then in the `@theme inline` block, replace the five `--color-chart-*` lines (currently lines ~24-28) with eight, so Tailwind exposes `text-chart-*` / fill utilities and the raw vars resolve:

```css
    --color-chart-8: var(--chart-8);
    --color-chart-7: var(--chart-7);
    --color-chart-6: var(--chart-6);
    --color-chart-5: var(--chart-5);
    --color-chart-4: var(--chart-4);
    --color-chart-3: var(--chart-3);
    --color-chart-2: var(--chart-2);
    --color-chart-1: var(--chart-1);
```

- [ ] **Step 5: Verification checkpoint**

Run: `cd frontend && npm run build`
Expected: build succeeds (only the pre-existing chunk-size warning). Do NOT `git add`. Manual check deferred to A2 (palette is consumed there).

---

### Task A2: Drive DashboardChart palette from CSS variables

**Files:**
- Modify: `frontend/src/core/components/DashboardChart.tsx` (`CHART_PALETTE` ~lines 35-44)

**Interfaces:**
- Consumes: `--color-chart-1 … --color-chart-8` from Task A1.
- Produces: `CHART_PALETTE` (still exported) now holding CSS-var references; same length (8) and same export name so existing importers are unaffected.

- [ ] **Step 1: Replace the hardcoded palette with CSS-var references**

In `frontend/src/core/components/DashboardChart.tsx`, replace:

```ts
export const CHART_PALETTE = [
  '#0047AB',
  '#3730A3',
  '#7C3AED',
  '#F59E0B',
  '#EA580C',
  '#059669',
  '#DC2626',
  '#0EA5E9',
];
```

with:

```ts
export const CHART_PALETTE = [
  'var(--color-chart-1)',
  'var(--color-chart-2)',
  'var(--color-chart-3)',
  'var(--color-chart-4)',
  'var(--color-chart-5)',
  'var(--color-chart-6)',
  'var(--color-chart-7)',
  'var(--color-chart-8)',
];
```

These resolve as SVG `fill`/`stop-color` values, so `Cell fill`, gradients, and `CHART_PALETTE[0]` references keep working unchanged.

- [ ] **Step 2: Verification checkpoint**

Run: `cd frontend && npm run build`
Expected: passes clean.

Manual: `cd frontend && npm run dev`, open the dashboard, confirm bar/pie/funnel/area charts render with the cobalt-led brand colors (identical to before, now sourced from CSS vars). Do NOT `git add`.

---

## Part B — Funnel conversion % (backend + workflow-ordered)

### Task B1: Pure state-ordering helper (TDD)

**Files:**
- Modify: `backend/dashboard/metrics.py` (add helper near `_pipeline_by_state`, ~line 220)
- Create: `backend/tests/test_dashboard_metrics.py`

**Interfaces:**
- Produces: `order_series_by_states(series: list[dict], state_order: list[str]) -> list[dict]` — reorders `[{"label","value"}]` so labels follow `state_order`; states in `state_order` missing from `series` are appended with `value: 0`; labels not in `state_order` keep their original relative order at the end.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_dashboard_metrics.py`:

```python
from __future__ import annotations

from dashboard.metrics import order_series_by_states


def test_orders_series_by_state_order():
    series = [
        {"label": "PANEL", "value": 3},
        {"label": "APPLIED", "value": 10},
        {"label": "SCREENING", "value": 6},
    ]
    order = ["APPLIED", "SCREENING", "PANEL"]
    result = order_series_by_states(series, order)
    assert [r["label"] for r in result] == ["APPLIED", "SCREENING", "PANEL"]
    assert [r["value"] for r in result] == [10, 6, 3]


def test_fills_missing_states_with_zero():
    series = [{"label": "APPLIED", "value": 10}]
    order = ["APPLIED", "SCREENING", "OFFER"]
    result = order_series_by_states(series, order)
    assert result == [
        {"label": "APPLIED", "value": 10},
        {"label": "SCREENING", "value": 0},
        {"label": "OFFER", "value": 0},
    ]


def test_unknown_labels_appended_after_ordered():
    series = [
        {"label": "LEGACY", "value": 2},
        {"label": "APPLIED", "value": 10},
    ]
    order = ["APPLIED"]
    result = order_series_by_states(series, order)
    assert [r["label"] for r in result] == ["APPLIED", "LEGACY"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_dashboard_metrics.py -v`
Expected: FAIL with `ImportError: cannot import name 'order_series_by_states'`.

- [ ] **Step 3: Implement the helper**

In `backend/dashboard/metrics.py`, add above `_pipeline_by_state` (after `_range_since`, ~line 220):

```python
def order_series_by_states(
    series: list[dict[str, Any]], state_order: list[str]
) -> list[dict[str, Any]]:
    """Reorder a label/value series to follow a workflow's declared state order.

    States in ``state_order`` absent from ``series`` are appended with value 0 so
    the funnel shows the full pipeline. Labels not in ``state_order`` keep their
    original relative order at the end.
    """
    by_label = {str(point["label"]): point for point in series}
    ordered: list[dict[str, Any]] = []
    for state in state_order:
        point = by_label.pop(state, None)
        ordered.append(point if point is not None else {"label": state, "value": 0})
    ordered.extend(by_label.values())
    return ordered
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_dashboard_metrics.py -v`
Expected: 3 passed.

- [ ] **Step 5: Verification checkpoint**

Run: `cd backend && pyright dashboard/metrics.py` (no new errors). Do NOT `git add`.

---

### Task B2: `pipeline.funnel` metric + active-workflow state loader

**Files:**
- Modify: `backend/dashboard/metrics.py` (add loader + `_pipeline_funnel`; register in `_METRIC_FNS` ~line 490 and `METRIC_REGISTRY` ~line 502)

**Interfaces:**
- Consumes: `order_series_by_states` (Task B1); `WorkflowStateMachineModel` (already imported, line 25); `StateMachineDefinition` parse via `json`.
- Produces: metric key `pipeline.funnel` (output `series`, default visuals `("funnel", "bar")`, param `workflow_id`).

- [ ] **Step 1: Add `json` import**

At the top of `backend/dashboard/metrics.py`, add after line 8 (`from __future__ import annotations`):

```python
import json
```

- [ ] **Step 2: Add the active-workflow state-order loader**

In `backend/dashboard/metrics.py`, add below `order_series_by_states` (from Task B1):

```python
def _active_workflow_state_order(
    db: Session, organization_id: str, workflow_id: str
) -> list[str]:
    """Ordered state names for a workflow's active definition.

    Reads the active ``WorkflowStateMachineModel`` row, parses ``definition_json``,
    and returns state names sorted by each state's ``order`` field (states without
    an explicit order sort last, by declared sequence). Returns [] when no active
    definition is found, so callers can fall back to count-desc ordering.
    """
    row = (
        db.query(WorkflowStateMachineModel.definition_json)
        .filter(
            WorkflowStateMachineModel.organization_id == organization_id,
            WorkflowStateMachineModel.id == workflow_id,
            WorkflowStateMachineModel.is_active.is_(True),
        )
        .first()
    )
    if row is None:
        return []
    try:
        definition = json.loads(row[0])
    except (TypeError, ValueError):
        return []
    states = definition.get("states") if isinstance(definition, dict) else None
    if not isinstance(states, list):
        return []
    indexed = []
    for seq, state in enumerate(states):
        if not isinstance(state, dict):
            continue
        name = state.get("name")
        if not name:
            continue
        order = state.get("order")
        sort_key = (0, order, seq) if isinstance(order, int) else (1, 0, seq)
        indexed.append((sort_key, str(name)))
    indexed.sort(key=lambda item: item[0])
    return [name for _, name in indexed]
```

- [ ] **Step 3: Add the funnel metric function**

In `backend/dashboard/metrics.py`, add after `_pipeline_by_state` (~line 235):

```python
def _pipeline_funnel(db: Session, organization_id: str, filters: dict[str, Any]) -> dict[str, Any]:
    """Pipeline counts ordered by the workflow's declared state sequence.

    Like ``pipeline.by_state`` but ordered for funnel display. Falls back to
    count-descending when no active workflow definition is available.
    """
    query = (
        db.query(EntityStateRuntimeModel.current_state, func.count().label("count"))
        .filter(EntityStateRuntimeModel.organization_id == organization_id)
    )
    workflow_id = _filter_str(filters, "workflow_id")
    if workflow_id:
        query = query.filter(EntityStateRuntimeModel.workflow_id == workflow_id)
    since = _range_since(filters)
    if since:
        query = query.filter(EntityStateRuntimeModel.state_entered_at >= since)
    query = query.group_by(EntityStateRuntimeModel.current_state).order_by(func.count().desc())
    series = [{"label": state, "value": int(count)} for state, count in query.all()]

    state_order = (
        _active_workflow_state_order(db, organization_id, workflow_id)
        if workflow_id
        else []
    )
    if state_order:
        series = order_series_by_states(series, state_order)
    return {"kind": "series", "series": series}
```

- [ ] **Step 4: Register the metric**

In `_METRIC_FNS` (~line 490), add after the `"pipeline.by_state"` entry:

```python
    "pipeline.funnel": _pipeline_funnel,
```

In `METRIC_REGISTRY` (~line 502), add after the `pipeline.by_state` `MetricSpec`:

```python
    MetricSpec(
        key="pipeline.funnel",
        label="Pipeline Funnel",
        description="Workflow instances by state, ordered as a conversion funnel.",
        output="series",
        default_visuals=("funnel", "bar"),
        params=(MetricParam("workflow_id", "Workflow", "string", source="workflows"),),
    ),
```

- [ ] **Step 5: Verification checkpoint**

Run: `cd backend && python -m pytest tests/test_dashboard_metrics.py -v && pyright dashboard/metrics.py`
Expected: tests pass, no new pyright errors.

Manual: `cd backend && uvicorn app.main:app --reload`, then `curl` the metrics endpoint (or the dashboard) and confirm `pipeline.funnel` appears in the metric list. Do NOT `git add`.

---

### Task B3: Funnel conversion-% labels (frontend)

**Files:**
- Modify: `frontend/src/core/components/DashboardChart.tsx` (funnel branch ~lines 225-251)

**Interfaces:**
- Consumes: the `colored` series (already computed) inside `DashboardChart`.
- Produces: per-segment conversion-% labels rendered on the funnel.

- [ ] **Step 1: Compute conversion percentages**

In `frontend/src/core/components/DashboardChart.tsx`, inside `DashboardChart`, just before the `if (viz === 'funnel')` branch (~line 225), add a memo that maps each colored point to its stage-over-stage conversion string:

```tsx
  const funnelConversion = useMemo(
    () =>
      colored.map((point, i) => {
        if (i === 0) return '100%';
        const prev = colored[i - 1].value;
        if (!prev) return '—';
        return `${((point.value / prev) * 100).toFixed(0)}%`;
      }),
    [colored],
  );
```

- [ ] **Step 2: Render the conversion label on the funnel**

In the `if (viz === 'funnel')` branch, add a third `LabelList` inside `<Funnel>` after the existing value `LabelList` (~line 243), using a custom content renderer so it can read the per-index conversion string:

```tsx
            <LabelList
              position="left"
              dataKey="label"
              stroke="none"
              content={({ index, x, y, height }) => {
                if (typeof index !== 'number' || index === 0) return null;
                const top = typeof y === 'number' ? y : 0;
                const h = typeof height === 'number' ? height : 0;
                const left = typeof x === 'number' ? x : 0;
                return (
                  <text
                    x={left - 8}
                    y={top + h / 2}
                    textAnchor="end"
                    dominantBaseline="middle"
                    className="fill-muted-foreground text-[10px] font-medium"
                  >
                    {funnelConversion[index]}
                  </text>
                );
              }}
            />
```

(The first stage shows no conversion; each later stage shows its drop-off vs the stage above.)

- [ ] **Step 3: Verification checkpoint**

Run: `cd frontend && npm run build`
Expected: passes clean (watch for Recharts `LabelList` content-prop type errors under `tsc -b`; the `typeof` guards keep all coordinates `number`).

Manual: create a chart widget bound to `pipeline.funnel` with a workflow selected; confirm stages appear in pipeline order with conversion-% labels on the left of each lower stage. Do NOT `git add`.

---

## Part C — KPI suite: delta + sparkline + gauge

### Task C0: Previous-period delta for scalar metrics (TDD)

**Files:**
- Modify: `backend/dashboard/metrics.py` (add `_previous_range`; wire into `_entities_count` ~line 238 and `_sla_breaches` ~line 256)
- Modify: `backend/tests/test_dashboard_metrics.py` (add tests)

**Interfaces:**
- Produces: `_previous_range(filters: dict) -> tuple[datetime, datetime] | None` — returns the `[start, end)` bounds of the period immediately before the current `time_range` window, or `None` when `time_range` is unset/`all`. Scalar metric payloads gain `prevValue: int` when a previous window exists.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_dashboard_metrics.py`:

```python
from datetime import datetime, timezone

from dashboard.metrics import _previous_range


def test_previous_range_none_for_all():
    assert _previous_range({}) is None
    assert _previous_range({"time_range": "all"}) is None


def test_previous_range_today_is_yesterday():
    window = _previous_range({"time_range": "today"})
    assert window is not None
    start, end = window
    assert start.tzinfo == timezone.utc
    # Previous window is exactly one day long and ends at today's midnight.
    assert (end - start).days == 1
    now = datetime.now(timezone.utc)
    assert end.date() == now.date()
    assert start.date() < now.date()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_dashboard_metrics.py -v`
Expected: FAIL with `ImportError: cannot import name '_previous_range'`.

- [ ] **Step 3: Implement `_previous_range`**

In `backend/dashboard/metrics.py`, add after `_range_since` (~line 219):

```python
def _previous_range(filters: dict[str, Any]) -> tuple[datetime, datetime] | None:
    """The [start, end) window immediately preceding the current ``time_range``.

    Used to compute period-over-period deltas for scalar metrics. ``None`` when
    ``time_range`` is unset or ``all`` (no meaningful baseline). The current
    window's lower bound (from ``_range_since``) is the previous window's upper
    bound.
    """
    current_start = _range_since(filters)
    if current_start is None:
        return None
    value = _filter_str(filters, "time_range")
    if value == "today":
        return current_start - timedelta(days=1), current_start
    if value == "this_week":
        return current_start - timedelta(days=7), current_start
    if value == "this_month":
        # Step back one calendar month from the first-of-month boundary.
        prev_month_end = current_start
        last_day_prev = prev_month_end - timedelta(days=1)
        prev_start = last_day_prev.replace(day=1)
        return prev_start, prev_month_end
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_dashboard_metrics.py -v`
Expected: all passed.

- [ ] **Step 5: Wire `prevValue` into `_entities_count`**

In `_entities_count` (~line 238), replace the final return:

```python
    return {"kind": "scalar", "value": int(query.scalar() or 0)}
```

with a version that also computes the previous-window count:

```python
    value = int(query.scalar() or 0)
    payload: dict[str, Any] = {"kind": "scalar", "value": value}
    prev_window = _previous_range(filters)
    if prev_window is not None:
        prev_start, prev_end = prev_window
        prev_query = (
            db.query(func.count())
            .select_from(EntityRecordModel)
            .filter(
                EntityRecordModel.organization_id == organization_id,
                EntityRecordModel.archived_at.is_(None),
                EntityRecordModel.created_at >= prev_start,
                EntityRecordModel.created_at < prev_end,
            )
        )
        if entity_type_id:
            prev_query = prev_query.filter(EntityRecordModel.entity_type_id == entity_type_id)
        payload["prevValue"] = int(prev_query.scalar() or 0)
    return payload
```

- [ ] **Step 6: Wire `prevValue` into `_sla_breaches`**

In `_sla_breaches` (~line 256), replace the final return:

```python
    return {"kind": "scalar", "value": int(query.scalar() or 0)}
```

with:

```python
    value = int(query.scalar() or 0)
    payload: dict[str, Any] = {"kind": "scalar", "value": value}
    prev_window = _previous_range(filters)
    if prev_window is not None:
        prev_start, prev_end = prev_window
        prev_query = (
            db.query(func.count())
            .select_from(ActionRunModel)
            .filter(
                ActionRunModel.organization_id == organization_id,
                ActionRunModel.action_kind == "signal.fire",
                ActionRunModel.config_json["signal_type"].astext == "sla_breach",
                ActionRunModel.status == "succeeded",
                ActionRunModel.completed_at >= prev_start,
                ActionRunModel.completed_at < prev_end,
            )
        )
        if workflow_id:
            entity_ids = db.query(EntityStateRuntimeModel.entity_id).filter(
                EntityStateRuntimeModel.organization_id == organization_id,
                EntityStateRuntimeModel.workflow_id == workflow_id,
            )
            prev_query = prev_query.filter(ActionRunModel.entity_id.in_(entity_ids))
        payload["prevValue"] = int(prev_query.scalar() or 0)
    return payload
```

- [ ] **Step 7: Verification checkpoint**

Run: `cd backend && python -m pytest tests/test_dashboard_metrics.py -v && pyright dashboard/metrics.py`
Expected: tests pass, no new pyright errors.

Manual: run the server; with a stat widget bound to `entities.count` and `time_range=today`, confirm the response includes `prevValue` and the KPI card shows a trend pill. Do NOT `git add`.

---

### Task C1: KPI sparkline (backend trend + frontend)

**Files:**
- Modify: `backend/dashboard/metrics.py` (add `_daily_trend` helper; attach `trend` in `_entities_count`)
- Modify: `frontend/src/core/types/index.ts` (extend scalar variant ~line 382)
- Modify: `frontend/src/core/components/DashboardStat.tsx`

**Interfaces:**
- Produces: scalar payloads optionally include `trend: list[{"label","value"}]` (daily buckets). Frontend scalar type gains `trend?: DashboardSeriesPoint[]`. `DashboardStat` accepts `trend?: { label: string; value: number }[]` and renders an inline sparkline.

- [ ] **Step 1: Add the daily-trend helper (backend)**

In `backend/dashboard/metrics.py`, add after `_previous_range`:

```python
def _daily_trend(
    db: Session, organization_id: str, filters: dict[str, Any], days: int = 14
) -> list[dict[str, Any]]:
    """Daily count of entities created over the trailing ``days`` window.

    Powers the KPI sparkline. Honors ``entity_type_id`` when present so the
    sparkline matches the headline ``entities.count`` value.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    bucket = func.date_trunc("day", EntityRecordModel.created_at)
    query = db.query(bucket.label("day"), func.count().label("count")).filter(
        EntityRecordModel.organization_id == organization_id,
        EntityRecordModel.archived_at.is_(None),
        EntityRecordModel.created_at >= since,
    )
    entity_type_id = _filter_str(filters, "entity_type_id")
    if entity_type_id:
        query = query.filter(EntityRecordModel.entity_type_id == entity_type_id)
    rows = query.group_by(bucket).order_by(bucket.asc()).all()
    return [
        {"label": day.date().isoformat() if day else "", "value": int(count)}
        for day, count in rows
    ]
```

- [ ] **Step 2: Attach `trend` in `_entities_count`**

In `_entities_count`, immediately before `return payload` (added in C0 Step 5), insert:

```python
    payload["trend"] = _daily_trend(db, organization_id, filters)
```

- [ ] **Step 3: Extend the scalar TS type**

In `frontend/src/core/types/index.ts`, change the scalar variant of `DashboardWidgetData` (~line 382):

```ts
  | { kind: 'scalar'; value: number; prevValue?: number }
```

to:

```ts
  | {
      kind: 'scalar';
      value: number;
      prevValue?: number;
      trend?: DashboardSeriesPoint[];
    }
```

- [ ] **Step 4: Render the sparkline in DashboardStat**

In `frontend/src/core/components/DashboardStat.tsx`:

Extend the props interface:

```tsx
interface DashboardStatProps {
  value: number;
  prevValue?: number;
  /** Optional Lucide icon name shown in the accent badge. */
  icon?: string;
  /** Optional daily trend points for an inline sparkline. */
  trend?: { label: string; value: number }[];
}
```

Add Recharts imports at the top (after the existing lucide import):

```tsx
import { Area, AreaChart, ResponsiveContainer } from 'recharts';
```

Destructure `trend` in the signature: `export default function DashboardStat({ value, prevValue, icon, trend }: DashboardStatProps) {`.

Then, inside the root `<div className="flex h-full flex-col justify-center gap-2">`, after the trend-pill block (the closing `)}` of `direction && (…)`), add:

```tsx
      {trend && trend.length > 1 && (
        <div className="h-8 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={trend} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="stat-spark" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-chart-1)" stopOpacity={0.25} />
                  <stop offset="100%" stopColor="var(--color-chart-1)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <Area
                type="monotone"
                dataKey="value"
                stroke="var(--color-chart-1)"
                strokeWidth={1.5}
                fill="url(#stat-spark)"
                dot={false}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
```

- [ ] **Step 5: Pass `trend` through WidgetBody**

In `frontend/src/pages/DashboardPage.tsx`, update the stat render (~line 842):

```tsx
    return <DashboardStat value={data.value} prevValue={data.prevValue} icon={widget.icon} />;
```

to:

```tsx
    return (
      <DashboardStat
        value={data.value}
        prevValue={data.prevValue}
        icon={widget.icon}
        trend={data.trend}
      />
    );
```

- [ ] **Step 6: Verification checkpoint**

Run: `cd frontend && npm run build` and `cd backend && pyright dashboard/metrics.py`
Expected: both clean.

Manual: stat widget bound to `entities.count` shows a sparkline beneath the value and delta pill. Do NOT `git add`.

---

### Task C2: Gauge widget (backend metric + frontend component + builder)

**Files:**
- Modify: `backend/dashboard/metrics.py` (add `_sla_compliance`; register)
- Create: `frontend/src/core/components/DashboardGauge.tsx`
- Modify: `frontend/src/core/components/index.ts`
- Modify: `frontend/src/core/types/index.ts` (`DashboardWidgetData`, `DashboardViz`, `DashboardWidgetType`)
- Modify: `frontend/src/pages/DashboardPage.tsx` (builder kind + WidgetBody)

**Interfaces:**
- Produces:
  - Backend metric `sla.compliance` (output `gauge`), payload `{"kind": "gauge", "value": float, "max": 100, "label": "On-time %"}`.
  - `DashboardGauge` component: props `{ value: number; max: number; label?: string }`.
  - TS: `DashboardWidgetData` gains `{ kind: 'gauge'; value: number; max: number; label?: string }`; `DashboardViz` gains `'gauge'`; `DashboardWidgetType` gains `'gauge'`.

- [ ] **Step 1: Add the SLA-compliance metric (backend)**

In `backend/dashboard/metrics.py`, add after `_sla_breaches` (~line 289):

```python
def _sla_compliance(db: Session, organization_id: str, filters: dict[str, Any]) -> dict[str, Any]:
    """On-time percentage for instances that carry an SLA due time.

    Compliance = instances whose ``sla_due_at`` is still in the future (or null
    among those with a due date is excluded) over all instances with a due date.
    Returns a gauge payload (0-100). When no instance has an SLA, value is 100.
    """
    base = db.query(func.count()).select_from(EntityStateRuntimeModel).filter(
        EntityStateRuntimeModel.organization_id == organization_id,
        EntityStateRuntimeModel.sla_due_at.isnot(None),
    )
    workflow_id = _filter_str(filters, "workflow_id")
    if workflow_id:
        base = base.filter(EntityStateRuntimeModel.workflow_id == workflow_id)
    total = int(base.scalar() or 0)
    if total == 0:
        return {"kind": "gauge", "value": 100.0, "max": 100, "label": "On-time %"}
    now = datetime.now(timezone.utc)
    on_time_query = db.query(func.count()).select_from(EntityStateRuntimeModel).filter(
        EntityStateRuntimeModel.organization_id == organization_id,
        EntityStateRuntimeModel.sla_due_at.isnot(None),
        EntityStateRuntimeModel.sla_due_at >= now,
    )
    if workflow_id:
        on_time_query = on_time_query.filter(EntityStateRuntimeModel.workflow_id == workflow_id)
    on_time = int(on_time_query.scalar() or 0)
    return {
        "kind": "gauge",
        "value": round(on_time / total * 100, 1),
        "max": 100,
        "label": "On-time %",
    }
```

- [ ] **Step 2: Register the gauge metric**

In `_METRIC_FNS` (~line 490), add:

```python
    "sla.compliance": _sla_compliance,
```

In `METRIC_REGISTRY` (~line 502), add after the `sla.breaches` `MetricSpec`:

```python
    MetricSpec(
        key="sla.compliance",
        label="SLA Compliance",
        description="Percentage of SLA-bound instances still within their due time.",
        output="gauge",
        default_visuals=("gauge",),
        params=(MetricParam("workflow_id", "Workflow", "string", source="workflows"),),
    ),
```

- [ ] **Step 3: Extend the frontend types**

In `frontend/src/core/types/index.ts`:

Add `'gauge'` to `DashboardWidgetType` (~line 289):

```ts
export type DashboardWidgetType = 'stat' | 'chart' | 'table' | 'button' | 'gauge';
```

Add `'gauge'` to `DashboardViz` (~line 290):

```ts
export type DashboardViz =
  | 'number'
  | 'bar'
  | 'line'
  | 'area'
  | 'pie'
  | 'funnel'
  | 'table'
  | 'gauge';
```

Add the gauge variant to `DashboardWidgetData` (~line 380), before the `error` variant:

```ts
  | { kind: 'gauge'; value: number; max: number; label?: string }
```

Also update `DashboardMetricRead['output']` (~line 351) to include gauge:

```ts
  output: 'series' | 'scalar' | 'rows' | 'gauge';
```

- [ ] **Step 4: Create the DashboardGauge component**

Create `frontend/src/core/components/DashboardGauge.tsx`:

```tsx
/**
 * DashboardGauge Component
 *
 * Presentational radial gauge for bounded-ratio widgets (e.g. SLA compliance).
 * Renders a single-value arc with the percentage in the center. No data fetching.
 */

import { useMemo } from 'react';
import { PolarAngleAxis, RadialBar, RadialBarChart, ResponsiveContainer } from 'recharts';

interface DashboardGaugeProps {
  value: number;
  max: number;
  label?: string;
}

function gaugeColor(pct: number): string {
  if (pct >= 80) return 'var(--color-chart-6)'; // emerald
  if (pct >= 50) return 'var(--color-chart-4)'; // amber
  return 'var(--color-chart-7)'; // red
}

export default function DashboardGauge({ value, max, label }: DashboardGaugeProps) {
  const pct = useMemo(() => (max > 0 ? Math.max(0, Math.min(value, max)) : 0), [value, max]);
  const data = [{ name: label ?? 'value', value: pct, fill: gaugeColor((pct / max) * 100) }];

  return (
    <div className="relative flex h-full w-full items-center justify-center">
      <ResponsiveContainer width="100%" height="100%">
        <RadialBarChart
          data={data}
          startAngle={210}
          endAngle={-30}
          innerRadius="70%"
          outerRadius="100%"
        >
          <PolarAngleAxis type="number" domain={[0, max]} tick={false} axisLine={false} />
          <RadialBar dataKey="value" cornerRadius={8} background animationDuration={600} />
        </RadialBarChart>
      </ResponsiveContainer>
      <div className="pointer-events-none absolute flex flex-col items-center">
        <span className="text-2xl font-semibold tabular-nums text-foreground">
          {value.toLocaleString(undefined, { maximumFractionDigits: 1 })}
          {max === 100 ? '%' : ''}
        </span>
        {label && <span className="text-xs text-muted-foreground">{label}</span>}
      </div>
    </div>
  );
}

export type { DashboardGaugeProps };
```

- [ ] **Step 5: Export the component**

In `frontend/src/core/components/index.ts`, add after the `DashboardChart` export (line 13):

```ts
export { default as DashboardGauge } from './DashboardGauge';
```

- [ ] **Step 6: Add the `gauge` widget kind to the builder**

In `frontend/src/pages/DashboardPage.tsx`:

Add to the `WidgetKind` union (~line 105):

```ts
type WidgetKind = 'stat' | 'table' | 'chart' | 'button' | 'gauge';
```

Add to `WIDGET_KINDS` (~line 112), after the `chart` entry (import `Gauge` from `lucide-react` in the existing icon import group):

```ts
  { value: 'gauge', label: 'Gauge', description: 'A ratio dial', icon: Gauge },
```

Add to `KIND_OUTPUT` (~line 120):

```ts
const KIND_OUTPUT: Record<Exclude<WidgetKind, 'button'>, DashboardMetricRead['output']> = {
  stat: 'scalar',
  table: 'rows',
  chart: 'series',
  gauge: 'gauge',
};
```

Handle gauge in `defaultLayoutForType` (~line 126) — gauges are square-ish like stats; add a case:

```ts
    case 'gauge':
      return { w: 3, h: 3 };
```

Map gauge output to widget type in `widgetTypeForOutput` (~line 137):

```ts
function widgetTypeForOutput(output: DashboardMetricRead['output']): DashboardWidgetType {
  if (output === 'scalar') return 'stat';
  if (output === 'rows') return 'table';
  if (output === 'gauge') return 'gauge';
  return 'chart';
}
```

Set default viz for gauge in `vizForOutput` (~line 143):

```ts
function vizForOutput(metric: DashboardMetricRead): DashboardViz {
  if (metric.output === 'scalar') return 'number';
  if (metric.output === 'rows') return 'table';
  if (metric.output === 'gauge') return 'gauge';
  return (metric.default_visuals[0] as DashboardViz) ?? 'bar';
}
```

- [ ] **Step 7: Render the gauge in WidgetBody**

In `frontend/src/pages/DashboardPage.tsx`, import `DashboardGauge` in the component import group (~line 30, alongside `DashboardChart`/`DashboardStat`). Then add a branch in `WidgetBody` after the stat branch (~line 843):

```tsx
  if (widget.type === 'gauge' && data.kind === 'gauge') {
    return <DashboardGauge value={data.value} max={data.max} label={data.label} />;
  }
```

- [ ] **Step 8: Verification checkpoint**

Run: `cd frontend && npm run build` and `cd backend && python -m pytest tests/test_dashboard_metrics.py -v && pyright dashboard/metrics.py`
Expected: all clean.

Manual: in the dashboard builder, add a **Gauge** widget bound to `sla.compliance`; confirm the dial renders with the on-time % in the center and color shifts by threshold (green ≥80, amber ≥50, red below). Confirm empty/100% state when no SLA-bound instances exist. Do NOT `git add`.

---

## Self-Review

**Spec coverage:**
- Part A (shadcn foundation, CSS-var palette) → Tasks A1, A2. ✓
- Part B (workflow-ordered funnel + conversion %) → Tasks B1, B2, B3. ✓
- Part C0 (delta) → Task C0. ✓
- Part C1 (sparkline) → Task C1. ✓
- Part C2 (gauge) → Task C2. ✓
- "No Pydantic changes" → honored; only TS union + untyped payloads. ✓
- "Fallback to count-desc when no active workflow" → B2 Step 3. ✓

**Type consistency:**
- `order_series_by_states` — defined B1, consumed B2. ✓
- `_previous_range` — defined C0, consumed C0 (entities/sla). ✓
- `_daily_trend` — defined C1, consumed C1. ✓
- `trend?: DashboardSeriesPoint[]` (TS) ↔ backend `trend` list[{label,value}]. ✓
- gauge payload `{kind,value,max,label}` ↔ TS gauge variant ↔ `DashboardGauge` props. ✓
- `DashboardMetricRead['output']` widened to include `'gauge'` so `KIND_OUTPUT.gauge` typechecks. ✓

**Placeholder scan:** none — every code step contains complete code; commands have expected output. Frontend "test" steps use `npm run build` (no runner) per Global Constraints. ✓
