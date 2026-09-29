import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, Download } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { onboardingApi } from "@/skins/hrms/api/onboarding";
import { workApi, workError, type WorkItem } from "@/skins/hrms/api/work";
import { useAuth } from "@/skins/hrms/auth/AuthContext";
import { Badge } from "@/skins/hrms/components/Badge";
import { Button } from "@/skins/hrms/components/Button";
import { Card } from "@/skins/hrms/components/Card";
import { Field, FormError, Select, TextArea, TextInput, WarningBanner } from "@/skins/hrms/components/Form";
import { formatDate } from "@/skins/hrms/modules/onboarding/shared";

export default function WorkDetailPage() {
  const { source = "tasks", id = "" } = useParams();
  const { user } = useAuth();
  const { data: item, isLoading, error, refetch } = useQuery({
    queryKey: ["work", user?.employee_id, source, id], queryFn: () => workApi.detail(source, id),
    enabled: ["tasks", "documents"].includes(source), refetchOnWindowFocus: true,
  });
  return <div className="mx-auto max-w-3xl space-y-5">
    <Link to="/my-work" className="inline-flex items-center gap-2 text-sm text-gray-600 hover:text-cobalt"><ArrowLeft size={16} /> My Work</Link>
    {isLoading ? <p role="status">Loading task…</p> : error || !item ? <Card>
      <FormError message={error ? workError(error) : "Work item not found."} />
      <p className="my-3 text-sm text-gray-600">This item may have been reassigned or may no longer be available to you.</p>
      <Button variant="secondary" onClick={() => refetch()}>Refresh</Button>
    </Card> : <TaskContent key={item.id} item={item} />}
  </div>;
}

function TaskContent({ item }: { item: WorkItem }) {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const [note, setNote] = useState("");
  const [payroll, setPayroll] = useState("");
  const [selected, setSelected] = useState("");
  const [start, setStart] = useState(new Date().toLocaleDateString("en-CA"));
  const [end, setEnd] = useState("");
  const [percent, setPercent] = useState(100);
  const [role, setRole] = useState("");
  const [reassigning, setReassigning] = useState(false);
  const [newOwner, setNewOwner] = useState("");
  const [reason, setReason] = useState("");
  const [warning, setWarning] = useState(false);
  const isAsset = item.action_type === "asset_assignment";
  const isAllocation = item.action_type === "project_allocation";
  const [overReason, setOverReason] = useState("");
  const [confirmedProposal, setConfirmedProposal] = useState("");
  const proposalKey = JSON.stringify([selected, start, end, percent]);
  const preview = useQuery({
    queryKey: ["allocation-preview", item.id, proposalKey],
    queryFn: () => workApi.allocationPreview(item.id, {project_id: selected, allocation_percent: percent,
      role_on_project: "Preview", start_date: start, end_date: end || undefined}),
    enabled: isAllocation && item.can_act && !!selected && !!start && (!end || end >= start) && percent > 0 && percent <= 100,
  });
  const optionsType = isAsset ? "assets" : "projects";
  const options = useQuery({
    queryKey: ["work", user?.employee_id, item.id, optionsType],
    queryFn: () => workApi.options(item.id, optionsType),
    enabled: item.can_act && (isAsset || isAllocation),
  });
  const owners = useQuery({
    queryKey: ["work", user?.employee_id, item.id, "assignees"],
    queryFn: () => workApi.options(item.id, "assignees"), enabled: reassigning,
  });
  const projectRoles = useQuery({
    queryKey: ["work", user?.employee_id, item.id, "project-roles"],
    queryFn: () => workApi.options(item.id, "project-roles"),
    enabled: item.can_act && isAllocation,
  });
  async function refresh() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["work"] }),
      queryClient.invalidateQueries({ queryKey: ["onboarding"] }),
    ]);
  }
  const save = useMutation({
    mutationFn: async () => {
      if (isAsset) await workApi.assignAsset(item.id, { asset_id: selected, assigned_date: start, condition_notes: note || undefined });
      else if (isAllocation) {
        const result = await workApi.allocate(item.id, { project_id: selected, allocation_percent: percent, role_on_project: role.trim(), start_date: start, end_date: end || undefined, confirm_overallocation: confirmedProposal === proposalKey, overallocation_reason: overReason });
        setWarning(result.over_allocated);
      } else await workApi.complete(item.id, { note: note || undefined, payroll_reference: payroll || undefined });
    },
    onSuccess: refresh,
    onError: refresh,
  });
  const review = useMutation({
    mutationFn: (status: "verified" | "rejected") => onboardingApi.reviewDocument(item.id, status, note || undefined),
    onSuccess: refresh, onError: refresh,
  });
  const reassign = useMutation({
    mutationFn: () => workApi.reassign(item.id, newOwner, reason),
    onSuccess: refresh, onError: refresh,
  });
  const busy = save.isPending || review.isPending || reassign.isPending;
  const selfService = ["employee_profile", "document_collection"].includes(item.action_type);

  function submit(event: FormEvent) { event.preventDefault(); save.mutate(); }

  return <>
    <div className="flex flex-wrap items-center gap-2"><Badge>{item.kind === "approval" ? "Approval" : "Action"}</Badge><Badge>{item.workflow_type}</Badge>
      <Badge>{item.status === "pending" ? "Waiting on prerequisites" : item.status}</Badge>{item.overdue && <Badge tone="danger">Overdue</Badge>}</div>
    <div><h1 className="text-2xl font-light text-gray-900">{item.title}</h1><p className="mt-2 text-sm text-gray-600">{item.employee_name} · {item.department} · Joining {formatDate(item.date_joined)}</p></div>
    <Card>
      {item.description && <p className="mb-4 text-sm text-gray-700">{item.description}</p>}
      <div className="mb-5 flex flex-wrap gap-4 text-sm text-gray-600"><span>Owner: {item.assignee_name}</span>{item.due_date && <span>Due {formatDate(item.due_date)}</span>}</div>
      {item.note && <p className="mb-4 rounded-xl bg-gray-50 p-3 text-sm text-gray-700">{item.note}</p>}
      {item.file_name && <a className="mb-5 inline-flex items-center gap-2 text-sm text-cobalt" href={onboardingApi.documentDownloadUrl(item.id)} target="_blank" rel="noreferrer"><Download size={16} /> {item.file_name}</a>}
      {!item.can_act && <p className="flex items-center gap-2 text-sm text-gray-600"><CheckCircle2 size={18} />
        {item.status === "pending" ? "This step will become actionable when its prerequisites are complete." : item.status === "submitted" ? "Waiting for an eligible HR reviewer." : "No action is required from you on this item."}</p>}
      {item.can_act && selfService && <Link to="/welcome"><Button>Continue My Onboarding</Button></Link>}
      {item.can_act && item.kind === "approval" && <div className="space-y-4 border-t border-gray-100 pt-4">
        <p className="text-sm text-gray-600">Review the document before approving. Request changes to send it back to the employee for a new upload.</p>
        <Field label="Review note" hint="A reason is required when requesting changes."><TextArea value={note} onChange={e => setNote(e.target.value)} /></Field>
        <FormError message={review.error ? workError(review.error) : null} />
        <div className="flex gap-2"><Button disabled={busy} onClick={() => review.mutate("verified")}>Approve document</Button>
          <Button variant="secondary" disabled={busy || !note.trim()} onClick={() => review.mutate("rejected")}>Request changes</Button></div>
      </div>}
      {item.can_act && !selfService && item.kind === "action" && item.action_type !== "invite_employee" && <form onSubmit={submit} className="space-y-4 border-t border-gray-100 pt-4">
        {(isAsset || isAllocation) && <>
          <Field label={isAsset ? "Available asset" : "Project"}>
            <Select required value={selected} onChange={e => setSelected(e.target.value)} disabled={options.isLoading || !!options.error}>
              <option value="">{options.isLoading ? "Loading…" : "Select an option"}</option>
              {options.data?.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
            </Select>
          </Field>
          {options.error && <FormError message={workError(options.error)} />}
          {!options.isLoading && !options.error && options.data?.length === 0 && <p className="text-sm text-gray-600">No eligible options are available. Contact HR or the module owner.</p>}
          <Field label={isAsset ? "Assigned date" : "Start date"}><TextInput required type="date" value={start} onChange={e => setStart(e.target.value)} /></Field>
        </>}
        {isAllocation && <>
          <Field label="End date (if the project has an end date)"><TextInput type="date" min={start} value={end} onChange={e => setEnd(e.target.value)} /></Field>
          <Field label="Allocation percentage"><TextInput required type="number" min="1" max="100" value={percent} onChange={e => setPercent(Number(e.target.value))} /></Field>
          {preview.error && <FormError message={workError(preview.error)} />}
          {preview.data && <div className="space-y-2 rounded border border-gray-200 p-3 text-sm">
            <p className="font-semibold">All allocations across projects · Proposed peak {preview.data.total_allocation_percent}%</p>
            {preview.data.allocations.map(a => <p key={a.allocation_id} className={a.over_allocated ? "text-red-800" : ""}>
              {a.project_name} · {a.manager_name} · {a.allocation_percent}% · {a.start_date} to {a.end_date ?? "ongoing"} · {a.status}{a.over_allocated ? " · Overallocated" : ""}
            </p>)}
            {preview.data.over_allocated && <div className="space-y-2 rounded bg-red-50 p-3 text-red-900">
              <strong>Overallocation warning</strong>
              {preview.data.overallocated_periods.map(p => <p key={p.start_date}>{p.start_date} to {p.end_date ?? "ongoing"}: {p.total_allocation_percent}% (+{p.excess_percent}%)</p>)}
              <Field label="Reason for overallocation"><TextArea required maxLength={2000} value={overReason} onChange={e => setOverReason(e.target.value)} /></Field>
              <label><input type="checkbox" checked={confirmedProposal === proposalKey} onChange={e => setConfirmedProposal(e.target.checked ? proposalKey : "")} /> Confirm overallocation and notify HR, Super Admin and me.</label>
            </div>}
          </div>}
          <Field label="Role on project"><Select required value={role} onChange={e => setRole(e.target.value)}>
            <option value="">Select project role…</option>
            {projectRoles.data?.map(option => <option key={option.id} value={option.label}>{option.label}</option>)}
          </Select></Field>
        </>}
        {item.payroll_required && <Field label="Payroll reference ID"><TextInput required value={payroll} onChange={e => setPayroll(e.target.value)} /></Field>}
        {!isAllocation && <Field label={isAsset ? "Condition / handover notes (optional)" : "Completion note (optional)"}><TextArea maxLength={2000} value={note} onChange={e => setNote(e.target.value)} /></Field>}
        <FormError message={save.error ? workError(save.error) : null} />
        <Button type="submit" disabled={busy || (isAllocation && (!preview.data || preview.isFetching || !!preview.error || (preview.data.over_allocated && (confirmedProposal !== proposalKey || !overReason.trim())))) || ((isAsset || isAllocation) && !selected) || (item.payroll_required && !payroll.trim())}>
          {busy ? "Saving…" : isAsset ? "Assign asset and complete task" : isAllocation ? "Create allocation and complete task" : "Complete task"}
        </Button>
      </form>}
    </Card>
    {warning && <WarningBanner title="Allocation saved">This employee's total allocation exceeds 100%.</WarningBanner>}
    {item.record_id && <Link className="inline-block text-sm text-cobalt" to={`/onboarding/${item.record_id}`}>View workflow progress</Link>}
    {item.can_reassign && !selfService && item.action_type !== "invite_employee" && <Card>
      <Button variant="secondary" onClick={() => setReassigning(!reassigning)}>Reassign task</Button>
      {reassigning && <form className="mt-4 space-y-4" onSubmit={e => { e.preventDefault(); reassign.mutate(); }}>
        <Field label="New owner"><Select required value={newOwner} onChange={e => setNewOwner(e.target.value)}><option value="">Select an active employee</option>{owners.data?.map(o => <option value={o.id} key={o.id}>{o.label}</option>)}</Select></Field>
        <Field label="Reason"><TextArea required maxLength={2000} value={reason} onChange={e => setReason(e.target.value)} /></Field>
        <FormError message={owners.error ? workError(owners.error) : reassign.error ? workError(reassign.error) : null} />
        <Button type="submit" disabled={busy || !newOwner || !reason.trim()}>Save assignment</Button>
      </form>}
    </Card>}
  </>;
}
