import {
  FileText,
  Plus,
  Pencil,
  Trash2,
  Loader2,
  Check,
  X,
  ChevronUp,
  ChevronDown,
  MoreHorizontal,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { FormSchema } from '../../../../../core/types';
import type { SchemaGroup } from '../useFormOrdering';
import { ENTITY_TYPE_LABELS } from '../constants';

interface FormSchemaListProps {
  schemaGroups: SchemaGroup[];
  selectedSchema: FormSchema | null;
  editingSchemaName: { schemaId: string; name: string } | null;
  savingSchemaName: boolean;
  deletingSchema: string | null;
  reorderingEntityType: string | null;
  canWrite: boolean;
  onSelectSchema: (schema: FormSchema) => void;
  onNewForm: () => void;
  onDeleteSchema: (schema: FormSchema) => void;
  onStartRename: (schema: FormSchema) => void;
  onChangeRenameName: (name: string) => void;
  onConfirmRename: () => void;
  onCancelRename: () => void;
  onMoveSchema: (schema: FormSchema, direction: -1 | 1) => void;
}

export default function FormSchemaList({
  schemaGroups,
  selectedSchema,
  editingSchemaName,
  savingSchemaName,
  deletingSchema,
  reorderingEntityType,
  canWrite,
  onSelectSchema,
  onNewForm,
  onDeleteSchema,
  onStartRename,
  onChangeRenameName,
  onConfirmRename,
  onCancelRename,
  onMoveSchema,
}: FormSchemaListProps) {
  return (
    <div className="bg-card rounded-xl border border-border overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-border">
        <span className="flex items-center gap-2 text-sm font-medium text-foreground">
          <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
          Entity Forms
        </span>
        <Button
          variant="ghost"
          size="icon"
          onClick={onNewForm}
          className="h-7 w-7 text-muted-foreground hover:text-foreground"
          title="New Form"
          disabled={!canWrite}
        >
          <Plus className="w-3.5 h-3.5" />
        </Button>
      </div>

      {/* List */}
      <div className="py-1">
        {schemaGroups.length === 0 ? (
          <p className="px-3 py-2 text-sm text-muted-foreground">No forms configured</p>
        ) : (
          schemaGroups.map(([entityKey, group]) => (
            <div key={entityKey}>
              {/* Group label */}
              <div className="flex items-center gap-1.5 px-3 pt-2 pb-1 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                {ENTITY_TYPE_LABELS[entityKey] || entityKey}
                {reorderingEntityType === entityKey && (
                  <Loader2 className="w-3 h-3 animate-spin" />
                )}
              </div>

              {group.map((schema, i) => {
                const isSelected = selectedSchema?.id === schema.id;
                const isEditing = editingSchemaName?.schemaId === schema.id;
                const isDeleting = deletingSchema === schema.id;

                return (
                  <div
                    key={schema.id}
                    className={`group relative flex items-center gap-1 mx-1 mb-0.5 rounded-lg ${
                      isSelected ? 'bg-primary/10' : 'hover:bg-muted/50'
                    }`}
                  >
                    {isEditing ? (
                      /* Rename mode */
                      <div className="flex flex-1 items-center gap-1 px-2 py-1.5">
                        <input
                          autoFocus
                          type="text"
                          value={editingSchemaName.name}
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
                          disabled={savingSchemaName}
                          className="text-primary hover:text-primary/80 disabled:opacity-50"
                          title="Save"
                        >
                          {savingSchemaName ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Check className="w-3.5 h-3.5" />
                          )}
                        </button>
                        <button
                          type="button"
                          onClick={onCancelRename}
                          disabled={savingSchemaName}
                          className="text-muted-foreground hover:text-foreground disabled:opacity-50"
                          title="Cancel"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ) : (
                      <>
                        {/* Schema name button — takes all available space */}
                        <button
                          type="button"
                          onClick={() => onSelectSchema(schema)}
                          className="flex-1 min-w-0 text-left px-3 py-2"
                        >
                          <div
                            className={`truncate text-sm font-medium leading-tight ${
                              isSelected ? 'text-primary' : 'text-foreground'
                            }`}
                          >
                            {schema.name}
                          </div>
                          <div
                            className={`text-xs mt-0.5 ${
                              isSelected ? 'text-primary/60' : 'text-muted-foreground'
                            }`}
                          >
                            {schema.schema.fields?.length || 0} fields
                          </div>
                        </button>

                        {/* Actions dropdown — visible on hover or when selected */}
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
                              {isDeleting ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              ) : (
                                <MoreHorizontal className="w-3.5 h-3.5" />
                              )}
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-40">
                              <DropdownMenuItem onClick={() => onStartRename(schema)}>
                                <Pencil className="w-3.5 h-3.5 mr-2" />
                                Rename
                              </DropdownMenuItem>
                              {group.length > 1 && (
                                <>
                                  <DropdownMenuItem
                                    onClick={() => onMoveSchema(schema, -1)}
                                    disabled={i === 0 || reorderingEntityType === entityKey}
                                  >
                                    <ChevronUp className="w-3.5 h-3.5 mr-2" />
                                    Move up
                                  </DropdownMenuItem>
                                  <DropdownMenuItem
                                    onClick={() => onMoveSchema(schema, 1)}
                                    disabled={
                                      i === group.length - 1 ||
                                      reorderingEntityType === entityKey
                                    }
                                  >
                                    <ChevronDown className="w-3.5 h-3.5 mr-2" />
                                    Move down
                                  </DropdownMenuItem>
                                </>
                              )}
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                onClick={() => onDeleteSchema(schema)}
                                className="text-destructive focus:text-destructive"
                              >
                                <Trash2 className="w-3.5 h-3.5 mr-2" />
                                Delete
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
