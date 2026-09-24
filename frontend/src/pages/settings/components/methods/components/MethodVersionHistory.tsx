import { useCallback, useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, Clock3, Copy, Loader2, Search } from 'lucide-react';
import Modal from '@/core/components/Modal';
import { Button } from '@/components/ui/button';
import { methodLibrary, users } from '@/core/services/api';
import { getApiErrorMessage } from '@/core/services/api/client';
import type { MethodIdentity, MethodVersion } from '@/core/types';

const PAGE_SIZE = 10;

interface MethodVersionHistoryProps {
  open: boolean;
  onClose: () => void;
  method: MethodIdentity;
  canWrite: boolean;
  onCloneVersion: (version: MethodVersion) => void;
  entityLabel?: string;
  codePrefix?: string;
}

function formatActor(actor: string | null | undefined, userNames: Map<string, string>): string {
  if (!actor?.trim()) return 'System';
  return userNames.get(actor) ?? 'Unknown user';
}

function matchesSearch(
  method: MethodIdentity,
  version: MethodVersion,
  query: string,
  userNames: Map<string, string>,
): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return true;
  return [
    method.name,
    method.category_name ?? '',
    `v${version.version}`,
    version.version_id,
    version.is_latest ? 'current latest' : 'previous version',
    version.created_by ?? '',
    version.created_by ? userNames.get(version.created_by) ?? '' : '',
  ].some((value) => value.toLowerCase().includes(normalized));
}

export default function MethodVersionHistory({
  open,
  onClose,
  method,
  canWrite,
  onCloneVersion,
  entityLabel = 'Form',
  codePrefix = 'FR',
}: MethodVersionHistoryProps) {
  const [items, setItems] = useState<MethodVersion[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState('');
  const [userNames, setUserNames] = useState<Map<string, string>>(new Map());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadVersions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const userListPromise = users.list().catch(() => []);
      const pageSize = 200;
      let nextOffset = 0;
      let allItems: MethodVersion[] = [];
      let expectedTotal = 0;
      do {
        const response = await methodLibrary.listVersions(method.method_id, {
          limit: pageSize,
          offset: nextOffset,
        });
        allItems = [...allItems, ...response.items];
        expectedTotal = response.total;
        if (response.items.length === 0) break;
        nextOffset += response.items.length;
      } while (nextOffset < expectedTotal);
      setItems(allItems);
      setTotal(expectedTotal);
      const userList = await userListPromise;
      setUserNames(new Map(userList.map((user) => [
        user.id,
        user.full_name?.trim() || user.email || user.id,
      ])));
    } catch (err) {
      setError(
        getApiErrorMessage(err, `Failed to load ${entityLabel.toLowerCase()} history`),
      );
    } finally {
      setLoading(false);
    }
  }, [entityLabel, method.method_id]);

  useEffect(() => {
    if (open) void loadVersions();
  }, [open, loadVersions]);

  useEffect(() => {
    if (!open) {
      setSearch('');
      setOffset(0);
    }
  }, [open]);

  useEffect(() => {
    setOffset(0);
  }, [search]);

  const filteredItems = useMemo(
    () => items.filter((version) => matchesSearch(method, version, search, userNames)),
    [items, method, search, userNames],
  );
  const visibleItems = useMemo(
    () => filteredItems.slice(offset, offset + PAGE_SIZE),
    [filteredItems, offset],
  );

  const pageStart = filteredItems.length === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + PAGE_SIZE, filteredItems.length);

  return (
    <Modal open={open} onClose={onClose} title={`${method.name} · ${entityLabel} version history`} size="xl">
      <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span className="rounded bg-muted px-1.5 py-0.5 font-mono">
          {codePrefix}-{String(method.method_code).padStart(2, '0')}
        </span>
        <span>{total} version{total === 1 ? '' : 's'}</span>
        {method.category_name && <span>· {method.category_name}</span>}
      </div>

      {total > 1 && (
        <div className="relative mb-3 max-w-sm">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search versions…"
            className="h-8 w-full rounded-lg border border-border bg-card pl-8 pr-2 text-xs focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20"
          />
        </div>
      )}

      {error && (
        <div className="mb-3 rounded-lg border border-destructive/30 bg-destructive-subtle p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading versions…
        </div>
      ) : visibleItems.length === 0 ? (
        <p className="py-8 text-sm text-muted-foreground">
          {search ? `No versions match "${search}".` : 'No version history yet.'}
        </p>
      ) : (
        <div className="relative">
          <div className="absolute bottom-5 left-[7px] top-5 w-px bg-gradient-to-b from-primary/60 via-border to-border" />
          <ol className="space-y-3">
            {visibleItems.map((version) => (
              <li key={version.version_id} className="relative pl-6">
                <span
                  className={`absolute left-0 top-4 h-3.5 w-3.5 rounded-full border-2 border-card ${
                    version.is_latest
                      ? 'bg-primary ring-4 ring-primary/10'
                      : 'bg-muted-foreground/50'
                  }`}
                />
                <div
                  className={`rounded-lg border p-3 transition-colors ${
                    version.is_latest
                      ? 'border-primary/30 bg-primary/[0.03] shadow-sm'
                      : 'border-border bg-card hover:border-primary/20'
                  }`}
                >
                  <div className="mb-3 flex items-center justify-between gap-3 border-b border-border/70 pb-2">
                    <div>
                      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                        Version
                      </div>
                      <div className="font-mono text-sm font-semibold text-foreground">
                        v{version.version}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                        Status
                      </div>
                      <div
                        className={`text-xs font-semibold ${
                          version.is_latest ? 'text-primary' : 'text-muted-foreground'
                        }`}
                      >
                        {version.is_latest ? 'Current' : 'Previous version'}
                      </div>
                    </div>
                  </div>

                  <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
                    <div className="grid grid-cols-[minmax(120px,auto)_minmax(0,1fr)] gap-3 border-b border-border/60 pb-2">
                      <dt className="text-xs font-medium text-muted-foreground">{entityLabel}</dt>
                      <dd className="min-w-0 break-words text-xs text-foreground">{method.name}</dd>
                    </div>
                    <div className="grid grid-cols-[minmax(120px,auto)_minmax(0,1fr)] gap-3 border-b border-border/60 pb-2">
                      <dt className="text-xs font-medium text-muted-foreground">Created by / Updated by</dt>
                      <dd className="min-w-0 break-words text-xs text-foreground">{formatActor(version.created_by, userNames)}</dd>
                    </div>
                    <div className="grid grid-cols-[minmax(120px,auto)_minmax(0,1fr)] gap-3 border-b border-border/60 pb-2">
                      <dt className="text-xs font-medium text-muted-foreground">Version ID</dt>
                      <dd className="min-w-0 break-all font-mono text-[11px] text-foreground">{version.version_id}</dd>
                    </div>
                  </dl>

                  {canWrite && (
                    <div className="mt-3 flex justify-end">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => onCloneVersion(version)}
                        icon={<Copy className="h-3.5 w-3.5" />}
                      >
                        Clone this version
                      </Button>
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}

      {filteredItems.length > PAGE_SIZE && (
        <div className="mt-4 flex items-center justify-between border-t border-border pt-3 text-xs text-muted-foreground">
          <span>{pageStart}–{pageEnd} of {filteredItems.length}</span>
          <div className="flex items-center gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              disabled={offset === 0 || loading}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              title="Previous page"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              disabled={offset + PAGE_SIZE >= filteredItems.length || loading}
              onClick={() => setOffset(offset + PAGE_SIZE)}
              title="Next page"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      <div className="mt-4 flex items-center gap-2 border-t border-border pt-3 text-[11px] text-muted-foreground">
        <Clock3 className="h-3.5 w-3.5" />
        {entityLabel} item list changes create a new {entityLabel.toLowerCase()} version; metadata edits stay on the live {entityLabel.toLowerCase()}.
      </div>
    </Modal>
  );
}
