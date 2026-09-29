import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Download } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { onboardingApi } from "@/skins/hrms/api/onboarding";
import type { OnboardingDetail, OnboardingTask } from "@/skins/hrms/api/types";
import { Badge } from "@/skins/hrms/components/Badge";
import { Button } from "@/skins/hrms/components/Button";
import { Card } from "@/skins/hrms/components/Card";
import { Field, TextInput } from "@/skins/hrms/components/Form";

import {
  DOC_STATUS_STYLES,
  DOC_TYPE_LABELS,
  formatDate,
  isOverdue,
  StepProgress,
  TaskStatusBadge,
  taskOwnerLabel,
} from "./shared";

export default function OnboardingDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const { data: record, isLoading, error } = useQuery({
    queryKey: ["onboarding", "detail", id],
    queryFn: () => onboardingApi.detail(id!),
    enabled: !!id,
  });
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);

  if (error) return <p className="text-sm text-danger">This workflow is unavailable or outside your access.</p>;

  if (isLoading || !record) {
    return <p className="text-sm text-gray-600">Loading…</p>;
  }

  const selected =
    record.tasks.find((t) => t.id === selectedTaskId) ??
    record.tasks.find((t) => t.status === "ready") ??
    record.tasks[record.tasks.length - 1];

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["onboarding"] });
  }

  return (
    <div>
      <Link
        to="/onboarding"
        className="mb-4 inline-flex items-center gap-1 text-sm text-gray-600 hover:text-cobalt"
      >
        <ArrowLeft size={14} /> Onboarding pipeline
      </Link>

      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-light tracking-tight text-gray-900">
            {record.employee?.full_name ?? "Employee"}
          </h1>
          <p className="text-sm text-gray-600">
            {record.employee?.designation} · {record.employee?.department} · joining{" "}
            {formatDate(record.employee?.date_joined)}
          </p>
        </div>
        <div className="flex items-center gap-4">
          <StepProgress done={record.progress_done} total={record.progress_total} />
          <Badge>{record.status}</Badge>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,320px)_1fr]">
        <Card className="h-fit">
          <h3 className="mb-4 text-xs font-medium uppercase tracking-wider text-gray-600">
            Steps
          </h3>
          <ol className="space-y-1">
            {record.tasks.map((task) => (
              <TimelineRow
                key={task.id}
                task={task}
                selected={task.id === selected?.id}
                onSelect={() => setSelectedTaskId(task.id)}
              />
            ))}
          </ol>
        </Card>

        <div className="space-y-6">
          {selected && (
            <TaskPanel key={selected.id} record={record} task={selected} onChanged={refresh} />
          )}
          <DocumentsPanel record={record} />
        </div>
      </div>
    </div>
  );
}

function TimelineRow({
  task,
  selected,
  onSelect,
}: {
  task: OnboardingTask;
  selected: boolean;
  onSelect: () => void;
}) {
  const dotClass =
    task.status === "done"
      ? "bg-success"
      : task.status === "skipped"
        ? "bg-gray-300"
        : task.status === "ready"
          ? "border-2 border-cobalt bg-white"
          : "bg-gray-200";
  return (
    <li>
      <button
        onClick={onSelect}
        className={`flex w-full items-start gap-3 rounded-xl px-3 py-2 text-left transition-colors duration-hover ease-brand ${
          selected ? "bg-cobalt/5" : "hover:bg-gray-50"
        }`}
      >
        <span className={`mt-1 h-2.5 w-2.5 flex-shrink-0 rounded-full ${dotClass}`} />
        <span className="min-w-0 flex-1">
          <span
            className={`block text-sm ${
              task.status === "ready" ? "font-medium text-gray-900" : "text-gray-700"
            } ${task.status === "skipped" ? "line-through" : ""}`}
          >
            {task.title}
          </span>
          <span className="block text-xs text-gray-600">
            {task.status === "done" || task.status === "skipped"
              ? `${task.completed_by_name ?? "System"} · ${formatDate(task.completed_at)}`
              : `${taskOwnerLabel(task)}${task.due_date ? ` · due ${formatDate(task.due_date)}` : ""}`}
            {isOverdue(task) && <span className="font-medium text-danger"> · overdue</span>}
          </span>
        </span>
      </button>
    </li>
  );
}

/** Contextual action panel for the selected step. */
function TaskPanel({
  record,
  task,
  onChanged,
}: {
  record: OnboardingDetail;
  task: OnboardingTask;
  onChanged: () => Promise<void>;
}) {
  const [note, setNote] = useState("");
  const skip = useMutation({
    mutationFn: () => onboardingApi.skipTask(record.id, task.id, note),
    onSuccess: onChanged,
  });
  return <Card>
    <div className="mb-3 flex items-center justify-between">
      <h3 className="text-base font-semibold text-gray-900">{task.title}</h3>
      <TaskStatusBadge status={task.status} />
    </div>
    <p className="mb-3 text-sm text-gray-600">{task.description}</p>
    <p className="mb-4 text-sm text-gray-600">Owner: {taskOwnerLabel(task)}</p>
    {task.completion_note && <p className="mb-4 text-sm text-gray-600">{task.completion_note}</p>}
    <Link to={`/my-work/tasks/${task.id}`}><Button variant="secondary">Open task / manage assignment</Button></Link>
    {(task.status === "ready" || task.status === "pending") && <div className="mt-5 space-y-3 border-t border-gray-100 pt-4">
      <Field label="Reason for skipping (required)"><TextInput value={note} onChange={e => setNote(e.target.value)} /></Field>
      {skip.isError && <p className="text-sm text-danger">Could not skip this step. Refresh and try again.</p>}
      <Button variant="ghost" disabled={skip.isPending || !note.trim()} onClick={() => skip.mutate()}>Skip step</Button>
    </div>}
  </Card>;
}

/** Documents stay visible to process owners; decisions use the focused review. */
function DocumentsPanel({ record }: { record: OnboardingDetail }) {
  if (record.workflow_type !== "onboarding") return null;
  return <Card>
    <h3 className="mb-4 text-base font-semibold text-gray-900">Documents</h3>
    {!record.documents.length ? <p className="text-sm text-gray-600">No documents uploaded yet.</p> :
      <ul className="divide-y divide-gray-100">{record.documents.map(doc => <li key={doc.id} className="flex flex-wrap items-center gap-3 py-3">
        <div className="min-w-0 flex-1"><p className="text-sm font-medium text-gray-900">{DOC_TYPE_LABELS[doc.doc_type]}</p>
          <p className="text-xs text-gray-600">{doc.file_name} � uploaded {formatDate(doc.created_at)}</p>
          {doc.note && <p className="text-xs text-gray-600">{doc.note}</p>}
        </div>
        <span className={`rounded-full px-2.5 py-0.5 text-xs ${DOC_STATUS_STYLES[doc.status]}`}>{doc.status}</span>
        <a href={onboardingApi.documentDownloadUrl(doc.id)} target="_blank" rel="noreferrer" aria-label={`Download ${doc.file_name}`}><Download size={16} /></a>
        <Link to={`/my-work/documents/${doc.id}`}><Button variant="secondary">Open review</Button></Link>
      </li>)}</ul>}
  </Card>;
}
