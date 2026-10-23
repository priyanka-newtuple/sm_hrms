import { useId, useState, type ReactNode } from 'react';
import RecordActivity from './RecordActivity';
import RecordComments from './RecordComments';

/** Keep Details mounted so tab changes never discard a partly completed form. */
export function RecordTabs({ entityId, workflowId, scope, children }: {
  entityId: string; workflowId?: string; scope: string; children: ReactNode;
}) {
  const id = useId();
  const [tab, setTab] = useState('Details');
  const [visited, setVisited] = useState<string[]>(['Details']);
  return <div className="hrms-record-tabs">
    <div role="tablist" aria-label="Record information" className="flex gap-2 border-b border-blue-100 mb-5">
      {['Details', 'Activity', 'Comments'].map(label => <button key={label} type="button"
        role="tab" id={`${id}-${label}`} aria-selected={tab === label} aria-controls={`${id}-${label}-panel`}
        className={`px-4 py-3 border-b-2 font-medium ${tab === label ? 'border-[#0047AB] text-[#0047AB]' : 'border-transparent text-slate-500'}`}
        onClick={() => { setTab(label); setVisited(v => v.includes(label) ? v : [...v, label]); }}>
        {label}
      </button>)}
    </div>
    {['Details', 'Activity', 'Comments'].map(label => <div key={label} role="tabpanel"
      id={`${id}-${label}-panel`} aria-labelledby={`${id}-${label}`} hidden={tab !== label}>
      {label === 'Details' ? children : visited.includes(label) && (label === 'Activity'
        ? <RecordActivity entityId={entityId} scope={scope} orgUsers={[]} />
        : <RecordComments entityId={entityId} workflowId={workflowId} scope={scope} />)}
    </div>)}
  </div>;
}
