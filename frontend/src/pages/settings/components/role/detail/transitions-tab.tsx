import { useState, useMemo } from 'react'
import { usePublishedWorkflows } from '@/core/hooks/usePublishedWorkflows'
import type { PublishedWorkflow } from '@/core/hooks/usePublishedWorkflows'
import { SearchInput } from '../shared/search-input'
import { WorkflowGroup } from './transitions/workflow-group'

export interface TransitionsTabProps {
  transitionPerms: Set<string>
  onChange: (next: Set<string>) => void
  workflowPerms: Set<string>
  workflowRestricted: boolean
  onWorkflowPermsChange: (next: Set<string>) => void
  onWorkflowRestrictedChange: (restricted: boolean) => void
  roleColor: string | null
  disabled?: boolean
}

function filterWorkflows(workflows: PublishedWorkflow[], q: string): PublishedWorkflow[] {
  if (!q) return workflows
  return workflows
    .map((wf) => {
      const matchedTransitions = wf.transitions.filter(
        (t) =>
          wf.name.toLowerCase().includes(q) ||
          t.label.toLowerCase().includes(q) ||
          (t.description ?? '').toLowerCase().includes(q)
      )
      if (matchedTransitions.length === 0) return null
      return { ...wf, transitions: matchedTransitions }
    })
    .filter((wf): wf is PublishedWorkflow => wf !== null)
}

export function TransitionsTab({
  transitionPerms,
  onChange,
  workflowPerms,
  workflowRestricted,
  onWorkflowPermsChange,
  onWorkflowRestrictedChange,
  roleColor,
  disabled = false,
}: TransitionsTabProps) {
  const { workflows, loading, error } = usePublishedWorkflows()
  const [search, setSearch] = useState('')

  const q = search.toLowerCase().trim()
  const filtered = useMemo(() => filterWorkflows(workflows, q), [workflows, q])

  function toggle(machineName: string, transitionKey: string) {
    const key = `${machineName}:${transitionKey}`
    const next = new Set(transitionPerms)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    onChange(next)
  }

  function allowAll(workflow: PublishedWorkflow) {
    const allEnabled = workflow.transitions.every((t) =>
      transitionPerms.has(`${workflow.machineName}:${t.key}`)
    )
    const next = new Set(transitionPerms)
    if (allEnabled) {
      workflow.transitions.forEach((t) => next.delete(`${workflow.machineName}:${t.key}`))
    } else {
      workflow.transitions.forEach((t) => next.add(`${workflow.machineName}:${t.key}`))
    }
    onChange(next)
  }

  function toggleWorkflow(workflow: PublishedWorkflow) {
    const next = new Set(workflowPerms)
    if (next.has(workflow.machineName)) {
      next.delete(workflow.machineName)
      const transitions = new Set(transitionPerms)
      workflow.transitions.forEach((t) => transitions.delete(`${workflow.machineName}:${t.key}`))
      onChange(transitions)
    } else {
      next.add(workflow.machineName)
    }
    onWorkflowPermsChange(next)
  }

  if (loading) {
    return <div className="py-12 text-center text-sm text-muted-foreground">Loading workflows…</div>
  }

  if (error === 'insufficient_permissions') {
    return (
      <div className="py-12 text-center text-sm text-muted-foreground">
        Transition configuration requires <strong>workflow:read</strong> permission. Contact a
        system administrator to grant access.
      </div>
    )
  }

  if (error) {
    return (
      <div className="py-12 text-center text-sm text-muted-foreground">
        Failed to load workflows. Transition permissions cannot be edited at this time.
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-border p-4">
        <h3 className="text-sm font-semibold text-foreground">Workflow access</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          Limit this role to selected workflows. At least one workflow is required when restricted.
        </p>
        <div className="mt-3 flex gap-5 text-sm">
          <label className="flex items-center gap-2">
            <input type="radio" checked={!workflowRestricted} onChange={() => onWorkflowRestrictedChange(false)} disabled={disabled} />
            All workflows
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" checked={workflowRestricted} onChange={() => onWorkflowRestrictedChange(true)} disabled={disabled} />
            Selected workflows
          </label>
        </div>
        {workflowRestricted && (
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {workflows.map((workflow) => (
              <label key={workflow.machineName} className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm">
                <input
                  type="checkbox"
                  checked={workflowPerms.has(workflow.machineName)}
                  onChange={() => toggleWorkflow(workflow)}
                  disabled={disabled}
                />
                {workflow.name}
              </label>
            ))}
          </div>
        )}
      </div>
      <p className="text-sm text-muted-foreground">
        Allow this role to move records through workflow stages. Each switch grants one{' '}
        <strong>transition</strong> — the right to advance a record from one state to another.
      </p>

      <SearchInput value={search} onChange={setSearch} placeholder="Search transitions..." />

      {filtered.length === 0 && (
        <p className="py-8 text-center text-sm text-muted-foreground">
          {workflows.length === 0
            ? 'No published workflows found.'
            : 'No transitions match your search.'}
        </p>
      )}

      <div className="space-y-4">
        {filtered.filter((wf) => !workflowRestricted || workflowPerms.has(wf.machineName)).map((wf) => (
          <WorkflowGroup
            key={wf.machineName}
            workflow={wf}
            transitionPerms={transitionPerms}
            onToggle={toggle}
            onAllowAll={allowAll}
            roleColor={roleColor}
            disabled={disabled}
          />
        ))}
      </div>
    </div>
  )
}
