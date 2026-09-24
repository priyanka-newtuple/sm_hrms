import {
  IconPencil, IconEye, IconTrash, IconX, IconSave, IconSparkle, IconChevron,
} from "./Icons.tsx";
import { Lock } from "lucide-react";
import { RichEditor } from "./Editor.tsx";
import { SubjectInput } from "./SubjectInput.tsx";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button.tsx";
import { Input } from "@/components/ui/input.tsx";
import { systemTagClass } from "../styles";
import type { EntityType, FormOption, Template, TemplateValidationErrors, Variable } from "../types";


const selectTriggerClass =
  "flex h-10 w-full items-center justify-between rounded-lg border border-border bg-card px-3 text-left text-sm text-foreground shadow-sm outline-none transition focus-visible:border-border focus-visible:ring-2 focus-visible:ring-border/10";

interface EditViewProps {
  draft: Template;
  editing: Template | undefined;
  dirty: boolean;
  entityTypes: EntityType[];
  formOptions: FormOption[];
  availableVariables: Variable[];
  validationErrors: TemplateValidationErrors;
  saveError: string | null;
  deleteError: string | null;
  isSaving: boolean;
  isDeleting: boolean;
  onUpdate: (patch: Partial<Template>) => void;
  onEntityTypeChange: (entityType: string | null) => void;
  onFormChange: (formId: string | null) => void;
  onSave: () => void;
  onCancel: () => void;
  onDelete: () => void;
  onPreview: () => void;
  onBack: () => void;
  canWrite?: boolean;
}

export function EditView({
  draft,
  editing,
  dirty,
  entityTypes,
  formOptions,
  availableVariables,
  validationErrors,
  saveError,
  deleteError,
  isSaving,
  isDeleting,
  onUpdate,
  onEntityTypeChange,
  onFormChange,
  onSave,
  onCancel,
  onDelete,
  onPreview,
  onBack,
  canWrite = true,
}: EditViewProps) {
  const currentEntity = entityTypes.find((entityType) => entityType.value === draft.entityType);
  const currentForm = formOptions.find((form) => form.value === draft.formId);

  return (
    <>
        <div className="flex flex-col gap-4 px-5 py-5 lg:flex-row lg:items-end lg:justify-between lg:px-6">
          <div className="space-y-2">
            <button
              className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-sm font-medium text-muted-foreground transition hover:bg-muted hover:text-foreground"
              onClick={onBack}
            >
              <IconChevron className="h-3.5 w-3.5 rotate-90" />
              All templates
            </button>
            <div className="space-y-1.5">
              <div className="inline-flex items-center gap-2 rounded-full border border-border px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                <span className={cn("h-1.5 w-1.5 rounded-full", dirty ? "bg-muted-foreground" : "bg-foreground")} />
                {dirty ? "Draft changed" : "Ready to publish"}
              </div>
              <h2 className="flex flex-wrap items-center gap-2 text-xl font-medium tracking-[-0.03em] text-foreground sm:text-[30px]">
                {draft.name || "Untitled Template"}
                {editing && editing.isSystem && <span className={systemTagClass}>System</span>}
              </h2>
              <p className="max-w-2xl text-sm leading-5 text-muted-foreground">
                Configure the name, subject, and body. Type <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[12px] text-foreground">/</code> or{" "}
                <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[12px] text-foreground">{`{{`}</code> in the editor to insert variables.
              </p>
            </div>
          </div>
        <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" rounded="lg" className="border-border" onClick={onPreview}>
              <IconEye /> Preview
            </Button>
            <Button
              variant="outline"
              rounded="lg"
              onClick={onDelete}
              disabled={!canWrite || isDeleting || Boolean(editing && editing.isSystem)}
              title={editing && editing.isSystem ? "System templates can't be deleted" : "Delete template"}
              className="border-destructive/30 text-destructive hover:bg-destructive-subtle"
            >
              <IconTrash /> {isDeleting ? "Deleting…" : "Delete"}
            </Button>
          </div>
        </div>


        <div className={cn("border-b border-border px-5 py-4")}>
          <div className="space-y-1">
            <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
              Template editor
            </div>
            <h2 className="flex items-center gap-2 text-base font-semibold tracking-[-0.02em] text-foreground">
              <IconPencil className="h-3.5 w-3.5 text-muted-foreground" />
              Edit Template
            </h2>
            <p className="text-sm leading-5 text-muted-foreground">
              Pick an entity type, then a form, then insert variables from that form. Type{" "}
              <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[12px] text-foreground">/</code>{" "}
              in the editor to insert variables.
            </p>
          </div>
        </div>

        {!canWrite && (
          <div className="mx-5 mt-4 flex items-center gap-2 rounded-lg border border-warning/30 bg-warning-subtle p-3 text-sm text-warning">
            <Lock className="h-4 w-4 shrink-0" />
            You have read-only access to Email Templates. Contact an admin to make changes.
          </div>
        )}

        {(saveError || deleteError) && (
          <div className="mx-5 mt-3 rounded-xl border border-destructive/30 bg-destructive-subtle px-3 py-2 text-sm text-destructive">
            {saveError ?? deleteError}
          </div>
        )}

        <div className="grid gap-4 px-5 py-4 xl:grid-cols-[minmax(0,1.65fr)_280px]">
          <div className="space-y-0">
            <div className="pb-4">
              <div className="mb-3">
                <div className="text-sm font-semibold tracking-[-0.01em] text-foreground">Template setup</div>
                <div className="mt-1 text-sm text-muted-foreground">
                  Connect this message to the right entity and form context before editing content.
                </div>
              </div>
              <div className="grid gap-3 md:grid-cols-3">
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-foreground">Template Name</label>
                  <Input
                    className="h-10 rounded-lg border-border bg-card"
                    type="text"
                    value={draft.name}
                    disabled={!canWrite}
                    onChange={(e) => onUpdate({ name: e.target.value })}
                  />
                  {validationErrors.name && <div className="text-xs text-destructive">{validationErrors.name}</div>}
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="flex items-center gap-2 text-sm font-medium text-foreground">
                    Entity type{" "}
                    <span className="text-xs font-normal text-muted-foreground">— controls available variables</span>
                  </label>
                  <DropdownMenu>
                    <DropdownMenuTrigger className={selectTriggerClass} disabled={!canWrite}>
                      <span>{currentEntity?.label ?? "— none —"}</span>
                      <IconChevron className="h-3.5 w-3.5" />
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start">
                      {entityTypes.map((et) => (
                        <DropdownMenuItem
                          key={et.value ?? "none"}
                          className={cn(et.value === draft.entityType && "bg-info-subtle text-info")}
                          onClick={() => onEntityTypeChange(et.value)}
                        >
                          {et.label}
                        </DropdownMenuItem>
                      ))}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="flex items-center gap-2 text-sm font-medium text-foreground">
                    Form
                    <span className="text-xs font-normal text-muted-foreground">— fields come from this form only</span>
                  </label>
                  <DropdownMenu>
                    <DropdownMenuTrigger
                      className={cn(selectTriggerClass, !draft.entityType && "cursor-not-allowed opacity-60")}
                      disabled={!canWrite || !draft.entityType}
                    >
                      <span>
                        {!draft.entityType
                          ? "Select an entity type first"
                          : currentForm?.label ?? "Select a form"}
                      </span>
                      <IconChevron className="h-3.5 w-3.5" />
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start">
                      {formOptions.length > 0 ? (
                        formOptions.map((form) => (
                          <DropdownMenuItem
                            key={form.value}
                            className={cn(form.value === draft.formId && "bg-info-subtle text-info")}
                            onClick={() => onFormChange(form.value)}
                          >
                            {form.label}
                            <span className="ml-2 text-xs text-muted-foreground">
                              {form.fieldCount} fields
                            </span>
                          </DropdownMenuItem>
                        ))
                      ) : (
                        <DropdownMenuItem disabled>
                          {draft.entityType ? "No forms found" : "Select an entity type first"}
                        </DropdownMenuItem>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </div>
            </div>

            <div className="border-t border-border py-4">
              <div className="mb-3">
                <div className="text-sm font-semibold tracking-[-0.01em] text-foreground">Subject line</div>
                <div className="mt-1 text-sm text-muted-foreground">
                  Keep it short, specific, and ready for variables.
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <SubjectInput
                  className="h-10 rounded-lg border-border bg-card"
                  value={draft.subject}
                  onChange={(v) => onUpdate({ subject: v })}
                  variables={availableVariables}
                  placeholder="e.g. Action Required: {{form_title}}"
                  disabled={!canWrite}
                />
                {validationErrors.subject && <div className="text-xs text-destructive">{validationErrors.subject}</div>}
                <div className="text-xs text-muted-foreground">
                  Type <code className="font-mono">{"{{"}</code> to insert variables.
                </div>
              </div>
            </div>

            <div className="border-t border-border pt-4">
              <div className="mb-3">
                <div className="text-sm font-semibold tracking-[-0.01em] text-foreground">Email body</div>
                <div className="mt-1 text-sm text-muted-foreground">
                  Compose visually or switch to source mode when you need precise control.
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <RichEditor
                  value={draft.bodyHtml}
                  onChange={(v) => onUpdate({ bodyHtml: v })}
                  variables={availableVariables}
                  key={`${draft.templateId}:${draft.formId ?? "no-form"}`}
                  disabled={!canWrite}
                />
                {validationErrors.bodyHtml && <div className="text-xs text-destructive">{validationErrors.bodyHtml}</div>}
              </div>
            </div>
          </div>

          <div className="space-y-0 border-l border-border pl-4 xl:sticky xl:top-5 xl:self-start">
            <div className="pb-4">
              <div className="mb-3">
                <div className="text-sm font-semibold tracking-[-0.01em] text-foreground">Variable library</div>
                <div className="mt-1 text-sm text-muted-foreground">
                  Copy variables from the current form context and drop them into the subject or body.
                </div>
              </div>
              <div className="mb-3 flex items-center gap-2 text-xs text-muted-foreground">
                <IconSparkle className="h-3.5 w-3.5 text-muted-foreground" />
                <span>
                  Available variables for{" "}
                  <strong className="capitalize text-foreground">
                    {currentForm?.label ?? draft.entityType ?? "any context"}
                  </strong> · click to copy
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                {availableVariables.length === 0 && (
                  <span className="text-xs text-muted-foreground">
                    {draft.formId ? "No fields found for this form." : "Select a form to load its fields."}
                  </span>
                )}
                {availableVariables.map((v) => (
                  <button
                    key={v.key}
                    className="inline-flex items-center gap-1 rounded-full border border-border bg-card px-2.5 py-1 text-xs font-medium text-foreground transition hover:border-border hover:bg-muted/50"
                    onClick={() => {
                      if (!canWrite) return;
                      navigator.clipboard?.writeText(`{{${v.key}}}`);
                    }}
                    disabled={!canWrite}
                    title={`Click to copy {{${v.key}}}`}
                  >
                    {`{{${v.key}}}`}
                    {v.label && <span className="font-sans text-[11px] text-muted-foreground">· {v.label}</span>}
                  </button>
                ))}
              </div>
            </div>

            <div className="border-t border-border pt-4">
              <div className="text-sm font-semibold tracking-[-0.01em] text-foreground">Editing tips</div>
              <div className="mt-2.5 space-y-2.5 text-sm leading-5 text-muted-foreground">
                <div>Use preview before saving to catch subject issues and spacing problems early.</div>
                <div>Switch to source mode only when you need direct HTML control for advanced formatting.</div>
                <div>Variables stay highlighted in preview so it is easy to see what will be substituted later.</div>
              </div>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-3 border-t border-border bg-muted/50 px-5 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            {dirty ? (
              <>
                <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground" />
                Unsaved changes
              </>
            ) : (
              <>
                <span className="h-1.5 w-1.5 rounded-full bg-foreground" />
                All changes saved
              </>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" rounded="lg" className="border-border" onClick={onCancel} disabled={!dirty}>
              <IconX /> Cancel
            </Button>
            <Button
              variant="primary"
              rounded="lg"
              onClick={onSave}
              disabled={!canWrite || isSaving}
            >
              <IconSave /> {isSaving ? "Saving…" : "Save Changes"}
            </Button>
          </div>
        </div>

    </>
  );
}
