import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { employeesApi } from "@/skins/hrms/api/employees";
import { onboardingApi } from "@/skins/hrms/api/onboarding";
import type { OnboardingRecord } from "@/skins/hrms/api/types";
import { usePermission } from "@/skins/hrms/auth/usePermission";
import { Badge } from "@/skins/hrms/components/Badge";
import { Button } from "@/skins/hrms/components/Button";
import { Card, CardHeader, CardTitle } from "@/skins/hrms/components/Card";
import { Modal } from "@/skins/hrms/components/Modal";
import { Table } from "@/skins/hrms/components/Table";
import { FEATURES } from "@/skins/hrms/lib/features";

import { formatDate, StepProgress } from "./shared";

type Tab = "onboarding" | "offboarding";

export default function OnboardingPage() {
  const [tab, setTab] = useState<Tab>("onboarding");
  const canCreate = usePermission(
    tab === "offboarding" ? FEATURES.EMPLOYEE_OFFBOARDING : FEATURES.EMPLOYEE_ONBOARDING,
    "create",
  );
  const [showStart, setShowStart] = useState(false);

  const TABS: { key: Tab; label: string }[] = [
    { key: "onboarding", label: "Onboarding" },
    { key: "offboarding", label: "Offboarding" },
  ];

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-light tracking-tight text-gray-900">Employee Onboarding</h1>
        {canCreate && (
          <Button onClick={() => setShowStart(true)}>
            <Plus size={16} /> Start {tab === "offboarding" ? "Offboarding" : "Onboarding"}
          </Button>
        )}
      </div>

      <div className="mb-6 flex gap-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`rounded-full px-4 py-2 text-sm font-medium transition-colors duration-hover ease-brand ${
              tab === t.key ? "bg-cobalt text-white" : "bg-white text-gray-600 border border-gray-200"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "onboarding" && <PipelineBoard />}
      {tab === "offboarding" && <OffboardingList />}

      {showStart && (
        <StartWorkflowModal
          workflowType={tab === "offboarding" ? "offboarding" : "onboarding"}
          onClose={() => setShowStart(false)}
        />
      )}
    </div>
  );
}

/** One row per hire: progress, the step it's waiting on, and whose desk it's on. */
function PipelineBoard() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["onboarding", "onboarding"],
    queryFn: () => onboardingApi.list("onboarding"),
  });

  if (isLoading) return <p className="text-sm text-gray-600">Loading…</p>;
  const records = data?.items ?? [];

  return (
    <Card>
      <Table<OnboardingRecord>
        rows={records}
        emptyMessage="No onboarding in progress. Start one to see the pipeline."
        columns={[
          {
            key: "hire",
            header: "New hire",
            render: (r) => (
              <Link to={`/onboarding/${r.id}`} className="group">
                <div className="font-medium text-gray-900 group-hover:text-cobalt">
                  {r.employee?.full_name ?? "Employee"}
                </div>
                <div className="text-xs text-gray-600">
                  {r.employee?.designation} · {r.employee?.department}
                </div>
              </Link>
            ),
          },
          {
            key: "joining",
            header: "Joining",
            render: (r) => formatDate(r.employee?.date_joined),
          },
          {
            key: "progress",
            header: "Progress",
            render: (r) => <StepProgress done={r.progress_done} total={r.progress_total} />,
          },
          {
            key: "waiting",
            header: "Waiting on",
            render: (r) =>
              r.status === "completed" ? (
                <span className="text-gray-600">All steps complete</span>
              ) : (
                (r.current_task_title ?? "—")
              ),
          },
          {
            key: "owner",
            header: "Owner",
            render: (r) =>
              r.status === "completed" ? (
                <Badge tone="success">completed</Badge>
              ) : r.current_assignee_name ? (
                <Badge tone="info">{r.current_assignee_name}</Badge>
              ) : (
                <span className="text-gray-600">—</span>
              ),
          },
          {
            key: "due",
            header: "Due",
            render: (r) => <DueCell due={r.current_due_date} />,
          },
          {
            key: "open",
            header: "",
            render: (r) => (
              <Button variant="ghost" onClick={() => navigate(`/onboarding/${r.id}`)}>
                Open
              </Button>
            ),
          },
        ]}
      />
    </Card>
  );
}

function DueCell({ due }: { due?: string | null }) {
  if (!due) return <span className="text-gray-600">—</span>;
  const overdue = new Date(due).getTime() < new Date().setHours(0, 0, 0, 0);
  return (
    <span className={overdue ? "font-medium text-danger" : "text-gray-900"}>
      {formatDate(due)}
      {overdue && " (overdue)"}
    </span>
  );
}

/** Offboarding keeps the simple checklist — it has no template flow (yet). */
function OffboardingList() {
  const { data, isLoading } = useQuery({
    queryKey: ["onboarding", "offboarding"],
    queryFn: () => onboardingApi.list("offboarding"),
  });


  if (isLoading) return <p className="text-sm text-gray-600">Loading…</p>;

  return (
    <div className="space-y-4">
      {(data?.items ?? []).map((record) => (
        <Card key={record.id}>
          <CardHeader>
            <CardTitle>{record.employee?.full_name ?? "Employee"}</CardTitle>
            <Badge>{record.status}</Badge>
          </CardHeader>
          <ul className="space-y-2">
            {record.tasks.map((task) => (
              <li key={task.id} className="flex items-center justify-between text-sm">
                <span
                  className={task.is_complete ? "text-gray-600 line-through" : "text-gray-900"}
                >
                  {task.title}
                </span>
                {!task.is_complete && (
                  <Link to={`/my-work/tasks/${task.id}`}><Button variant="secondary">Open task</Button></Link>
                )}
              </li>
            ))}
          </ul>
        </Card>
      ))}
      {data?.items.length === 0 && (
        <p className="py-8 text-center text-sm text-gray-600">No offboarding records yet.</p>
      )}
    </div>
  );
}

function StartWorkflowModal({
  workflowType,
  onClose,
}: {
  workflowType: "onboarding" | "offboarding";
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { data: employees } = useQuery({
    queryKey: ["employees"],
    queryFn: () => employeesApi.list(),
  });
  const [employeeId, setEmployeeId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const inputClass =
    "w-full rounded-xl border border-gray-200 px-3 py-2 text-sm focus:border-cobalt focus:outline-none";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const record = await onboardingApi.start(employeeId, workflowType);
      await queryClient.invalidateQueries({ queryKey: ["onboarding"] });
      onClose();
      if (workflowType === "onboarding") navigate(`/onboarding/${record.id}`);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: { message?: string } } } })
        .response?.data?.detail;
      setError(detail?.message ?? "Could not start the workflow.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open onClose={onClose} title={`Start ${workflowType}`}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <select
          required
          className={inputClass}
          value={employeeId}
          onChange={(e) => setEmployeeId(e.target.value)}
        >
          <option value="">Select employee…</option>
          {(employees?.items ?? []).map((e) => (
            <option key={e.id} value={e.id}>
              {e.full_name}
            </option>
          ))}
        </select>
        {workflowType === "onboarding" && (
          <p className="text-xs text-gray-600">
            Starting onboarding assigns each step to its owner (Office Admin, Finance, HR, the new
            hire, Delivery Manager) and emails the first assignees.
          </p>
        )}
        {error && <p className="text-sm text-danger">{error}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={submitting || !employeeId}>
            {submitting ? "Starting…" : "Start"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
