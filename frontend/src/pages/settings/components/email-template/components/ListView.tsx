import {
  IconPlus, IconPencil, IconTrash, IconSearch, IconDots,
} from "./Icons.tsx";
import type { ColumnDef } from "@tanstack/react-table";
import { Lock } from "lucide-react";
import { DataTable, DateCell, actionsColumn } from "@/core/components/DataTable";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { formatCreatedAt } from "../services/templateService.ts";
import type { Template } from "../types";
import { Button } from "@/components/ui/button.tsx";
import { Input } from "@/components/ui/input.tsx";
import { insetPanelClass, panelClass } from "../styles";

const entityChipClass =
  "rounded-full border border-border bg-muted/50 px-2.5 py-1 text-[10px] font-medium capitalize text-foreground";
const ghostEntityChipClass =
  "rounded-full border border-dashed border-border bg-card px-2.5 py-1 text-[10px] font-medium text-muted-foreground";
const iconButtonClass =
  "inline-flex h-8 w-8 items-center justify-center rounded-md border border-transparent text-muted-foreground transition hover:border-border hover:bg-muted/50 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40";

interface ListViewProps {
  templates: Template[];
  filtered: Template[];
  query: string;
  onQuery: (q: string) => void;
  onOpen: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
  loading?: boolean;
  canWrite?: boolean;
}

export function ListView({
  templates, filtered, query, onQuery, onOpen, onCreate, onDelete, loading, canWrite = true,
}: ListViewProps) {
  const isEmpty = templates.length === 0;
  const hasNoMatches = !isEmpty && filtered.length === 0;

  return (
    <>
        <div className="flex flex-col gap-3 px-5 py-4 lg:flex-row lg:items-end lg:justify-between lg:px-6">
          <div className="max-w-2xl space-y-1.5">
            <div className="mb-1 text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
              Settings / Messaging
            </div>
            <div className="space-y-1">
              <h1 className="text-2xl font-semibold tracking-[-0.03em] text-foreground sm:text-[30px]">
                Email Templates
              </h1>
              <p className="text-sm leading-5 text-muted-foreground">
                Reusable outbound emails for workflow actions, with form-aware variables and quick previews.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3 sm:gap-4">
            <div className="text-right">
              <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                Library size
              </div>
              <div className="mt-0.5 text-lg font-semibold tracking-tight text-foreground">
                {templates.length} template{templates.length === 1 ? "" : "s"}
              </div>
            </div>
            {!isEmpty && (
              <Button
                variant="primary"
                size="md"
                rounded="lg"
                onClick={onCreate}
                disabled={!canWrite}
              >
                <IconPlus /> New Template
              </Button>
            )}
          </div>
        </div>

      {!canWrite && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-warning/30 bg-warning-subtle p-3 text-sm text-warning">
          <Lock className="h-4 w-4 shrink-0" />
          You have read-only access to Email Templates. Contact an admin to make changes.
        </div>
      )}


      {loading ? (
        <div className="py-14 text-center text-sm text-muted-foreground">Loading templates…</div>
      ) : isEmpty ? (
        <EmptyState onCreate={onCreate} canWrite={canWrite} />
      ) : (
        <>
          <div className="mb-3 flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <div className="relative w-full max-w-xl">
              <IconSearch className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                type="text"
                className="h-10 rounded-lg border-border bg-card pl-9 pr-3"
                placeholder="Search by name or subject…"
                value={query}
                onChange={(e) => onQuery(e.target.value)}
              />
            </div>
            <div className="flex items-center gap-2.5 text-xs text-muted-foreground sm:text-sm">
              <span>{filtered.length} shown</span>
              <span className="text-muted-foreground/60">/</span>
              <span>
                {templates.length} total template{templates.length === 1 ? "" : "s"}
              </span>
            </div>
          </div>

          {hasNoMatches ? (
            <div className={cn(insetPanelClass, "px-6 py-10 text-center")}>
              <div className="mx-auto mb-3 inline-flex h-10 w-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
                <IconSearch />
              </div>
              <div className="mb-1 text-base font-semibold text-foreground">No templates match "{query}"</div>
              <div className="text-sm text-muted-foreground">Try a different search term, or create a new template.</div>
              <Button variant="outline" rounded="lg" className="mt-4" onClick={() => onQuery("")}>
                Clear search
              </Button>
            </div>
          ) : (
            <div className={cn(panelClass, "overflow-hidden")}>
              <TemplatesTable
                templates={filtered}
                onOpen={onOpen}
                onDelete={onDelete}
                canWrite={canWrite}
              />
            </div>
          )}
        </>
      )}
    </>
  );
}

function EmptyState({ onCreate, canWrite = true }: { onCreate: () => void; canWrite?: boolean }) {
  return (
    <div className={cn(insetPanelClass, "mx-auto max-w-3xl px-6 py-10 text-center")}>
      <div className="mx-auto mb-4 h-[90px] w-[110px]">
        <svg width="120" height="100" viewBox="0 0 120 100" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect x="18" y="22" width="84" height="60" rx="6" fill="#fff" stroke="#e2e8f0" strokeWidth="1.5" />
          <rect x="18" y="22" width="84" height="16" rx="6" fill="#dbeafe" stroke="#e2e8f0" strokeWidth="1.5" />
          <rect x="26" y="46" width="50" height="4" rx="2" fill="#e6e8ee" />
          <rect x="26" y="54" width="68" height="3" rx="1.5" fill="#eef0f4" />
          <rect x="26" y="60" width="58" height="3" rx="1.5" fill="#eef0f4" />
          <rect x="26" y="66" width="40" height="3" rx="1.5" fill="#eef0f4" />
          <rect x="26" y="72" width="22" height="6" rx="3" fill="#2563eb" />
          <circle cx="92" cy="30" r="3" fill="#2563eb" />
          <path d="M84 30 L78 30 M70 30 L72 30" stroke="#2563eb" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </div>
      <h2 className="mb-2 text-xl font-semibold tracking-tight text-foreground">No email templates yet</h2>
      <p className="mx-auto mb-5 max-w-xl text-sm leading-5 text-muted-foreground">
        Templates let you reuse polished, on-brand emails across workflows. Add
        variables like <code className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-[12px] text-info">{`{{form_link}}`}</code> to personalize each send.
      </p>
      <Button variant="primary" size="md" rounded="lg" onClick={onCreate} disabled={!canWrite}>
        <IconPlus /> Add new template
      </Button>
      <div className="mx-auto mt-5 grid max-w-2xl gap-2 border-t border-border pt-4 text-left md:grid-cols-3">
        <div className="flex items-center gap-3 py-1 text-sm text-muted-foreground"><span className="inline-flex h-[20px] w-[20px] items-center justify-center rounded-full bg-muted text-[11px] font-semibold text-foreground">1</span> Name your template and pick an entity type</div>
        <div className="flex items-center gap-3 py-1 text-sm text-muted-foreground"><span className="inline-flex h-[20px] w-[20px] items-center justify-center rounded-full bg-muted text-[11px] font-semibold text-foreground">2</span> Compose with the visual editor, or switch to HTML</div>
        <div className="flex items-center gap-3 py-1 text-sm text-muted-foreground"><span className="inline-flex h-[20px] w-[20px] items-center justify-center rounded-full bg-muted text-[11px] font-semibold text-foreground">3</span> Drop in variables with <kbd className="rounded border border-border bg-card px-1.5 py-0.5 font-mono text-[11px] text-foreground">/</kbd> or <kbd className="rounded border border-border bg-card px-1.5 py-0.5 font-mono text-[11px] text-foreground">{`{{`}</kbd></div>
      </div>
    </div>
  );
}

type TemplatesTableProps = {
  templates: Template[];
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  canWrite?: boolean;
};

function TemplatesTable({ templates, onOpen, onDelete, canWrite = true }: TemplatesTableProps) {
  const columns: ColumnDef<Template, unknown>[] = [
    {
      id: "template",
      header: "Template",
      accessorFn: (template) => template.name,
      cell: ({ row }) => (
        <span className="truncate text-sm font-medium text-foreground">{row.original.name}</span>
      ),
      meta: { width: "16rem" },
    },
    {
      id: "subject",
      header: "Description",
      accessorFn: (template) => template.subject ?? "",
      cell: ({ row }) =>
        row.original.subject ? (
          <span className="block truncate text-sm text-muted-foreground">
            {row.original.subject}
          </span>
        ) : (
          <span className="text-sm text-muted-foreground/50">—</span>
        ),
    },
    {
      id: "type",
      header: "Type",
      accessorFn: (template) => (template.isSystem ? "System" : "Custom"),
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground">
          {row.original.isSystem ? "System" : "Custom"}
        </span>
      ),
      meta: { width: "8rem" },
    },
    {
      id: "scope",
      header: "Scope",
      accessorFn: (template) => template.entityType ?? "",
      cell: ({ row }) =>
        row.original.entityType ? (
          <span className={entityChipClass}>{row.original.entityType}</span>
        ) : (
          <span className={ghostEntityChipClass}>No entity</span>
        ),
      meta: { width: "12rem" },
    },
    {
      id: "created",
      header: "Created",
      accessorFn: (template) => template.createdAt,
      cell: ({ row }) => (
        <DateCell>
          <span className="whitespace-nowrap">{formatCreatedAt(row.original.createdAt)}</span>
        </DateCell>
      ),
      meta: { width: "10rem" },
    },
    actionsColumn<Template>({
      width: "11rem",
      alwaysVisible: true,
      render: (template) => (
        <>
          <Button
            variant="outline"
            size="md"
            rounded="lg"
            className="border-border"
            onClick={() => onOpen(template.templateId)}
            disabled={!canWrite}
          >
            <IconPencil className="size-3.5" /> Edit
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger
              className={iconButtonClass}
              aria-label="More options"
              disabled={!canWrite}
            >
              <IconDots />
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="end"
              className="min-w-36 rounded-xl border border-border bg-card p-1 shadow-lg shadow-slate-900/10"
            >
              <DropdownMenuItem onClick={() => onOpen(template.templateId)} disabled={!canWrite}>
                <IconPencil className="size-3.5" />
                Edit
              </DropdownMenuItem>
              <DropdownMenuItem
                variant="destructive"
                disabled={!canWrite || template.isSystem}
                onClick={() => onDelete(template.templateId)}
              >
                <IconTrash className="size-3.5" />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </>
      ),
    }),
  ];

  return (
    <DataTable
      label="Email templates"
      data={templates}
      columns={columns}
      getRowId={(template) => template.templateId}
      onRowClick={(template) => onOpen(template.templateId)}
      // The surrounding panel already draws the frame.
      framed={false}
      emptyState={{ title: "No templates" }}
    />
  );
}
