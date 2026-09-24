import Badge from '@/core/components/Badge'
import { ColorToggle } from '../../shared/color-toggle'
import type { PublishedWorkflow, WorkflowTransition } from '@/core/hooks/usePublishedWorkflows'

export interface WorkflowGroupProps {
  workflow: PublishedWorkflow
  transitionPerms: Set<string>
  onToggle: (machineName: string, transitionKey: string) => void
  onAllowAll: (workflow: PublishedWorkflow) => void
  roleColor: string | null
  disabled?: boolean
}

const TERMINAL_STATES = new Set(['REJECTED', 'WITHDRAWN', 'rejected', 'withdrawn'])

function resolveFrom(from: string | string[]): string {
  if (Array.isArray(from)) return from.length === 1 ? from[0] : '*'
  return from ?? '*'
}

function StatePill({ value }: { value: string }) {
  const isAny = !value || value === '*' || value.toLowerCase() === 'any'
  if (isAny) {
    return (
      <Badge className="font-medium whitespace-nowrap">
        Any stage
      </Badge>
    )
  }
  return (
    <Badge
      variant={TERMINAL_STATES.has(value) ? 'error' : 'default'}
      className="font-medium whitespace-nowrap"
    >
      {value}
    </Badge>
  )
}

interface TransitionRowProps {
  transition: WorkflowTransition
  machineName: string
  transitionPerms: Set<string>
  onToggle: (machineName: string, transitionKey: string) => void
  roleColor: string | null
  disabled: boolean
}

function TransitionRow({
  transition,
  machineName,
  transitionPerms,
  onToggle,
  roleColor,
  disabled,
}: TransitionRowProps) {
  const permKey = `${machineName}:${transition.key}`
  return (
    <div className="flex items-center gap-4 px-5 py-3 border-t border-border">
      <div className="flex items-center gap-1.5 shrink-0">
        <StatePill value={resolveFrom(transition.from)} />
        <span className="text-muted-foreground text-xs">→</span>
        <StatePill value={transition.to_state} />
      </div>
      <div className="flex-1 min-w-0">
        <span className="text-sm text-foreground">{transition.label}</span>
        {transition.description && (
          <span className="ml-2 text-xs text-muted-foreground">{transition.description}</span>
        )}
      </div>
      <ColorToggle
        checked={transitionPerms.has(permKey)}
        onCheckedChange={() => onToggle(machineName, transition.key)}
        color={roleColor ?? '#4F46E5'}
        disabled={disabled}
      />
    </div>
  )
}

export function WorkflowGroup({
  workflow,
  transitionPerms,
  onToggle,
  onAllowAll,
  roleColor,
  disabled = false,
}: WorkflowGroupProps) {
  const enabledCount = workflow.transitions.filter((t) =>
    transitionPerms.has(`${workflow.machineName}:${t.key}`)
  ).length
  const allEnabled =
    workflow.transitions.length > 0 && enabledCount === workflow.transitions.length

  return (
    <div className="rounded-xl border border-border overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 bg-muted">
        <div>
          <p className="text-sm font-semibold text-foreground">{workflow.name}</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {workflow.entityType} · {workflow.transitions.length} transition
            {workflow.transitions.length !== 1 ? 's' : ''}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">
            {enabledCount}/{workflow.transitions.length}
          </span>
          <button
            disabled={disabled || workflow.transitions.length === 0}
            onClick={() => onAllowAll(workflow)}
            className="text-xs font-medium text-muted-foreground border border-border rounded-md px-3 py-1 bg-card hover:bg-muted transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {allEnabled ? 'Remove all' : 'Allow all'}
          </button>
        </div>
      </div>

      {workflow.transitions.map((t) => (
        <TransitionRow
          key={t.key}
          transition={t}
          machineName={workflow.machineName}
          transitionPerms={transitionPerms}
          onToggle={onToggle}
          roleColor={roleColor}
          disabled={disabled}
        />
      ))}
    </div>
  )
}
