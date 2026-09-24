import { useEffect, useState } from 'react';

import { entityTypes as entityTypesApi } from '@/core/services/api';
import type { IdentifierConfig } from '@/core/types';
import {
  hasIdentifierTemplate,
  resolveIdentifierLabel,
  resolveIdentifierRequiredMessage,
} from '@/shared/utils/entityForm';

// TTL bounds staleness after another user (or another tab) edits the template;
// invalidateIdentifierConfigCache gives same-session edits instant effect.
const CACHE_TTL_MS = 60_000;
const cache = new Map<string, { value: IdentifierConfig | null; at: number }>();

function freshEntry(entityTypeName: string): { value: IdentifierConfig | null } | undefined {
  const entry = cache.get(entityTypeName);
  if (!entry) return undefined;
  if (Date.now() - entry.at > CACHE_TTL_MS) {
    cache.delete(entityTypeName);
    return undefined;
  }
  return entry;
}

/** Call after saving/deleting an entity type so open pages refetch the config. */
export function invalidateIdentifierConfigCache(entityTypeName?: string): void {
  if (entityTypeName) cache.delete(entityTypeName);
  else cache.clear();
}

/** Identifier configuration for an entity type name. */
export function useIdentifierConfig(entityTypeName?: string | null) {
  const [config, setConfig] = useState<IdentifierConfig | null>(
    entityTypeName ? freshEntry(entityTypeName)?.value ?? null : null,
  );

  useEffect(() => {
    if (!entityTypeName) {
      setConfig(null);
      return;
    }
    const entry = freshEntry(entityTypeName);
    if (entry) {
      setConfig(entry.value);
      return;
    }

    setConfig(null);
    let cancelled = false;
    entityTypesApi
      .get(entityTypeName)
      .then((entityType) => {
        const next = (entityType.schema_definition ?? null) as IdentifierConfig | null;
        cache.set(entityTypeName, { value: next, at: Date.now() });
        if (!cancelled) setConfig(next);
      })
      .catch(() => {
        if (!cancelled) setConfig(null);
      });
    return () => {
      cancelled = true;
    };
  }, [entityTypeName]);

  const label = resolveIdentifierLabel(config, entityTypeName);
  return {
    config,
    templateMode: hasIdentifierTemplate(config),
    label,
    requiredMessage: resolveIdentifierRequiredMessage(config, label),
  };
}
