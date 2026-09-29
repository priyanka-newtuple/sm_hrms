import type {
  EmployeeDocumentStatus,
  EmployeeDocumentType,
  OnboardingTask,
  OnboardingTaskStatus,
} from "@/skins/hrms/api/types";

/** Segmented progress bar: one segment per step, filled when done/skipped. */
export function StepProgress({ done, total }: { done: number; total: number }) {
  if (total === 0) return null;
  return (
    <div className="flex items-center gap-2">
      <div className="flex w-28 gap-0.5">
        {Array.from({ length: total }).map((_, i) => (
          <div
            key={i}
            className={`h-1.5 flex-1 rounded-full ${i < done ? "bg-cobalt" : "bg-gray-200"}`}
          />
        ))}
      </div>
      <span className="text-xs text-gray-600">
        {done}/{total}
      </span>
    </div>
  );
}

export const TASK_STATUS_STYLES: Record<OnboardingTaskStatus, string> = {
  pending: "bg-gray-50 text-gray-500",
  ready: "bg-cobalt/10 text-cobalt",
  done: "bg-success/10 text-success",
  skipped: "bg-gray-100 text-gray-500",
};

export function TaskStatusBadge({ status }: { status: OnboardingTaskStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${TASK_STATUS_STYLES[status]}`}
    >
      {status}
    </span>
  );
}

export const DOC_TYPE_LABELS: Record<EmployeeDocumentType, string> = {
  id_proof: "Government ID proof",
  address_proof: "Address proof",
  pan: "PAN card",
  education_certificate: "Education certificates",
  experience_certificate: "Experience certificates",
  signed_offer_letter: "Signed offer letter",
  other: "Other document",
};

/** Doc types shown in the wizard/verification checklist, in display order.
 * Mirrors backend REQUIRED_DOCUMENT_TYPES + optional extras. */
export const CHECKLIST_DOC_TYPES: { type: EmployeeDocumentType; required: boolean }[] = [
  { type: "id_proof", required: true },
  { type: "pan", required: true },
  { type: "education_certificate", required: true },
  { type: "signed_offer_letter", required: true },
  { type: "experience_certificate", required: false },
  { type: "address_proof", required: false },
];

export const DOC_STATUS_STYLES: Record<EmployeeDocumentStatus, string> = {
  submitted: "bg-cobalt/10 text-cobalt",
  verified: "bg-success/10 text-success",
  rejected: "bg-danger/10 text-danger",
};

export function taskOwnerLabel(task: OnboardingTask): string {
  return task.assignee_name ?? task.assignee_role ?? "Unassigned";
}

export function formatDate(value?: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function isOverdue(task: OnboardingTask): boolean {
  return (
    task.status === "ready" &&
    !!task.due_date &&
    new Date(task.due_date).getTime() < new Date().setHours(0, 0, 0, 0)
  );
}
