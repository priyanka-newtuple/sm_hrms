import { useState } from 'react';

export type RecordAction = {trigger:string;label?:string;allowed?:boolean;blocked_reasons?:string[]};
/** Presentation only: callers supply authorized actions and retain their domain commands. */
export function MoveTo({actions,disabled=false,onAction}:{actions:RecordAction[];disabled?:boolean;onAction:(trigger:string)=>void}) {
  const [selected,setSelected]=useState('');
  const action=actions.find(a=>a.trigger===selected);
  if(!actions.length)return null;
  return <div className="flex flex-wrap items-end gap-3 py-3">
    <label className="min-w-60 flex-1 text-sm">Move to
      <select aria-label="Move to" className="hrms-field-input mt-2" value={action?selected:''} disabled={disabled}
        onChange={e=>setSelected(e.target.value)}>
        <option value="">Choose an action</option>
        {actions.map(a=><option key={a.trigger} value={a.trigger} disabled={a.allowed===false}>{a.label||a.trigger.replaceAll('_',' ')}</option>)}
      </select>
    </label>
    <button type="button" className="hrms-primary-button" disabled={disabled||!action||action.allowed===false}
      title={action?.blocked_reasons?.join('; ')} onClick={()=>{if(action&&action.allowed!==false)onAction(action.trigger);}}>Continue</button>
  </div>;
}
