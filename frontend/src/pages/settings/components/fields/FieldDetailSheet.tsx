/**
 * FieldDetailSheet
 *
 * Replaces the old inline chevron-accordion (editor + version history both
 * expanding in place, one row at a time) with a big centered dialog: the
 * list row stays a single compact line, and everything about one field (its
 * editor, its version history) lives in here instead, split across
 * Configuration / History tabs. Scales the same whether a field has one
 * version or fifty, since history is a scroll inside a fixed-size panel,
 * not more accordion height pushing the list around.
 */

import { Loader2, Search } from 'lucide-react';
import Badge from '@/core/components/Badge';
import Modal from '@/core/components/Modal';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import type { FieldType, FieldVersion, FieldWithVersion, FormField, Picklist } from '@/core/types';
import { FIELD_TYPE_LABELS } from '../form-config/constants';
import LibraryFieldEditor from './LibraryFieldEditor';
import {
  formatFieldCode,
  matchesHistorySearch,
  settingsToRows,
  versionsNewestFirst,
} from './fieldLibraryUtils';

interface FieldDetailSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  target: FieldWithVersion | null;
  tab: 'config' | 'history';
  onTabChange: (tab: 'config' | 'history') => void;

  field: FormField;
  description: string;
  onChangeDescription: (value: string) => void;
  onChangeField: (field: FormField) => void;
  allFields: FormField[];
  picklists: Picklist[];
  isNew: boolean;
  saving: boolean;
  editError: string | null;
  canWrite: boolean;
  onSave: () => void;
  onCancel: () => void;

  historyItems: FieldVersion[] | null;
  historyLoading: boolean;
  historySearch: string;
  onHistorySearchChange: (value: string) => void;
  displayUser: (id: string | null | undefined) => string | null;
  entityLabel?: string;
  codePrefix?: string;
  fieldTypeOptions?: readonly { value: string; label: string }[];
}

export default function FieldDetailSheet({
  open,
  onOpenChange,
  target,
  tab,
  onTabChange,
  field,
  description,
  onChangeDescription,
  onChangeField,
  allFields,
  picklists,
  isNew,
  saving,
  editError,
  canWrite,
  onSave,
  onCancel,
  historyItems,
  historyLoading,
  historySearch,
  onHistorySearchChange,
  displayUser,
  entityLabel = 'Field',
  codePrefix = 'F',
  fieldTypeOptions,
}: FieldDetailSheetProps) {
  const identity = target?.identity ?? null;
  const version = target?.version ?? null;
  const canConfigure = canWrite && !identity?.is_archived;

  return (
    <Modal open={open} onClose={() => { onCancel(); onOpenChange(false); }} title={isNew ? `New ${entityLabel.toLowerCase()}` : identity?.name ?? ''} size="xl">
      {identity && (
        <div className="mb-4 flex flex-wrap items-center gap-1.5">
          <Badge variant="cobalt">{FIELD_TYPE_LABELS[identity.field_type as FieldType] ?? identity.field_type}</Badge>
          <Badge variant="default">{formatFieldCode(identity.field_count_id, codePrefix)}</Badge>
          {identity.is_archived && <Badge variant="default">Archived</Badge>}
        </div>
      )}

      {isNew ? (
        <>
          {editError && (
            <div className="mb-3 rounded-lg border border-destructive/30 bg-destructive-subtle p-3 text-sm text-destructive">
              {editError}
            </div>
          )}
          <LibraryFieldEditor
            field={field}
            description={description}
            onChangeDescription={onChangeDescription}
            allFields={allFields}
            picklists={picklists}
            isNew
            savingField={saving}
            canWrite={canWrite}
            onChangeField={onChangeField}
            onSave={onSave}
            onCancel={onCancel}
            entityLabel={entityLabel}
            fieldTypeOptions={fieldTypeOptions}
          />
        </>
      ) : (
        <Tabs value={tab} onValueChange={(v) => onTabChange(v as 'config' | 'history')}>
          <TabsList className="grid w-full max-w-md grid-cols-2">
            <TabsTrigger value="config" disabled={!canConfigure}>Configuration</TabsTrigger>
            <TabsTrigger value="history">History{version ? ` (v${version.version})` : ''}</TabsTrigger>
          </TabsList>

          <TabsContent value="config">
            {editError && (
              <div className="mb-3 rounded-lg border border-destructive/30 bg-destructive-subtle p-3 text-sm text-destructive">
                {editError}
              </div>
            )}
            <div className="mb-3 rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
              <span className="font-medium text-foreground">Versioning:</span>{' '}
              Changing the type or any configuration option creates a new version. Name and
              description edits do not.
            </div>
            <LibraryFieldEditor
              field={field}
              description={description}
              onChangeDescription={onChangeDescription}
              allFields={allFields}
              picklists={picklists}
              isNew={false}
              savingField={saving}
              canWrite={canConfigure}
              onChangeField={onChangeField}
              onSave={onSave}
              onCancel={onCancel}
              entityLabel={entityLabel}
              fieldTypeOptions={fieldTypeOptions}
            />
          </TabsContent>

          <TabsContent value="history">
            {identity && (historyItems?.length ?? 0) > 1 && (
              <div className="relative mb-3 max-w-sm">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <input
                  type="search"
                  value={historySearch}
                  onChange={(e) => onHistorySearchChange(e.target.value)}
                  placeholder="Search versions…"
                  className="h-8 w-full rounded-lg border border-border bg-card pl-8 pr-2 text-xs focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20"
                />
              </div>
            )}

            {historyLoading ? (
              <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading versions…
              </div>
            ) : identity && (historyItems ?? []).filter((v) => matchesHistorySearch(identity, v, historySearch, codePrefix)).length === 0 ? (
              <p className="py-6 text-sm text-muted-foreground">
                {historySearch ? `No versions match "${historySearch}".` : 'No version history yet.'}
              </p>
            ) : (
              identity && (
                <div className="relative">
                  <div className="absolute bottom-5 left-[7px] top-5 w-px bg-gradient-to-b from-primary/60 via-border to-border" />
                  <ol className="space-y-3">
                  {versionsNewestFirst(historyItems ?? [])
                    .filter((v) => matchesHistorySearch(identity, v, historySearch, codePrefix))
                    .map((v) => {
                      const rows = settingsToRows((v.settings ?? {}) as Record<string, unknown>);
                      const creatorName = v.created_by_name ?? displayUser(v.created_by);
                      const detailRows = [
                        { label: `${entityLabel} Name`, value: v.name || identity.name },
                        {
                          label: `${entityLabel} Type`,
                          value: FIELD_TYPE_LABELS[v.field_type as FieldType] ?? v.field_type,
                        },
                        {
                          label: 'Required',
                          value: v.settings?.required === true ? 'Required' : 'Optional',
                        },
                        { label: 'Description', value: v.description || '—' },
                        { label: 'Created by / Updated by', value: creatorName || '—' },
                        ...rows,
                      ];

                      return (
                        <li key={v.version_id} className="relative pl-6">
                          <span className={`absolute left-0 top-4 h-3.5 w-3.5 rounded-full border-2 border-card ${v.is_latest ? 'bg-primary ring-4 ring-primary/10' : 'bg-muted-foreground/50'}`} />
                          <div className={`rounded-lg border p-3 transition-colors ${v.is_latest ? 'border-primary/30 bg-primary/[0.03] shadow-sm' : 'border-border bg-card hover:border-primary/20'}`}>
                            <div className="mb-3 flex items-center justify-between gap-3 border-b border-border/70 pb-2">
                              <div>
                                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Version</div>
                                <div className="font-mono text-sm font-semibold text-foreground">v{v.version}</div>
                              </div>
                              <div className="text-right">
                                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Status</div>
                                <div className={`text-xs font-semibold ${v.is_latest ? 'text-primary' : 'text-muted-foreground'}`}>
                                  {v.is_latest ? 'Current' : 'Previous version'}
                                </div>
                              </div>
                            </div>
                            <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
                            {detailRows.map((row) => (
                              <div key={row.label} className="grid grid-cols-[minmax(120px,auto)_minmax(0,1fr)] gap-3 border-b border-border/60 pb-2 last:border-0">
                                <dt className="text-xs font-medium text-muted-foreground">{row.label}</dt>
                                <dd className="min-w-0 break-words text-xs text-foreground">{row.value}</dd>
                              </div>
                            ))}
                            </dl>
                          </div>
                        </li>
                      );
                    })}
                  </ol>
                </div>
              )
            )}
          </TabsContent>
        </Tabs>
      )}
    </Modal>
  );
}
