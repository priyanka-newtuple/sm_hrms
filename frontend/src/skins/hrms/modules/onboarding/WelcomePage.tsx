import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { employeesApi } from "@/skins/hrms/api/employees";
import { onboardingApi } from "@/skins/hrms/api/onboarding";
import type { EmployeeDocument, EmployeeDocumentType } from "@/skins/hrms/api/types";
import { useAuth } from "@/skins/hrms/auth/AuthContext";
import { Button } from "@/skins/hrms/components/Button";
import { Card } from "@/skins/hrms/components/Card";
import { Field, TextInput } from "@/skins/hrms/components/Form";

import {
  CHECKLIST_DOC_TYPES,
  DOC_STATUS_STYLES,
  DOC_TYPE_LABELS,
  formatDate,
} from "./shared";

type WizardStep = "personal" | "bank" | "documents";

/**
 * New-hire self-service wizard. Reached from the invitation email
 * (/welcome?token=...). Submitting personal + bank details completes the
 * "Employee fills personal & bank details" onboarding step; uploads feed the
 * document-collection step, which HR verifies.
 */
export default function WelcomePage() {
  const { user } = useAuth();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const acceptedRef = useRef(false);

  // Mark the invitation accepted (best-effort; the wizard works without it).
  useEffect(() => {
    const token = searchParams.get("token");
    if (token && !acceptedRef.current) {
      acceptedRef.current = true;
      onboardingApi.acceptInvitation(token).catch(() => undefined);
    }
  }, [searchParams]);

  const { data: onboarding, isLoading } = useQuery({
    queryKey: ["onboarding", "me"],
    queryFn: onboardingApi.myOnboarding,
  });
  const { data: me } = useQuery({
    queryKey: ["employees", user?.employee_id],
    queryFn: () => employeesApi.get(user!.employee_id),
    enabled: !!user,
  });

  const profileTask = onboarding?.tasks.find((t) => t.action_type === "employee_profile");
  const docsTask = onboarding?.tasks.find((t) => t.action_type === "document_collection");
  const profileDone = profileTask ? profileTask.status !== "ready" && profileTask.status !== "pending" : false;

  const [step, setStep] = useState<WizardStep | null>(null);
  const activeStep: WizardStep = step ?? (profileDone ? "documents" : "personal");

  const [form, setForm] = useState({
    phone: "",
    personal_email: "",
    date_of_birth: "",
    address: "",
    bank_account_number: "",
    bank_ifsc: "",
  });
  const [prefilled, setPrefilled] = useState(false);
  useEffect(() => {
    if (me && !prefilled) {
      setForm({
        phone: me.phone ?? "",
        personal_email: me.personal_email ?? "",
        date_of_birth: me.date_of_birth ?? "",
        address: me.address ?? "",
        bank_account_number: me.bank_account_number ?? "",
        bank_ifsc: me.bank_ifsc ?? "",
      });
      setPrefilled(true);
    }
  }, [me, prefilled]);

  const submitProfile = useMutation({
    mutationFn: () =>
      onboardingApi.submitProfile(
        Object.fromEntries(Object.entries(form).filter(([, v]) => v !== "")),
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["onboarding"] });
      setStep("documents");
    },
  });

  if (isLoading) return <p className="text-sm text-gray-600">Loading…</p>;

  if (!onboarding) {
    return (
      <Card className="mx-auto max-w-lg text-center">
        <h1 className="mb-2 text-xl font-semibold text-gray-900">Welcome!</h1>
        <p className="text-sm text-gray-600">
          There's no onboarding in progress for your account. If you believe this is a mistake,
          contact HR.
        </p>
      </Card>
    );
  }

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const STEPS: { key: WizardStep; label: string }[] = [
    { key: "personal", label: "1 · Personal" },
    { key: "bank", label: "2 · Bank & payroll" },
    { key: "documents", label: "3 · Documents" },
  ];

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="mb-1 text-2xl font-light tracking-tight text-gray-900">
        Welcome to Newtuple{user ? `, ${user.full_name.split(" ")[0]}` : ""}!
      </h1>
      <p className="mb-6 text-sm text-gray-600">
        Complete these three steps so HR, Finance and IT can finish setting you up. Your progress
        is saved as you go.
      </p>

      <div className="mb-6 flex gap-2">
        {STEPS.map((s) => (
          <button
            key={s.key}
            onClick={() => setStep(s.key)}
            className={`rounded-full px-4 py-2 text-sm font-medium transition-colors duration-hover ease-brand ${
              activeStep === s.key
                ? "bg-cobalt text-white"
                : "bg-white text-gray-600 border border-gray-200"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {profileDone && activeStep !== "documents" && (
        <p className="mb-4 flex items-center gap-2 rounded-xl bg-success/5 px-3 py-2 text-sm text-success">
          <CheckCircle2 size={16} /> Personal &amp; bank details submitted — you can still update
          them below.
        </p>
      )}

      {activeStep === "personal" && (
        <Card className="space-y-4">
          <Field label="Personal email" hint="Used before your work account is fully set up.">
            <TextInput type="email" value={form.personal_email} onChange={set("personal_email")} />
          </Field>
          <Field label="Phone">
            <TextInput value={form.phone} onChange={set("phone")} placeholder="+91…" />
          </Field>
          <Field label="Date of birth">
            <TextInput type="date" value={form.date_of_birth} onChange={set("date_of_birth")} />
          </Field>
          <Field label="Current address">
            <TextInput value={form.address} onChange={set("address")} />
          </Field>
          <div className="flex justify-end">
            <Button onClick={() => setStep("bank")}>Continue</Button>
          </div>
        </Card>
      )}

      {activeStep === "bank" && (
        <Card className="space-y-4">
          <p className="text-sm text-gray-600">
            Your salary is paid to this account. Finance links it to your Razorpay payroll profile.
          </p>
          <Field label="Bank account number">
            <TextInput
              value={form.bank_account_number}
              onChange={set("bank_account_number")}
            />
          </Field>
          <Field label="IFSC code">
            <TextInput value={form.bank_ifsc} onChange={set("bank_ifsc")} placeholder="HDFC0001234" />
          </Field>
          <div className="flex justify-between">
            <Button variant="ghost" onClick={() => setStep("personal")}>
              Back
            </Button>
            <Button onClick={() => submitProfile.mutate()} disabled={submitProfile.isPending}>
              {submitProfile.isPending ? "Saving…" : "Submit details"}
            </Button>
          </div>
        </Card>
      )}

      {activeStep === "documents" && (
        <DocumentsStep
          employeeId={onboarding.employee_id}
          documents={onboarding.documents}
          docsTaskDone={docsTask ? docsTask.status === "done" : false}
        />
      )}
    </div>
  );
}

function DocumentsStep({
  employeeId,
  documents,
  docsTaskDone,
}: {
  employeeId: string;
  documents: EmployeeDocument[];
  docsTaskDone: boolean;
}) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  // Latest upload per type wins (re-uploads supersede rejected ones).
  const latestByType = new Map<EmployeeDocumentType, EmployeeDocument>();
  for (const doc of documents) {
    const existing = latestByType.get(doc.doc_type);
    if (!existing || doc.created_at >= existing.created_at) latestByType.set(doc.doc_type, doc);
  }

  const upload = useMutation({
    mutationFn: ({ docType, file }: { docType: EmployeeDocumentType; file: File }) =>
      onboardingApi.uploadDocument(employeeId, docType, file),
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ["onboarding"] });
    },
    onError: () => setError("Upload failed — PDF or image up to 15 MB."),
  });

  return (
    <Card>
      {docsTaskDone ? (
        <p className="mb-4 flex items-center gap-2 rounded-xl bg-success/5 px-3 py-2 text-sm text-success">
          <CheckCircle2 size={16} /> All required documents are verified. You're done here!
        </p>
      ) : (
        <p className="mb-4 text-sm text-gray-600">
          Upload each document below (PDF or photo). HR verifies them — you'll get an email if
          anything needs a re-upload.
        </p>
      )}
      {error && <p className="mb-3 text-sm text-danger">{error}</p>}
      <ul className="divide-y divide-gray-100">
        {CHECKLIST_DOC_TYPES.map(({ type, required }) => (
          <DocumentRow
            key={type}
            type={type}
            required={required}
            doc={latestByType.get(type)}
            uploading={upload.isPending}
            onUpload={(file) => upload.mutate({ docType: type, file })}
          />
        ))}
      </ul>
    </Card>
  );
}

function DocumentRow({
  type,
  required,
  doc,
  uploading,
  onUpload,
}: {
  type: EmployeeDocumentType;
  required: boolean;
  doc?: EmployeeDocument;
  uploading: boolean;
  onUpload: (file: File) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const needsUpload = !doc || doc.status === "rejected";

  return (
    <li className="flex flex-wrap items-center gap-3 py-3">
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-gray-900">
          {DOC_TYPE_LABELS[type]}
          {!required && <span className="ml-1 text-xs font-normal text-gray-500">(optional)</span>}
        </div>
        {doc ? (
          <div className="text-xs text-gray-600">
            {doc.file_name} · uploaded {formatDate(doc.created_at)}
          </div>
        ) : (
          <div className="text-xs text-gray-500">Not uploaded yet</div>
        )}
        {doc?.status === "rejected" && doc.note && (
          <div className="text-xs text-danger">Rejected: {doc.note} — please re-upload.</div>
        )}
      </div>
      {doc && (
        <span
          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${DOC_STATUS_STYLES[doc.status]}`}
        >
          {doc.status}
        </span>
      )}
      {needsUpload && (
        <>
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf,image/jpeg,image/png,image/webp"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) onUpload(file);
              e.target.value = "";
            }}
          />
          <Button variant="secondary" disabled={uploading} onClick={() => inputRef.current?.click()}>
            <Upload size={14} /> {doc ? "Re-upload" : "Upload"}
          </Button>
        </>
      )}
    </li>
  );
}
