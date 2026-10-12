import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { request, getApiErrorMessage } from '@/core/services/api/client';
import { Button } from '@/components/ui/button';
type Policy={revision:number;capabilities:string[];roles:Record<string,string[]>};
const names:Record<string,string>={'project:view':'Access Projects and Allocations','project:read_all':'View all projects','project:create':'Create projects','project:manage_assigned':'Manage assigned projects / designated PM allocation approval','project:manage_all':'Manage all projects','project:commercial_assigned':'View commercial data on assigned projects','project:commercial_all':'View all commercial data','project:approve':'Approve when designated (independent approver)','customer:create':'Create customers','allocation:request':'Request, amend and release allocations'};
function Editor({policy}:{policy:Policy}) {
 const [roles,setRoles]=useState(policy.roles);
 const client=useQueryClient();
 const save=useMutation({mutationFn:()=>request('/hrms/settings/project-access',{method:'PUT',body:JSON.stringify({roles,revision:policy.revision})}),onSuccess:()=>client.invalidateQueries({queryKey:['hrms']})});
 return <div className="space-y-3">
   <p className="text-sm text-muted-foreground">Project Managers manage projects assigned to them. Delivery Managers can manage all projects. Allocation requests require project management access and independent approval. These rules apply in the HRMS API, as well as the menu.</p>
   {Object.entries(roles).map(([role,grants])=><details key={role} className="rounded-lg border p-3"><summary className="cursor-pointer font-medium">{role.replace(/^hrms_/,'').replaceAll('_',' ')} · {grants.length} permissions</summary><div className="mt-3 grid gap-2 sm:grid-cols-2">{policy.capabilities.map(cap=><label key={cap} className="flex items-start gap-2 text-sm"><input type="checkbox" disabled={save.isPending} checked={grants.includes(cap)} onChange={e=>setRoles({...roles,[role]:e.target.checked?[...grants,cap]:grants.filter(c=>c!==cap)})}/>{names[cap]??cap}</label>)}</div></details>)}
   {save.isError&&<p role="alert" className="text-sm text-destructive">{getApiErrorMessage(save.error)}</p>}
   <Button variant="primary" disabled={save.isPending} onClick={()=>save.mutate()}>{save.isPending?'Saving…':'Save project and allocation access'}</Button>
   <p className="text-xs text-muted-foreground">Changes apply to subsequent requests. Users with several roles receive their combined permissions. Workflow state, capacity and designated-approver checks remain mandatory.</p>
 </div>;
}
export default function ProjectAccessSettings() {
 const policy=useQuery({queryKey:['hrms','settings','project-access'],queryFn:()=>request<Policy>('/hrms/settings/project-access'),refetchOnWindowFocus:false});
 return <section className="mb-6 space-y-3 rounded-xl border p-4"><h2 className="text-lg font-semibold">Project and allocation access</h2>{policy.isLoading&&<p>Loading access settings…</p>}{policy.isError&&<p role="alert">{getApiErrorMessage(policy.error)}</p>}{policy.data&&<Editor key={policy.data.revision} policy={policy.data}/>}</section>;
}
