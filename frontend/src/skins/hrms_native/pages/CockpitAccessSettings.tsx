import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { request, getApiErrorMessage } from '@/core/services/api/client';
import { Button } from '@/components/ui/button';
type Policy={revision:number;capabilities:string[];roles:Record<string,string[]>};
const names:Record<string,string>={'cockpit:view':'Access HR Cockpit','cockpit:author':'Create and edit all content types','cockpit:jobs':'Create and edit jobs and job descriptions','cockpit:approve':'Approve content when designated','cockpit:publish':'Publish, withdraw and archive approved content'};
function Editor({policy}:{policy:Policy}) {
 const [roles,setRoles]=useState(policy.roles);
 const client=useQueryClient();
 const save=useMutation({mutationFn:()=>request('/hrms/settings/cockpit-access',{method:'PUT',body:JSON.stringify({roles,revision:policy.revision})}),onSuccess:()=>client.invalidateQueries({queryKey:['hrms']})});
 return <div className="space-y-3">
   <p className="text-sm text-muted-foreground">HR Basic can author drafts. Recruiters can author jobs. HR Full and Super Admin can approve and publish. Authors cannot approve their own content.</p>
   {Object.entries(roles).map(([role,grants])=><details key={role} className="rounded-lg border p-3"><summary className="cursor-pointer font-medium">{role.replace(/^hrms_/,'').replaceAll('_',' ')} · {grants.length} permissions</summary><div className="mt-3 grid gap-2 sm:grid-cols-2">{policy.capabilities.map(cap=><label key={cap} className="flex items-start gap-2 text-sm"><input type="checkbox" disabled={save.isPending} checked={grants.includes(cap)} onChange={e=>setRoles({...roles,[role]:e.target.checked?[...grants,cap]:grants.filter(c=>c!==cap)})}/>{names[cap]??cap}</label>)}</div></details>)}
   {save.isError&&<p role="alert" className="text-sm text-destructive">{getApiErrorMessage(save.error)}</p>}
   <Button variant="primary" disabled={save.isPending} onClick={()=>save.mutate()}>{save.isPending?'Saving…':'Save cockpit access'}</Button>
   <p className="text-xs text-muted-foreground">Changes apply to subsequent requests. Users with several roles receive their combined permissions. Native workflow state and independent approval checks remain mandatory.</p>
 </div>;
}
export default function CockpitAccessSettings() {
 const policy=useQuery({queryKey:['hrms','settings','cockpit-access'],queryFn:()=>request<Policy>('/hrms/settings/cockpit-access'),refetchOnWindowFocus:false});
 return <section className="mb-6 space-y-3 rounded-xl border p-4"><h2 className="text-lg font-semibold">HR Cockpit access</h2>{policy.isLoading&&<p>Loading access settings…</p>}{policy.isError&&<p role="alert">{getApiErrorMessage(policy.error)}</p>}{policy.data&&<Editor key={policy.data.revision} policy={policy.data}/>}</section>;
}
