/**
 * MethodList
 *
 * The Methods tab's left sidebar. Mirrors the Forms tab's FormSchemaList,
 * grouped by method category instead of entity type (the method library's own
 * grouping), with inline rename and an actions menu.
 */

import {
  Archive,
  ArchiveRestore,
  Check,
  FileText,
  Loader2,
  MoreHorizontal,
  Pencil,
  Plus,
  Trash2,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { MethodIdentity } from '@/core/types';
import type { EditingMethodName } from '../hooks/useMethods';

const UNCATEGORISED = 'Uncategorised';

interface MethodListProps {
  methods: MethodIdentity[];
  selectedMethodId: string | null;
  editingMethodName: EditingMethodName | null;
  savingMethodName: boolean;
  canWrite: boolean;
  onSelectMethod: (method: MethodIdentity) => void;
  onNewMethod: () => void;
  onDeleteMethod: (method: MethodIdentity) => void;
  onArchiveMethod: (method: MethodIdentity) => void;
  onUnarchiveMethod: (method: MethodIdentity) => void;
  archivingMethodId: string | null;
  onStartRename: (method: MethodIdentity) => void;
  onChangeRenameName: (name: string) => void;
  onConfirmRename: () => void;
  onCancelRename: () => void;
  onCloneMethod: (method: MethodIdentity) => void;
  entityLabel?: string;
  entityLabelPlural?: string;
  codePrefix?: string;
}

/** Groups by category name, uncategorised last. The API already returns the
 *  newest methods first; preserve that order inside each category instead of
 *  sorting alphabetically, which made older methods appear first in the UI. */
function groupByCategory(methods: MethodIdentity[]): [string, MethodIdentity[]][] {
  const groups = new Map<string, MethodIdentity[]>();
  for (const method of methods) {
    const key = method.category_name?.trim() || UNCATEGORISED;
    const bucket = groups.get(key);
    if (bucket) bucket.push(method);
    else groups.set(key, [method]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => {
      if (a === UNCATEGORISED) return 1;
      if (b === UNCATEGORISED) return -1;
      return a.localeCompare(b);
    })
    .map(([key, items]) => [
      key,
      items.sort((a, b) => {
        // method_code is a monotonic per-organization creation sequence and is
        // the most reliable client-side tie-breaker for newest-first display.
        const byCode = b.method_code - a.method_code;
        if (byCode !== 0) return byCode;
        return (b.created_at ?? '').localeCompare(a.created_at ?? '');
      }),
    ]);
}

export default function MethodList({
  methods,
  selectedMethodId,
  editingMethodName,
  savingMethodName,
  canWrite,
  onSelectMethod,
  onNewMethod,
  onDeleteMethod,
  onArchiveMethod,
  onUnarchiveMethod,
  archivingMethodId,
  onStartRename,
  onChangeRenameName,
  onConfirmRename,
  onCancelRename,
  onCloneMethod,
  entityLabel = 'Form',
  entityLabelPlural = 'Forms',
  codePrefix = 'FR',
}: MethodListProps) {
  const groups = groupByCategory(methods);

  return (
    <div className="bg-card rounded-xl border border-border overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-border">
        <span className="flex items-center gap-2 text-sm font-medium text-foreground">
          <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
          {entityLabelPlural}
        </span>
        <Button
          variant="ghost"
          size="icon"
          onClick={onNewMethod}
          className="h-7 w-7 text-muted-foreground hover:text-foreground"
          title={`New ${entityLabel}`}
          disabled={!canWrite}
        >
          <Plus className="w-3.5 h-3.5" />
        </Button>
      </div>

      {/* List */}
      <div className="max-h-[65vh] min-h-[160px] overflow-y-auto py-1">
        {groups.length === 0 ? (
          <p className="px-3 py-2 text-sm text-muted-foreground">No {entityLabelPlural.toLowerCase()} configured</p>
        ) : (
          groups.map(([categoryName, group]) => (
            <div key={categoryName}>
              <div className="px-3 pt-2 pb-1 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                {categoryName}
              </div>

              {group.map((method) => {
                const isSelected = selectedMethodId === method.method_id;
                const isEditing = editingMethodName?.methodId === method.method_id;

                return (
                  <div
                    key={method.method_id}
                    className={`group relative flex items-center gap-1 mx-1 mb-0.5 rounded-lg ${
                      isSelected ? 'bg-primary/10' : 'hover:bg-muted/50'
                    }`}
                  >
                    {isEditing ? (
                      <div className="flex flex-1 items-center gap-1 px-2 py-1.5">
                        <input
                          autoFocus
                          type="text"
                          value={editingMethodName.name}
                          onChange={(e) => onChangeRenameName(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') onConfirmRename();
                            if (e.key === 'Escape') onCancelRename();
                          }}
                          className="flex-1 min-w-0 rounded border border-primary/40 bg-card px-2 py-0.5 text-sm text-foreground outline-none focus:border-primary"
                        />
                        <button
                          type="button"
                          onClick={onConfirmRename}
                          disabled={savingMethodName}
                          className="text-primary hover:text-primary/80 disabled:opacity-50"
                          title="Save"
                        >
                          {savingMethodName ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Check className="w-3.5 h-3.5" />
                          )}
                        </button>
                        <button
                          type="button"
                          onClick={onCancelRename}
                          disabled={savingMethodName}
                          className="text-muted-foreground hover:text-foreground disabled:opacity-50"
                          title="Cancel"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => onSelectMethod(method)}
                          className="flex-1 min-w-0 text-left px-3 py-2"
                        >
                          <div
                            className={`truncate text-sm font-medium leading-tight ${
                              isSelected ? 'text-primary' : 'text-foreground'
                            }`}
                          >
                            {method.name}
                            {method.is_archived && (
                              <span className="ml-1.5 text-xs font-normal text-muted-foreground">
                                archived
                              </span>
                            )}
                          </div>
                          <div
                            className={`text-xs mt-0.5 ${
                              isSelected ? 'text-primary/60' : 'text-muted-foreground'
                            }`}
                          >
                            {codePrefix}-{String(method.method_code).padStart(2, '0')}
                          </div>
                        </button>

                        {canWrite && (
                          <DropdownMenu>
                            <DropdownMenuTrigger
                              render={
                                <button
                                  type="button"
                                  className={`mr-1 shrink-0 rounded p-1 transition-opacity ${
                                    isSelected
                                      ? 'opacity-60 hover:opacity-100'
                                      : 'opacity-0 group-hover:opacity-60 hover:!opacity-100'
                                  } text-muted-foreground hover:bg-muted`}
                                  title="Actions"
                                />
                              }
                            >
                              <MoreHorizontal className="w-3.5 h-3.5" />
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-40">
                              <DropdownMenuItem
                                onClick={() => onStartRename(method)}
                                disabled={method.is_archived}
                              >
                                <Pencil className="w-3.5 h-3.5 mr-2" />
                                Rename
                              </DropdownMenuItem>
                              <DropdownMenuItem onClick={() => onCloneMethod(method)}>
                                <Plus className="w-3.5 h-3.5 mr-2" />
                                Clone
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                              {method.is_archived ? (
                                <DropdownMenuItem
                                  onClick={() => onUnarchiveMethod(method)}
                                  disabled={archivingMethodId === method.method_id}
                                >
                                  <ArchiveRestore className="w-3.5 h-3.5 mr-2" />
                                  Unarchive
                                </DropdownMenuItem>
                              ) : (
                                <DropdownMenuItem
                                  onClick={() => onArchiveMethod(method)}
                                  disabled={archivingMethodId === method.method_id}
                                >
                                  <Archive className="w-3.5 h-3.5 mr-2" />
                                  Archive
                                </DropdownMenuItem>
                              )}
                              <DropdownMenuItem
                                onClick={() => onDeleteMethod(method)}
                                className="text-destructive focus:text-destructive"
                              >
                                <Trash2 className="w-3.5 h-3.5 mr-2" />
                                Delete permanently
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        )}
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
