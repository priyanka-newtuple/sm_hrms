import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  RotateCcw,
  CheckCircle2,
  CircleAlert,
  AlertTriangle,
  ShieldCheck,
  Save,
  Loader2,
  Plus,
} from "lucide-react";
import type { StateMachineDocument } from "@/lib/state-machine/types";
import type { InspectorMode } from "../InspectorPanel";

interface EditorHeaderProps {
  doc: StateMachineDocument;
  isEditingExisting: boolean;
  isPublished: boolean;
  errorCount: number;
  warningCount: number;
  isValid: boolean;
  isValidating: boolean;
  isPublishing: boolean;
  isSavingDraft: boolean;
  mode: InspectorMode;
  onReset: () => void;
  onLoadExample: () => void;
  onValidate: () => void;
  onSaveDraft: () => void;
  onPublish: () => void;
  onAddState: () => void;
}

export function EditorHeader({
  doc,
  isEditingExisting,
  isPublished,
  errorCount,
  warningCount,
  isValid,
  isValidating,
  isPublishing,
  isSavingDraft,
  onReset,
  onLoadExample,
  onValidate,
  onSaveDraft,
  onPublish,
  onAddState,
}: EditorHeaderProps) {
  return (
    <header className="z-30 grid grid-cols-1 items-center gap-3 border-b border-border bg-background px-4 py-3 md:grid-cols-[1fr_auto_1fr]">
      <div className="ml-4 hidden items-center gap-2 text-xs text-muted-foreground md:flex">
        <span>Workflows</span>
        <span>/</span>
        <span className="font-medium text-foreground">
          {doc.definition.name || "Untitled machine"}
        </span>
        <Badge variant="secondary" className="font-mono text-[10px]">
          base v{doc.base_version}
        </Badge>
        {isEditingExisting && (
          <Badge variant="outline" className="text-[10px]">
            editing existing version
          </Badge>
        )}
      </div>

      <div className="flex items-center justify-center gap-2">
        <Button variant="ghost" size="default" onClick={onReset}>
          <RotateCcw className="mr-2 h-4 w-4" /> New
        </Button>
        <Button variant="outline" size="lg" onClick={onLoadExample}>
          Load example
        </Button>
        <Button
          variant="outline"
          size="default"
          onClick={onValidate}
          disabled={isValidating}
        >
          {isValidating ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <ShieldCheck className="mr-2 h-4 w-4" />
          )}
          Validate
        </Button>
        {isEditingExisting && (
          <Button
            variant="outline"
            size="default"
            onClick={onSaveDraft}
            disabled={isSavingDraft || isPublishing || isValidating}
          >
            {isSavingDraft ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Save className="mr-2 h-4 w-4" />
            )}
            Save as draft
          </Button>
        )}
        <Button variant="primary"
          size="default"
          onClick={onPublish}
          disabled={isPublishing || isValidating || isSavingDraft}
        >
          {isPublishing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
          {isEditingExisting || isPublished ? "Publish new version" : "Save machine"}
        </Button>
      </div>

      <div className="ml-auto flex items-center gap-2 justify-self-end">
        {isValid ? (
          <span className="hidden items-center gap-1.5 rounded-full border border-success/30 bg-success-subtle px-2.5 py-1 text-xs text-success sm:inline-flex">
            <CheckCircle2 className="h-3.5 w-3.5" /> Valid
          </span>
        ) : (
          <span className="hidden items-center gap-1.5 rounded-full border border-destructive/30 bg-destructive/10 px-2.5 py-1 text-xs text-destructive sm:inline-flex">
            <CircleAlert className="h-3.5 w-3.5" /> {errorCount}{" "}
            {errorCount === 1 ? "error" : "errors"}
          </span>
        )}
        {warningCount > 0 && (
          <span className="hidden items-center gap-1.5 rounded-full border border-warning/30 bg-warning-subtle px-2.5 py-1 text-xs text-warning sm:inline-flex">
            <AlertTriangle className="h-3.5 w-3.5" /> {warningCount}
          </span>
        )}
        {isPublished && (
          <span className="hidden items-center gap-1.5 rounded-full border border-cobalt-200 bg-cobalt-50 px-2.5 py-1 text-xs text-cobalt-700 sm:inline-flex">
            <CheckCircle2 className="h-3.5 w-3.5 text-[#0047AB]" />
            <span className="text-[#0047AB]">Published</span>
          </span>
        )}
        <Button variant="outline" size="sm" onClick={onAddState}>
          <Plus className="mr-1.5 h-3.5 w-3.5" /> Add state
        </Button>
      </div>
    </header>
  );
}
