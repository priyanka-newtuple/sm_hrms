---
name: frontend-codestructure
description: Enforces readable, SOLID, reusable frontend architecture patterns (component/hook/store layering, naming conventions, Zustand-first state management) when working on frontend/src/ files.
allowed-tools: Read, Grep, Glob, Bash
model: sonnet4.6
---

# Frontend Code Structure Skill

## Trigger

Auto-invoke this skill when creating or modifying files under `frontend/src/`.

## Architecture Overview

All application code lives under `frontend/src/core/`. There is no separate domain folder — new features are added into the relevant subfolder of `core/`.

```
frontend/src/
  core/
    components/            # All UI components (shared primitives + feature components)
    hooks/                 # All custom hooks
    services/              # API client and all API methods
    stores/                # Zustand stores
    types/                 # All TypeScript types
    utils/                 # Pure utility functions
    auth/                  # Auth context, ProtectedRoute, API
    contexts/              # App-level React Contexts ONLY (AuthContext, OrgSelectorContext, SkinContext)
  layouts/                 # Layout wrappers (SettingsLayout, AppLayout…)
  pages/                   # Route-level page components
  skins/                   # Skin/theme providers and configs
```

Reference component: `frontend/src/core/components/Button.tsx`

## Naming Conventions

| Item | Pattern | Example |
|---|---|---|
| Component | PascalCase | `FunnelStepCard` |
| Page component | `<Feature>Page` | `SettingsPage` |
| Layout component | `<Feature>Layout` | `SettingsLayout` |
| Store file | `<feature>.store.ts` | `funnelBuilder.store.ts` |
| Store hook export | `use<Feature>Store` | `useFunnelBuilderStore` |
| Custom hook | `use<Name>` | `useFunnels`, `useTabParam` |
| API service namespace | camelCase object | `funnels.list()`, `agents.create()` |
| Type / Interface | PascalCase | `FunnelStep`, `PlaybookConfig` |
| Enum | PascalCase | `FunnelStepType` |
| Utility function | camelCase | `convertFunnelToApi()` |
| Constants | SCREAMING_SNAKE | `MAX_FUNNEL_STEPS` |

## SOLID Principles Applied to React

### S — Single Responsibility

Every file has one reason to change. Split when a component handles multiple concerns.

```tsx
// Bad — renders AND manages fetch AND handles form state
function FunnelTab() {
  const [funnels, setFunnels] = useState([])
  const [form, setForm] = useState({})
  useEffect(() => { fetch('/funnels').then(...) }, [])
  return <div>...</div>
}

// Good — each piece has one job
function FunnelTab() {
  const { data: funnels } = useFunnels()          // fetching
  return <FunnelList funnels={funnels} />         // rendering
}

function FunnelList({ funnels }: { funnels: Funnel[] }) { ... }
```

**Signal to split:** component exceeds ~150–200 lines, or you describe it with "and" ("it fetches *and* renders *and* validates").

### O — Open/Closed

Extend components via props, not by modifying internals.

```tsx
// Bad — adding a new variant means editing Button internals every time
if (type === 'newVariant') { ... }

// Good — adding a variant only requires adding a key to the Record
const variantStyles: Record<Variant, string> = {
  primary: '...',
  secondary: '...',
  ghost: '...',
  // just add here
}
```

Use `className`, `children`, render props, and variant Records to keep components open for extension.

### L — Liskov Substitution

All variants of a component must honour the same base contract. If `Button` accepts `loading` and `disabled`, every variant (primary, secondary, ghost, danger) must handle them correctly — a `ghost` button cannot silently ignore `loading`.

### I — Interface Segregation

Keep prop interfaces small and focused. Compose them rather than creating one giant interface.

```tsx
// Bad
interface CardProps {
  title: string
  onClick?: () => void
  href?: string
  loading?: boolean
  draggable?: boolean
  onDrop?: () => void
}

// Good — split by concern, compose where needed
interface CardBaseProps { title: string; loading?: boolean }
interface ClickableCardProps extends CardBaseProps { onClick: () => void }
interface DraggableCardProps extends CardBaseProps { onDrop: () => void }
```

### D — Dependency Inversion

Components depend on hooks and stores (abstractions), never on concrete service implementations.

```tsx
// Bad — component knows about the API
function FunnelList() {
  useEffect(() => {
    api.funnels.list().then(setFunnels)
  }, [])
}

// Good — component depends on a hook abstraction
function FunnelList() {
  const { data: funnels, loading } = useFunnels()
}
```

**Dependency chain:** `Component → Hook → Store / useApi → Service → API`

Never skip a layer. Components call hooks; hooks call services.

## State Management: When to Use What

| State type | Solution |
|---|---|
| App-level auth, org, skin | Existing React Context — do **not** replace |
| Multi-step feature state (builders, wizards, tabs) | **Zustand store** |
| Shared state within a feature subtree | **Zustand store** |
| Simple UI toggle (modal open, dropdown open) | `useState` inside the component |
| Remote / server data (lists, single items) | `useApi` hook — **not** Zustand |
| Derived/computed values | `useMemo` inside a hook |

**Rule:** If state needs to survive across component unmounts, be shared between sibling components, or power a multi-step flow — use Zustand.

**Rule:** Never store API response data in Zustand. Use `useApi` for server data; Zustand is for client-side interaction state.

**Rule:** No new React Contexts for feature-level state. Contexts are reserved for app-level providers already in `core/contexts/`.

## Zustand Store Pattern

Store files live in `frontend/src/core/stores/`.

### Store file anatomy

```ts
// core/stores/funnelBuilder.store.ts

import { create } from 'zustand'
import type { FunnelStep } from '../types/funnel'

// 1. Define the full state + action interface
interface FunnelBuilderState {
  // — state —
  steps: FunnelStep[]
  activeStepId: string | null
  isDirty: boolean

  // — actions —
  addStep: (step: FunnelStep) => void
  removeStep: (id: string) => void
  reorderSteps: (steps: FunnelStep[]) => void
  setActiveStep: (id: string | null) => void
  reset: () => void
}

// 2. Extract initial state so reset() is a one-liner
const initialState: Pick<FunnelBuilderState, 'steps' | 'activeStepId' | 'isDirty'> = {
  steps: [],
  activeStepId: null,
  isDirty: false,
}

// 3. Create the store — actions co-located with state
export const useFunnelBuilderStore = create<FunnelBuilderState>((set) => ({
  ...initialState,

  addStep: (step) =>
    set((s) => ({ steps: [...s.steps, step], isDirty: true })),

  removeStep: (id) =>
    set((s) => ({ steps: s.steps.filter((s) => s.id !== id), isDirty: true })),

  reorderSteps: (steps) =>
    set({ steps, isDirty: true }),

  setActiveStep: (id) =>
    set({ activeStepId: id }),

  reset: () => set(initialState),
}))
```

### Consuming the store — use selectors

Always subscribe to the minimum slice to prevent unnecessary re-renders.

```tsx
// Bad — subscribes to the entire store
const store = useFunnelBuilderStore()

// Good — each component subscribes to only what it needs
const steps = useFunnelBuilderStore((s) => s.steps)
const addStep = useFunnelBuilderStore((s) => s.addStep)
const activeStepId = useFunnelBuilderStore((s) => s.activeStepId)
```

### Reset on exit

Call `reset()` in a `useEffect` cleanup when the feature unmounts to prevent stale state leaking to the next mount.

```tsx
useEffect(() => {
  return () => useFunnelBuilderStore.getState().reset()
}, [])
```

## Component Anatomy

### Presentational component (shared UI primitive)

Reference: `frontend/src/core/components/Button.tsx`

```tsx
// 1. Extend the native HTML element's props so all HTML attributes pass through
interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
  icon?: ReactNode
}

// 2. Variant styles as a typed Record — not a switch/if chain
const variantStyles: Record<NonNullable<ButtonProps['variant']>, string> = {
  primary: 'bg-cobalt text-white hover:bg-cobalt-700 ...',
  secondary: 'border border-gray-300 hover:bg-gray-50 ...',
  ghost: 'text-gray-600 hover:bg-gray-100 ...',
  danger: 'bg-red-500 text-white hover:bg-red-600 ...',
}

// 3. forwardRef so parent can ref the DOM node
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'primary', size = 'md', loading, icon, children, className, ...props }, ref) => (
    <button
      ref={ref}
      disabled={loading || props.disabled}
      className={cn(baseStyles, variantStyles[variant], sizeStyles[size], className)}
      {...props}
    >
      {loading ? <Spinner size={size} /> : icon}
      {children}
    </button>
  )
)
Button.displayName = 'Button'
```

Rules for presentational components:
- Always `forwardRef` on elements that consumers might need to ref
- Always spread `...props` so native HTML attributes work
- Always accept and merge `className` via `cn()`
- No API calls, no store access, no side effects

### Container / page component

Reference: `frontend/src/pages/SettingsPage.tsx`

```tsx
// Container orchestrates — it does NOT render detail UI itself
function SettingsPage() {
  const { user } = useAuth()              // app-level context — OK
  const tab = useTabParam()               // URL-derived state — hook

  return (
    <SettingsLayout>
      <SettingsTabs active={tab} />
      {tab === 'funnels'   && <FunnelsTab />}
      {tab === 'playbooks' && <PlaybooksTab />}
    </SettingsLayout>
  )
}
```

Rules for container/page components:
- Orchestrate child components — do not inline their markup
- Data fetching and store access live in hooks, not inline in JSX
- Permission checks at the page level, not buried in child components

## Custom Hook Patterns

### Data-fetching hook (wraps `useApi`)

```ts
// hooks/useFunnels.ts
export function useFunnels() {
  return useApi(() => funnelService.list(), { immediate: true })
}
```

Keep one hook per resource. The hook is the single place to change the fetching strategy.

### Store-access hook (encapsulates selector logic)

```ts
// hooks/useFunnelBuilder.ts — optional thin wrapper when selector logic is complex
export function useFunnelBuilder() {
  const steps       = useFunnelBuilderStore((s) => s.steps)
  const activeStep  = useFunnelBuilderStore((s) =>
    s.steps.find((step) => step.id === s.activeStepId) ?? null
  )
  const { addStep, removeStep, setActiveStep } = useFunnelBuilderStore()
  return { steps, activeStep, addStep, removeStep, setActiveStep }
}
```

### Logic-only hook (no state, pure computation)

```ts
// hooks/useFunnelValidation.ts
export function useFunnelValidation(steps: FunnelStep[]) {
  return useMemo(() => validateFunnelSteps(steps), [steps])
}
```

## Hard Rules

These must never be violated:

1. **Components never import from `services/`** — all service calls go through hooks
2. **Never put server/API response data in Zustand** — use `useApi` for remote data
3. **No new React Contexts for feature state** — use Zustand stores instead
4. **No prop drilling beyond 2 levels** — if a prop passes through an intermediate component that doesn't use it, introduce a store or hook
5. **Components must not exceed ~200 lines** — split into smaller components or extract logic to hooks
6. **No `any` type** — use `unknown` with type guards, or define a proper interface
7. **Every Zustand store must export a typed `interface <Name>State`** — the state shape must be explicit
8. **Presentational components in `core/components/` must have zero business logic** — they render, they do not decide

## Adding a New Feature Checklist

1. Identify if the feature needs shared state → create `core/stores/<feature>.store.ts`
2. Define TypeScript types in `core/types/`
3. Add API methods to `core/services/api.ts`
4. Write data-fetching and logic hooks in `core/hooks/`
5. Build presentational components in `core/components/`
6. Build the container page in `pages/`
7. Add the route in `frontend/src/App.tsx`
