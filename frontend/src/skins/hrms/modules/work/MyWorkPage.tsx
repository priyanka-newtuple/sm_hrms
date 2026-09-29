import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, ClipboardCheck } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { workApi, workError, type WorkView } from "@/skins/hrms/api/work";
import { useAuth } from "@/skins/hrms/auth/AuthContext";
import { Badge } from "@/skins/hrms/components/Badge";
import { Button } from "@/skins/hrms/components/Button";
import { Card } from "@/skins/hrms/components/Card";
import { FormError, Select } from "@/skins/hrms/components/Form";
import { formatDate } from "@/skins/hrms/modules/onboarding/shared";

export default function MyWorkPage() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const rawView = params.get("view");
  const view: WorkView = rawView === "waiting" || rawView === "completed" ? rawView : "todo";
  const page = Math.max(1, Number(params.get("page")) || 1);
  const kind = ["action", "approval"].includes(params.get("kind") ?? "") ? params.get("kind")! : "";
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["work", user?.employee_id, view, page, kind],
    queryFn: () => workApi.list(view, page, kind),
    refetchInterval: 30000,
    refetchOnWindowFocus: true,
  });
  const { data: counts } = useQuery({
    queryKey: ["work", user?.employee_id, "summary"], queryFn: workApi.summary,
    refetchInterval: 30000, refetchOnWindowFocus: true,
  });

  function change(next: { view?: string; page?: number; kind?: string }) {
    setParams({ view: next.view ?? view, kind: next.kind ?? kind, page: String(next.page ?? 1) });
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-light tracking-tight text-gray-900">My Work</h1>
        <p className="mt-1 text-sm text-gray-600">Your assigned actions and approvals, together in one place.</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Card><div className="flex items-center gap-3"><ClipboardCheck className="text-cobalt" size={22} />
          <div><div className="text-2xl text-gray-900">{counts?.actions ?? "—"}</div><p className="text-sm text-gray-600">Actions ready for you</p></div>
        </div></Card>
        <Card><div className="flex items-center gap-3"><CheckCircle2 className="text-cobalt" size={22} />
          <div><div className="text-2xl text-gray-900">{counts?.approvals ?? "—"}</div><p className="text-sm text-gray-600">Approvals to review</p></div>
        </div></Card>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-2" role="group" aria-label="Work status">
          {([['todo', 'To do'], ['waiting', 'Waiting'], ['completed', 'Completed']] as const).map(([key, label]) => (
            <button key={key} aria-pressed={view === key} onClick={() => change({ view: key })}
              className={`rounded-full px-4 py-2 text-sm font-medium ${view === key ? "bg-cobalt text-white" : "border border-gray-200 bg-white text-gray-600"}`}>
              {label}
            </button>
          ))}
        </div>
        <Select aria-label="Work type" value={kind} onChange={e => change({ kind: e.target.value })} className="!w-auto">
          <option value="">All work</option><option value="action">Actions</option><option value="approval">Approvals</option>
        </Select>
      </div>
      {view === "waiting" && <p className="text-sm text-gray-600">Assigned steps waiting on prerequisites and your documents awaiting HR review.</p>}
      {view === "completed" && <p className="text-sm text-gray-600">Completed assigned tasks and decisions you have made.</p>}
      {error ? <Card><FormError message={workError(error)} /><Button variant="secondary" onClick={() => refetch()}>Try again</Button></Card> :
        isLoading ? <p role="status" className="text-sm text-gray-600">Loading your work…</p> :
        <Card>
          {!data?.items.length ? <div className="py-10 text-center"><CheckCircle2 size={28} className="mx-auto mb-3 text-gray-400" />
            <p className="font-medium text-gray-900">{view === "todo" ? "You're all caught up" : "No items here"}</p>
            <p className="mt-1 text-sm text-gray-600">{view === "todo" ? "New work will appear here when it needs your attention." : "Items will appear as your workflow progresses."}</p>
          </div> : <ul className="divide-y divide-gray-100">
            {data.items.map(item => <li key={`${item.source}-${item.id}`}>
              <Link to={item.href ?? `/my-work/${item.source}/${item.id}`} className="flex items-center gap-4 rounded-xl px-2 py-5 hover:bg-gray-50">
                <div className="min-w-0 flex-1">
                  <div className="mb-2 flex flex-wrap gap-2"><Badge>{item.kind === "approval" ? "Approval" : "Action"}</Badge><Badge>{item.workflow_type}</Badge>
                    {item.overdue && <Badge tone="danger">Overdue</Badge>}</div>
                  <p className="font-medium text-gray-900">{item.title}</p>
                  <p className="mt-1 text-sm text-gray-600">{item.employee_name} · {item.department}</p>
                  <p className="mt-1 text-xs text-gray-600">{item.assignee_name} · {item.status === "pending" ? "Waiting on prerequisites" : item.status.replace(/_/g, ' ')}</p>
                </div>
                <span className="text-sm text-gray-600">{item.due_date ? `Due ${formatDate(item.due_date)}` : ""}</span>
                <ArrowRight size={18} className="shrink-0 text-gray-400" />
              </Link>
            </li>)}
          </ul>}
          {!!data?.total && <div className="mt-4 flex items-center justify-between border-t border-gray-100 pt-4">
            <span className="text-sm text-gray-600">{data.total} items · Page {page}</span>
            <div className="flex gap-2"><Button variant="secondary" disabled={page <= 1} onClick={() => change({ page: page - 1 })}>Previous</Button>
              <Button variant="secondary" disabled={page * data.page_size >= data.total} onClick={() => change({ page: page + 1 })}>Next</Button></div>
          </div>}
        </Card>}
    </div>
  );
}
