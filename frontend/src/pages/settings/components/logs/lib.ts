import type { AuditEventResponse } from '@/core/types';

const MASKED_VALUE = '***';

export type FieldChangeRow = {
  id: string;
  entityId: string | null;
  entityType: string | null;
  entityIdentifier: string | null;
  entityArchived: boolean;
  actorName: string | null;
  occurredAt: string | null;
  fieldKey: string | null;
  before: unknown;
  after: unknown;
  isTableField: boolean;
  isMasked: boolean;
  eventLabel: string | null;
};

const EVENT_LABELS: Record<string, string> = {
  ENTITY_CREATED: 'Record created',
  ENTITY_ARCHIVED: 'Record archived',
  ENTITY_ASSIGNEE_CHANGED: 'Assignee changed',
};

type ChangedFieldDiff = { before?: unknown; after?: unknown };

function toDiff(value: unknown): ChangedFieldDiff | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as ChangedFieldDiff;
}

function baseRow(event: AuditEventResponse) {
  return {
    entityId: event.entity_id,
    entityType: event.entity_type,
    entityIdentifier: event.entity_identifier,
    entityArchived: event.entity_archived,
    actorName: event.actor_name,
    occurredAt: event.event_timestamp,
    fieldKey: null,
    before: undefined as unknown,
    after: undefined as unknown,
    isTableField: false,
    isMasked: false,
    eventLabel: null as string | null,
  };
}

/**
 * An edit becomes one row per changed field; every other lifecycle event
 * (created, archived, assignee changed) becomes a single row.
 */
export function toFieldChangeRows(events: AuditEventResponse[]): FieldChangeRow[] {
  const rows: FieldChangeRow[] = [];
  for (const event of events) {
    if (event.event_type === 'ENTITY_ASSIGNEE_CHANGED') {
      rows.push({
        ...baseRow(event),
        id: event.id,
        before: event.metadata?.previous_assignee_id ?? null,
        after: event.metadata?.new_assignee_id ?? null,
        eventLabel: EVENT_LABELS.ENTITY_ASSIGNEE_CHANGED,
      });
      continue;
    }

    const label = EVENT_LABELS[event.event_type];
    if (label) {
      rows.push({ ...baseRow(event), id: event.id, eventLabel: label });
      continue;
    }

    const changedFields = event.metadata?.changed_fields;
    if (!changedFields || typeof changedFields !== 'object') continue;
    for (const [fieldKey, rawDiff] of Object.entries(changedFields)) {
      const diff = toDiff(rawDiff);
      if (!diff) continue;
      rows.push({
        ...baseRow(event),
        id: `${event.id}:${fieldKey}`,
        fieldKey,
        before: diff.before,
        after: diff.after,
        isTableField: Array.isArray(diff.before) || Array.isArray(diff.after),
        isMasked: diff.before === MASKED_VALUE && diff.after === MASKED_VALUE,
      });
    }
  }
  return rows;
}

export type TableCellChange = { rowLabel: string; column: string; before: unknown; after: unknown };

export type TableRowDetail = { cells: Array<{ column: string; value: unknown }> };

export type TableChange = {
  addedRows: TableRowDetail[];
  removedRows: TableRowDetail[];
  cellChanges: TableCellChange[];
};

function isInternalKey(key: string): boolean {
  return key === 'id' || key.startsWith('_');
}

function toRowRecord(row: unknown): Record<string, unknown> {
  return row && typeof row === 'object' && !Array.isArray(row)
    ? (row as Record<string, unknown>)
    : {};
}

function rowDisplayLabel(row: unknown, index: number): string {
  for (const [key, value] of Object.entries(toRowRecord(row))) {
    if (isInternalKey(key)) continue;
    if (value === null || value === undefined || value === '') continue;
    if (typeof value === 'object') continue;
    const text = String(value);
    return text.length > 40 ? `${text.slice(0, 40)}…` : text;
  }
  return `Row ${index + 1}`;
}

/** Every column of a row that was added or removed outright, empties included —
 *  a blank cell is part of what the row looked like. */
function toRowDetail(row: unknown): TableRowDetail {
  return {
    cells: Object.entries(toRowRecord(row))
      .filter(([key]) => !isInternalKey(key))
      .map(([column, value]) => ({ column, value })),
  };
}

/**
 * Diffs a Table/Grid field's before/after arrays down to changed cells. Rows
 * pair by `id` when present, by position otherwise — so a reorder without ids
 * reads as many cell edits.
 */
export function diffTableField(before: unknown, after: unknown): TableChange {
  const beforeRows = Array.isArray(before) ? before : [];
  const afterRows = Array.isArray(after) ? after : [];

  const keyOf = (row: unknown, index: number): string => {
    const id = toRowRecord(row).id;
    return id === undefined || id === null ? `#${index + 1}` : String(id);
  };

  const beforeByKey = new Map(beforeRows.map((row, index) => [keyOf(row, index), row]));
  const afterByKey = new Map(
    afterRows.map((row, index) => [keyOf(row, index), { row, index }]),
  );

  const cellChanges: TableCellChange[] = [];
  for (const [key, { row: afterRow, index }] of afterByKey) {
    const beforeRow = beforeByKey.get(key);
    if (beforeRow === undefined) continue;
    const beforeRecord = toRowRecord(beforeRow);
    const afterRecord = toRowRecord(afterRow);
    const rowLabel = rowDisplayLabel(beforeRow, index);
    const columns = new Set([...Object.keys(beforeRecord), ...Object.keys(afterRecord)]);
    for (const column of columns) {
      if (isInternalKey(column)) continue;
      const beforeValue = beforeRecord[column];
      const afterValue = afterRecord[column];
      if (JSON.stringify(beforeValue) === JSON.stringify(afterValue)) continue;
      cellChanges.push({ rowLabel, column, before: beforeValue, after: afterValue });
    }
  }

  const addedRows: TableRowDetail[] = [];
  for (const [key, { row }] of afterByKey) {
    if (!beforeByKey.has(key)) addedRows.push(toRowDetail(row));
  }
  const removedRows: TableRowDetail[] = [];
  for (const [key, row] of beforeByKey) {
    if (!afterByKey.has(key)) removedRows.push(toRowDetail(row));
  }

  return { addedRows, removedRows, cellChanges };
}

export function summarizeTableChange({ addedRows, removedRows, cellChanges }: TableChange): string {
  const parts: string[] = [];
  const added = addedRows.length;
  const removed = removedRows.length;
  if (added) parts.push(`${added} row${added === 1 ? '' : 's'} added`);
  if (removed) parts.push(`${removed} row${removed === 1 ? '' : 's'} removed`);
  if (cellChanges.length) {
    parts.push(`${cellChanges.length} cell${cellChanges.length === 1 ? '' : 's'} changed`);
  }
  return parts.length ? parts.join(' · ') : 'Table data changed';
}

export function formatFieldValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export function formatFieldLabel(fieldKey: string): string {
  const spaced = fieldKey.replace(/[_-]+/g, ' ').trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export function toDateParam(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}
