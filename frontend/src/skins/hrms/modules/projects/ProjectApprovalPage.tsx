import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { projectApprovalsApi } from "@/skins/hrms/api/projects";
import type { Project } from "@/skins/hrms/api/types";
import { useAuth } from "@/skins/hrms/auth/AuthContext";
import { Badge } from "@/skins/hrms/components/Badge";
import { Button } from "@/skins/hrms/components/Button";
import { Card } from "@/skins/hrms/components/Card";
import { Field, FormError, TextArea } from "@/skins/hrms/components/Form";
import { apiErrorMessage } from "@/skins/hrms/lib/apiError";

const FIELDS: [keyof Project, string][] = [
  ["customer_id", "Customer"], ["project_manager_id", "Project manager"], ["delivery_manager_id", "Delivery manager"],
  ["name", "Project"], ["start_date", "Start date"], ["end_date", "End date"],
  ["engagement_type", "Engagement"], ["currency", "Currency"], ["practice", "Practice"],
  ["budgeted_hours", "Budgeted hours"], ["budget_amount", "Budget"], ["billing_rate", "Billing rate"],
  ["revenue", "Revenue"], ["margin_percent", "Margin %"], ["description", "Description"],
];

function display(value: unknown) {
  if (value === undefined || value === null || value === "") return "—";
  return String(value).replace(/_/g, " ");
}

export default function ProjectApprovalPage() {
  const { id = "" } = useParams();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [note, setNote] = useState("");
  const { data: request, isLoading, error } = useQuery({
    queryKey: ["project-review", user?.employee_id, id], queryFn: () => projectApprovalsApi.get(id),
    refetchOnWindowFocus: true,
  });
  async function refresh() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["project-review"] }),
      queryClient.invalidateQueries({ queryKey: ["project"] }),
      queryClient.invalidateQueries({ queryKey: ["projects"] }),
      queryClient.invalidateQueries({ queryKey: ["work"] }),
    ]);
  }
  const action = useMutation({
    mutationFn: (operation: "submit" | "withdraw" | "approve" | "changes_requested" | "reject") => {
      if (!request) throw new Error("Request not loaded");
      return operation === "submit" ? projectApprovalsApi.submit(id, request.version) :
        operation === "withdraw" ? projectApprovalsApi.withdraw(id, request.version) :
        projectApprovalsApi.decide(id, request.version, operation, note);
    },
    onSuccess: async () => { setNote(""); await refresh(); }, onError: refresh,
  });

  return <div className="mx-auto max-w-4xl space-y-5">
    <Link to="/my-work" className="inline-flex items-center gap-2 text-sm text-gray-600 hover:text-cobalt"><ArrowLeft size={16} /> My Work</Link>
    {isLoading ? <p role="status">Loading project request…</p> : error || !request ?
      <FormError message={error ? apiErrorMessage(error) : "This request is unavailable."} /> : <>
        <div className="flex flex-wrap items-center gap-3"><h1 className="text-2xl font-light text-gray-900">{request.kind === "amendment" ? "Project amendment" : "Project approval"}</h1><Badge>{request.status}</Badge></div>
        <p className="text-sm text-gray-600">{request.project_code} · {request.proposed.name} · Requested by {request.requester_name} · Version {request.version}</p>
        {request.note && <Card><p className="text-sm font-medium text-gray-900">Review note</p><p className="mt-2 whitespace-pre-wrap text-sm text-gray-700">{request.note}</p></Card>}
        <Card>
          <dl className="mb-5 grid gap-4 sm:grid-cols-3">
            <div><dt className="text-xs uppercase text-gray-600">Customer</dt><dd className="text-sm text-gray-900">{request.customer_name}</dd></div>
            <div><dt className="text-xs uppercase text-gray-600">Project manager</dt><dd className="text-sm text-gray-900">{request.project_manager_name}</dd></div>
            <div><dt className="text-xs uppercase text-gray-600">Delivery manager</dt><dd className="text-sm text-gray-900">{request.delivery_manager_name}</dd></div>
          </dl>
          {request.kind === "amendment" && <p className="mb-4 text-sm text-gray-600">Approved values remain in use until this amendment is approved. Highlighted rows contain proposed changes.</p>}
          <div className="overflow-x-auto"><table className="w-full text-left text-sm">
            <thead><tr className="border-b border-gray-200"><th className="py-3 pr-4">Field</th>{request.kind === "amendment" && <th className="py-3 pr-4">Currently approved</th>}<th className="py-3">{request.kind === "amendment" ? "Proposed" : "Submitted details"}</th></tr></thead>
            <tbody>{FIELDS.filter(([key]) => Object.prototype.hasOwnProperty.call(request.proposed, key)).map(([key, label]) => {
              const changed = request.kind === "amendment" && request.current[key] !== request.proposed[key];
              return <tr key={key} className={`border-b border-gray-100 ${changed ? "bg-cobalt/5" : ""}`}><th className="py-3 pr-4 align-top font-medium text-gray-600">{label}</th>
                {request.kind === "amendment" && <td className="whitespace-pre-wrap py-3 pr-4 align-top text-gray-600">{display(request.current_names[key] ?? request.current[key])}</td>}
                <td className="whitespace-pre-wrap py-3 text-gray-900">{display(key === "customer_id" ? request.customer_name : key === "project_manager_id" ? request.project_manager_name : key === "delivery_manager_id" ? request.delivery_manager_name : request.proposed[key])}</td></tr>;
            })}</tbody>
          </table></div>
        </Card>
        <Card>
          <FormError message={action.error ? apiErrorMessage(action.error) : null} />
          {request.can_review && <div className="space-y-4">
            <Field label="Review note" hint="Required when requesting changes or rejecting."><TextArea maxLength={4000} value={note} onChange={e => setNote(e.target.value)} /></Field>
            <div className="flex flex-wrap gap-2"><Button disabled={action.isPending} onClick={() => action.mutate("approve")}>Approve {request.kind === "amendment" ? "amendment" : "project"}</Button>
              <Button variant="secondary" disabled={action.isPending || !note.trim()} onClick={() => action.mutate("changes_requested")}>Request changes</Button>
              <Button variant="danger" disabled={action.isPending || !note.trim()} onClick={() => action.mutate("reject")}>Reject</Button></div>
          </div>}
          {request.can_submit && <div className="space-y-3"><p className="text-sm text-gray-600">Review the details above before submitting. Submitted details are locked during review.</p>
            <div className="flex flex-wrap gap-2"><Button disabled={action.isPending} onClick={() => action.mutate("submit")}>Submit for approval</Button><Link to={`/projects/${request.project_id}`}><Button variant="secondary">Edit draft</Button></Link></div></div>}
          {request.can_withdraw && <div className="space-y-3"><p className="text-sm text-gray-600">Waiting for a project approver. Withdraw the request to make changes.</p><Button variant="secondary" disabled={action.isPending} onClick={() => action.mutate("withdraw")}>Withdraw to edit</Button></div>}
          {!request.can_review && !request.can_submit && !request.can_withdraw && <p className="text-sm text-gray-600">No decision is required from you on this request.</p>}
        </Card>
        <Card><h2 className="mb-4 font-semibold text-gray-900">Request history</h2><ol className="space-y-4">{request.history.map((event, index) => <li key={index} className="border-l-2 border-gray-200 pl-4">
          <p className="text-sm text-gray-900">{display(event.action)} · {event.actor}</p><p className="text-xs text-gray-600">{new Date(event.at).toLocaleString()} · Version {event.version}</p>
          {event.note && <p className="mt-1 whitespace-pre-wrap text-sm text-gray-600">{event.note}</p>}
          {event.snapshot && <details className="mt-1 text-sm text-gray-600"><summary className="cursor-pointer">Details at this step</summary><dl className="mt-2 space-y-1">{FIELDS.filter(([key]) => key in event.snapshot!).map(([key, label]) => <div key={key}><dt className="inline font-medium">{label}: </dt><dd className="inline whitespace-pre-wrap">{display(event.snapshot![key])}</dd></div>)}</dl></details>}
        </li>)}</ol></Card>
        <Link to={`/projects/${request.project_id}`} className="inline-block text-sm text-cobalt">View project</Link>
      </>}
  </div>;
}
