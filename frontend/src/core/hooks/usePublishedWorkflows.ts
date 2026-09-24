import { useState, useEffect } from 'react'
import { stateMachines } from '@/core/services/api'
import type { StateMachineRecord } from '@/core/types'

export interface WorkflowTransition {
  key: string
  label: string
  from: string | string[]
  to_state: string
  description?: string
}

export interface PublishedWorkflow {
  machineKey: string
  machineName: string
  name: string
  entityType: string
  transitions: WorkflowTransition[]
}

interface RawTransition {
  key?: unknown
  label?: unknown
  from?: unknown
  to_state?: unknown
  description?: unknown
}

interface RawDefinition {
  transitions?: RawTransition[]
}

function isValidTransition(t: RawTransition): t is WorkflowTransition {
  return typeof t.key === 'string' && typeof t.label === 'string'
}

function dedupeActive(records: StateMachineRecord[]): StateMachineRecord[] {
  const latest = new Map<string, StateMachineRecord>()
  for (const rec of records) {
    if (!rec.is_active) continue
    const existing = latest.get(rec.machine_name)
    if (!existing || rec.version > existing.version) {
      latest.set(rec.machine_name, rec)
    }
  }
  return Array.from(latest.values())
}

function toPublishedWorkflow(rec: StateMachineRecord): PublishedWorkflow {
  const def = rec.definition as RawDefinition
  return {
    machineKey: rec.machine_key,
    machineName: rec.machine_name,
    name: rec.name ?? rec.machine_name,
    entityType: rec.entity_type,
    transitions: (def.transitions ?? []).filter(isValidTransition),
  }
}

export interface UsePublishedWorkflowsResult {
  workflows: PublishedWorkflow[]
  loading: boolean
  error: string | null
}

export function usePublishedWorkflows(): UsePublishedWorkflowsResult {
  const [workflows, setWorkflows] = useState<PublishedWorkflow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    stateMachines
      .list()
      .then((all) => {
        if (cancelled) return
        const mapped = dedupeActive(all)
          .map(toPublishedWorkflow)
          .sort((a, b) => a.name.localeCompare(b.name))
        setWorkflows(mapped)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        const status = (err as { status?: number }).status
        setError(status === 403 ? 'insufficient_permissions' : 'Failed to load workflows')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return { workflows, loading, error }
}
