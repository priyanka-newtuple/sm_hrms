# Customizable Per-Role Dashboard — Concept & Design (Prototype)

> Status: **Concept / brainstorming** — not implementation-ready yet.
> Scope note: This deliberately ignores the *current* dashboard and projections
> behavior and designs the concept fresh, per request.

## 1. Goal

A customizable dashboard where an admin composes a grid of **widgets** (charts,
stat tiles, action buttons, tables) for a **role**. Everyone in that role sees
the role's dashboard. Data is fetched with a normal query on page load; the user
reloads to refresh (no realtime).

### Decisions locked in
| Dimension | Choice |
|-----------|--------|
| Flexibility | **Fully dynamic** — widgets composed from a metric catalog (not raw SQL) |
| Ownership | **Per-role** — admin defines a dashboard per role; members see it |
| Realtime | **None** — single fetch on load, reload to refresh |
| First version | **Prototype/demo** — prove the loop end-to-end, mock what's expensive |

## 2. The core idea: a *metric registry* widgets bind to

"Fully dynamic" does **not** mean end users write SQL (unsafe + huge build).
It means widgets are composed from:

```
metric (what data)  +  visualization (how to show it)  +  filters (which slice)
```

A **metric** is a named, parameterized server-side query. Example:

- `pipeline.by_state` → params: `{ entityType, jobId? }` → returns `{ state, count }[]`
- `applications.count` → params: `{ dateRange, state? }` → returns `{ value, prevValue }`
- `events.recent` → params: `{ limit, eventType? }` → returns rows
- `sla.breaches` → params: `{ entityType }` → returns `{ value }`
- `transitions.success_rate` → params: `{ dateRange }` → returns `{ value }`

Adding power later = adding metrics on the backend. The frontend builder never
changes. This is what makes it feel unlimited while staying shippable.

## 3. Data model (per-role layout as JSON)

```
DashboardConfig
  ├─ role            // e.g. "RECRUITER" — the dashboard's audience
  ├─ display_name
  └─ widgets[]       // stored as a JSON blob for the prototype
       ├─ id
       ├─ type       // "stat" | "chart" | "button" | "table"
       ├─ metric     // key into the metric registry (null for buttons)
       ├─ filters    // { jobId, dateRange, state, ... }
       ├─ viz        // "bar" | "line" | "pie" | "funnel" | "number"
       ├─ title
       └─ layout     // { x, y, w, h }  (react-grid-layout coords)
```

Storing `widgets` as JSON keeps the schema flexible during prototyping — no
migrations every time a widget gains an option.

## 4. Widget types

| Type | What it shows | Notes |
|------|---------------|-------|
| **Stat tile** | One number + trend (`Apps today: 42 ↑12%`) | metric returns `{value, prevValue}` |
| **Chart** | bar / line / pie / funnel | metric returns rows; viz picks rendering |
| **Table** | recent events / entities needing attention | metric returns rows + columns |
| **Button** | fires an action | `triggerTransition` \| `navigate` \| `runSignal` |

**The button widget is the differentiator.** Because the platform already has a
transition engine, a button can fire a state transition or signal — a genuinely
useful ATS action tile, not decoration.

## 5. API surface (minimal)

```
GET  /dashboard?role={role}        → DashboardConfig for the caller's role
PUT  /dashboard?role={role}        → save layout (admin/role-owner only)
GET  /dashboard/metrics            → catalog: metric keys, params, output shape
POST /dashboard/data               → body: [{ widgetId, metric, filters }]
                                     → returns { widgetId: data } in one round trip
```

One batched `/dashboard/data` call hydrates the whole grid on load. Reload = refetch.

## 6. Frontend: two modes

- **View mode** — render the role's widgets in a grid (`react-grid-layout`),
  hydrate via one `/dashboard/data` call. Charts via `recharts` (already installed).
- **Edit mode** (admin only) — drag/resize the grid; "Add widget" opens a builder:
  1. pick a **metric** (from `/dashboard/metrics`)
  2. pick a **visualization**
  3. set **filters**
  4. live **preview**
  5. **save** → `PUT /dashboard`

## 7. Suggested build order (demo)

1. `DashboardConfig` model + per-role JSON layout (`GET` / `PUT`).
2. Metric registry + batched `/dashboard/data` endpoint. Ship ~5 real metrics
   off the event log / entity states; mock the rest.
3. Frontend grid with view/edit modes.
4. Widget renderers: stat tile, chart, button, table.
5. Widget builder modal (metric → viz → filters → preview).

## 8. What already exists (cheap reuse)

Even though current behavior is out of scope, these are already present and
would lower prototype cost:

- `recharts` (v3.6.0) and `react-grid-layout` (v2.2.3) — `frontend/package.json`
- A `backend/dashboard/` module (controller / manager / db_models) with a
  query-source + query-preview pattern that mirrors the "metric registry" idea.
- RBAC via `build_actor_context()` exposing `actor["roles"]` — `backend/common/auth.py`.
- `recharts`-based widget rendering already in `frontend/src/pages/DashboardPage.tsx`.

## 9. Open questions

1. **Edit rights** — strictly admin-defines-per-role (members read-only), or can
   members personalize on top of the role default?
2. **Metric catalog** — derive a realistic starter set from real entities/event
   log, or keep fully mocked for the demo?
3. **Per-role storage** — one `DashboardConfig` row per role, or one config with
   role-visibility baked into each widget?
4. **Button safety** — should action buttons be limited to navigation in the
   prototype, or wired to real transitions/signals from day one?
```
