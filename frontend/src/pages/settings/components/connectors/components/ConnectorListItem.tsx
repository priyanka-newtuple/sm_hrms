/** Single row in the connector sidebar list, with inline test/rotate/delete actions. */

import { KeyRound, Trash2, Zap } from 'lucide-react';

import type { Connector } from '../../../../../core/types';

interface ConnectorListItemProps {
  connector: Connector;
  isActive: boolean;
  onSelect: () => void;
  onTest: (e: React.MouseEvent) => void;
  onRotateSecret: () => void;
  onDelete: (e: React.MouseEvent) => void;
}

export default function ConnectorListItem({
  connector: c,
  isActive,
  onSelect,
  onTest,
  onRotateSecret,
  onDelete,
}: ConnectorListItemProps) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onSelect()}
      className={`group w-full cursor-pointer rounded-lg border px-3 py-2.5 text-left transition-colors ${
        isActive
          ? 'border-primary/30 bg-primary/5'
          : 'border-transparent hover:border-border hover:bg-muted/50'
      }`}
    >
      <div className="flex items-start justify-between gap-1">
        <p className={`truncate text-sm font-medium ${isActive ? 'text-primary' : ''}`}>
          {c.name}
        </p>
        <div className="flex shrink-0 items-center gap-0.5 opacity-0 group-hover:opacity-100">
          <button
            type="button"
            title="Test"
            onClick={onTest}
            className="rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <Zap className="h-3 w-3" />
          </button>
          {c.auth_type && !['none', 'custom'].includes(c.auth_type) && (
            <button
              type="button"
              title="Rotate secret"
              onClick={(e) => { e.stopPropagation(); onRotateSecret(); }}
              className="rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <KeyRound className="h-3 w-3" />
            </button>
          )}
          <button
            type="button"
            title="Delete"
            onClick={onDelete}
            className="rounded p-0.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </div>
      </div>
      <p className="truncate font-mono text-[11px] text-muted-foreground">
        {c.method} {c.base_url}
      </p>
      <div className="mt-1 flex flex-wrap gap-1">
        {(c.entity_types ?? []).map((type) => (
          <span key={type} className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
            {type}
          </span>
        ))}
        {c.expose_as_tool && (
          <span className="rounded bg-info-subtle px-1.5 py-0.5 text-[10px] font-medium text-info">
            Tool
          </span>
        )}
        {c.validation_status && (
          <span
            className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
              c.validation_status === 'valid'
                ? 'bg-success-subtle text-success'
                : 'bg-destructive-subtle text-destructive'
            }`}
          >
            {c.validation_status}
          </span>
        )}
      </div>
    </div>
  );
}
