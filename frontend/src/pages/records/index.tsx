import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, UploadCloud } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useEntityStore } from '../../core/stores/entityStore';
import { usePermissions } from '../../core/hooks/usePermissions';
import { useFeatureFlags } from '../../core/hooks/useFeatureFlags';
import { useGlobalEntityFilter } from '../../core/contexts/GlobalEntityFilterContext';
import AccessDenied from '../../core/components/AccessDenied';
import type { EntityType, FormSchema } from '../../core/types';
import RecordsHeader from './components/RecordsHeader';
import RecordsSearchBar from './components/RecordsSearchBar';
import RecordsEmptyState from './components/RecordsEmptyState';
import EntityCard from './components/EntityCard';
import {
  entityTypeCardKey,
  latestEntityTypesByName,
  normalizeRecordEntityType,
} from './components/utils';

interface EntityRow {
  entityType: EntityType;
  schema?: FormSchema;
  count: number;
}

export default function RecordsPage() {
  const { entities, entityTypes, schemas, loading, entityTypesError, fetchAll } = useEntityStore();
  const { activeAnchorEntityId } = useGlobalEntityFilter();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');

  useEffect(() => {
    fetchAll(activeAnchorEntityId);
  }, [activeAnchorEntityId, fetchAll]);

  const rows = useMemo<EntityRow[]>(() => {
    const counts = new Map<string, number>();
    for (const entity of entities) {
      const key = normalizeRecordEntityType(entity.entity_type);
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    const schemasByType = new Map<string, FormSchema>();
    for (const s of schemas) {
      const key = normalizeRecordEntityType(s.entity_type);
      if (!schemasByType.has(key)) schemasByType.set(key, s);
    }
    return latestEntityTypesByName(entityTypes)
      .slice()
      .sort((a, b) => a.name.localeCompare(b.name))
      .map((entityType) => ({
        entityType,
        schema: schemasByType.get(normalizeRecordEntityType(entityType.name)),
        count: counts.get(normalizeRecordEntityType(entityType.name)) ?? 0,
      }));
  }, [entityTypes, schemas, entities]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      ({ entityType, schema }) =>
        entityType.name.toLowerCase().includes(q) ||
        entityType.display_name?.toLowerCase().includes(q) ||
        schema?.name.toLowerCase().includes(q),
    );
  }, [rows, query]);

  const { can, hasPermission } = usePermissions();
  const { bulkImportEnabled } = useFeatureFlags();
  const bulkImportAction = bulkImportEnabled && hasPermission('entity_record:write') ? (
    <Button
      variant="primary"
      size="md"
      onClick={() => navigate('/bulk-import')}
      icon={<UploadCloud />}
    >
      Bulk import
    </Button>
  ) : undefined;

  const permittedRows = useMemo(
    () => rows.filter(({ entityType }) => can('view', entityType.name)),
    [rows, can],
  );

  const visibleFilteredRows = useMemo(
    () => filtered.filter(({ entityType }) => can('view', entityType.name)),
    [filtered, can],
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 text-primary animate-spin" />
      </div>
    );
  }

  if (!loading && permittedRows.length === 0 && rows.length > 0) {
    return (
      <div className="mx-auto max-w-7xl">
        <RecordsHeader action={bulkImportAction} />
        <AccessDenied message="You don't have permission to view any entity types." />
      </div>
    );
  }

  if (entityTypesError && rows.length === 0) {
    return (
      <div className="mx-auto max-w-7xl">
        <RecordsHeader action={bulkImportAction} />
        <div className="rounded-xl border border-border bg-card p-12 text-center">
          <p className="text-foreground font-medium mb-1">Unable to load entity types</p>
          <p className="text-sm text-muted-foreground mb-4">
            Check your connection and try loading the records again.
          </p>
          <Button variant="primary" onClick={() => fetchAll(activeAnchorEntityId)}>
            Retry
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl">
      <RecordsHeader action={bulkImportAction} />
      <RecordsSearchBar value={query} onChange={setQuery} total={visibleFilteredRows.length} />

      {rows.length === 0 ? (
        <RecordsEmptyState onGoToSettings={() => navigate('/settings?tab=entities')} />
      ) : visibleFilteredRows.length === 0 ? (
        <div className="rounded-xl border border-border bg-card p-12 text-center text-sm text-muted-foreground">
          No entities match "{query}".
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {visibleFilteredRows.map(({ entityType, schema, count }) => (
            <EntityCard
              key={entityTypeCardKey(entityType)}
              entityType={entityType}
              schema={schema}
              count={count}
              onOpen={() => navigate(`/records/${encodeURIComponent(entityType.name)}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
