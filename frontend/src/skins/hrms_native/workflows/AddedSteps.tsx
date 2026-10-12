import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getApiErrorMessage, request } from '@/core/services/api/client';
import { createRequestId } from '../requestId';

type Step = { trigger: string; label: string; to_state: string };

/** Steps the organization added to this workflow in Settings → Funnels. HRMS has no rule of its own for
 * them, so they are offered to the people who manage the record. `onDemand` waits for a click before
 * asking the server (for long lists). */
export function AddedSteps({ entityId, onDemand = false }: { entityId: string; onDemand?: boolean }) {
  const client = useQueryClient();
  const [asked, setAsked] = useState(!onDemand);
  const steps = useQuery({ queryKey: ['hrms', 'workflow-steps', entityId], queryFn: () => request<{ steps: Step[] }>(`/hrms/workflow-steps/${entityId}`), enabled: asked });
  const run = useMutation({
    mutationFn: (trigger: string) => request(`/hrms/workflow-steps/${entityId}`, { method: 'POST', body: JSON.stringify({ trigger, idempotency_key: createRequestId() }) }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['hrms'] }),
  });
  if (!asked) return <button type="button" className="hrms-text-link" onClick={() => setAsked(true)}>Other steps</button>;
  if (!steps.data?.steps.length) return onDemand && steps.isSuccess ? <span className="text-sm text-slate-500">No other steps</span> : null;
  return <div className="flex flex-wrap items-center gap-2">
    <span className="text-sm text-slate-600">Other steps:</span>
    {steps.data.steps.map(step => <button key={step.trigger} type="button" className="hrms-outline-button" disabled={run.isPending}
      onClick={() => { if (window.confirm(`${step.label}?`)) run.mutate(step.trigger); }}>{step.label}</button>)}
    {run.isError && <span role="alert" className="text-sm text-red-700">{getApiErrorMessage(run.error)}</span>}
  </div>;
}
