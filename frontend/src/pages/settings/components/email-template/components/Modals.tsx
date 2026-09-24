import { useEffect } from "react";
import Modal from "../../../../../core/components/Modal";
import { Button } from "@/components/ui/button.tsx";
import { cn } from "@/lib/utils";
import { htmlToPreview } from "../utils/html.ts";
import type { Template } from "../types";

// theme-exempt:start — WYSIWYG. Typography of the rendered email preview;
// matches the recipient's white inbox, so it stays light in dark mode.
const previewContentClass = cn(
  "text-sm leading-7 text-slate-900",
  "[&_p]:mb-3 [&_a]:text-blue-600 [&_a]:underline",
  "[&_img]:max-w-full [&_img]:rounded-md",
  "[&_.email-btn]:inline-block [&_.email-btn]:rounded-lg [&_.email-btn]:bg-blue-600 [&_.email-btn]:px-4 [&_.email-btn]:py-2.5 [&_.email-btn]:font-semibold [&_.email-btn]:text-white [&_.email-btn]:no-underline",
  "[&_.var-chip]:inline-flex [&_.var-chip]:rounded-md [&_.var-chip]:bg-blue-50 [&_.var-chip]:px-2 [&_.var-chip]:py-0.5 [&_.var-chip]:font-mono [&_.var-chip]:text-[12px] [&_.var-chip]:font-medium [&_.var-chip]:text-blue-700",
);
// theme-exempt:end
interface PreviewModalProps {
  draft: Template;
  onClose: () => void;
}

export function PreviewModal({ draft, onClose }: PreviewModalProps) {
  const subject = (draft.subject || "").replace(/\{\{([\w.]+)\}\}/g, (_, k: string) => `[${k}]`);
  const body = htmlToPreview(draft.bodyHtml || "");

  return (
    <Modal open onClose={onClose} title="Preview" size="lg">
      <div className="mb-4 text-sm text-muted-foreground">
        Variables are highlighted — they'll be replaced with real values when sent.
      </div>
      <div className="-mx-6 bg-muted/50 px-6 py-5">
        {/* theme-exempt:start — WYSIWYG. A faithful render of the sent email, which
            arrives on white in the recipient's inbox; stays light in dark mode. */}
        <div className="mx-auto max-w-[600px] overflow-hidden rounded-[16px] border border-slate-200 bg-white shadow-[0_16px_36px_-32px_rgba(15,23,42,0.28)]">
          <div className="border-b border-slate-200 px-5 py-3.5">
            <div className="text-sm font-semibold text-slate-950">Workflow Bot &lt;workflows@yourapp.com&gt;</div>
            <div className="mt-0.5 text-xs text-slate-500">
              to <span className="text-slate-900">recipient@example.com</span>
            </div>
          </div>
          <div className="border-b border-slate-200 px-5 py-3.5 text-base font-semibold text-slate-950">
            {subject || <span className="text-slate-400">(no subject)</span>}
          </div>
          <div className={cn("px-5 py-4", previewContentClass)} dangerouslySetInnerHTML={{ __html: body }} />
        </div>
        {/* theme-exempt:end */}
      </div>
      <div className="mt-4 flex items-center justify-between">
        <div className="text-xs text-muted-foreground">
          Rendering at 600px — typical email client width.
        </div>
        <Button variant="outline" onClick={onClose}>Close</Button>
      </div>
    </Modal>
  );
}

interface ConfirmModalProps {
  title: string;
  message: string;
  confirmLabel: string;
  danger?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function ConfirmModal({
  title, message, confirmLabel, danger, onCancel, onConfirm,
}: ConfirmModalProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
      const tag = (e.target as HTMLElement | null)?.tagName ?? "";
      if (e.key === "Enter" && tag !== "INPUT" && tag !== "TEXTAREA") onConfirm();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onCancel, onConfirm]);

  return (
    <Modal open onClose={onCancel} title={title} size="sm" showClose={false}>
      <p className="text-sm text-muted-foreground">{message}</p>
      <div className="mt-6 flex justify-end gap-2">
        <Button variant="outline" onClick={onCancel}>Stay</Button>
        <Button
          variant={danger ? "destructive" : "primary"}
          onClick={onConfirm}
        >
          {confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}

export function SavedToast() {
  return (
    <div className="fixed bottom-6 left-1/2 z-[60] flex -translate-x-1/2 items-center gap-2 rounded-full bg-foreground px-4 py-2.5 text-sm text-background shadow-2xl shadow-slate-900/25 animate-in slide-in-from-bottom-2 fade-in duration-150">
      <span className="h-1.5 w-1.5 rounded-full bg-success" />
      Template saved
    </div>
  );
}
