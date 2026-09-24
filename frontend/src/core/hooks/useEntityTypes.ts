/**
 * Entity Types Hook
 *
 * Provides access to entity type definitions from the configuration-driven
 * entity registry. Use this hook to get available entity types for navigation,
 * check feature flags, and access entity type metadata.
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { STATE_MACHINES_CHANGED_EVENT } from '../events';
import { entityTypes as entityTypesApi } from '../services/api';
import type {
  EntityType,
  EntityTypeSummary,
  EntityTypeFeatures,
} from '../types';

function toEntityTypeSummary(entityType: EntityType): EntityTypeSummary {
  return {
    id: entityType.id,
    name: entityType.name,
    display_name: entityType.display_name,
    icon: entityType.icon,
    color: entityType.color,
    features: entityType.features,
  };
}

interface UseEntityTypesResult {
  /** All entity types (full details) */
  entityTypes: EntityType[];
  /** Entity type summaries (for navigation/dropdowns) */
  summaries: EntityTypeSummary[];
  /** Loading state */
  loading: boolean;
  /** Error message if failed to load */
  error: string | null;
  /** Refresh entity types from API */
  refetch: () => Promise<void>;
  /** Get entity type by name */
  getEntityType: (name: string) => EntityType | undefined;
  /** Get entity type summary by name */
  getSummary: (name: string) => EntityTypeSummary | undefined;
  /** Check if an entity type has a specific feature */
  hasFeature: (typeName: string, feature: keyof EntityTypeFeatures) => boolean;
  /** Get display name for an entity type */
  getDisplayName: (name: string) => string;
  /** Get icon for an entity type */
  getIcon: (name: string) => string | null;
  /** Get color for an entity type */
  getColor: (name: string) => string | null;
  /** Entity types that should appear in navigation (have forms or lifecycle) */
  navEntityTypes: EntityTypeSummary[];
}

export function useEntityTypes(): UseEntityTypesResult {
  const [entityTypes, setEntityTypes] = useState<EntityType[]>([]);
  const [summaries, setSummaries] = useState<EntityTypeSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchEntityTypes = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const listResponse = await entityTypesApi.list();
      setEntityTypes(listResponse.items);
      setSummaries(listResponse.items.map(toEntityTypeSummary));
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Failed to load entity types';
      setError(message);
      console.error('Failed to fetch entity types:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEntityTypes();
    // Publishing a workflow can create a new entity type; refetch so it appears
    // (in nav/records) without a manual page refresh (STAT-424). Reuses the
    // existing state-machines-changed event, mirroring useWorkflows.
    const onChange = () => void fetchEntityTypes();
    window.addEventListener(STATE_MACHINES_CHANGED_EVENT, onChange);
    return () => window.removeEventListener(STATE_MACHINES_CHANGED_EVENT, onChange);
  }, [fetchEntityTypes]);

  const getEntityType = useCallback(
    (name: string): EntityType | undefined => {
      // Handle namespaced names like "ATS.Candidate" -> "Candidate"
      const simpleName = name.includes('.') ? name.split('.').pop() : name;
      return entityTypes.find(
        (et) => et.name === name || et.name === simpleName
      );
    },
    [entityTypes]
  );

  const getSummary = useCallback(
    (name: string): EntityTypeSummary | undefined => {
      const simpleName = name.includes('.') ? name.split('.').pop() : name;
      return summaries.find(
        (s) => s.name === name || s.name === simpleName
      );
    },
    [summaries]
  );

  const hasFeature = useCallback(
    (typeName: string, feature: keyof EntityTypeFeatures): boolean => {
      const entityType = getEntityType(typeName);
      if (!entityType?.features) return false;
      return !!entityType.features[feature];
    },
    [getEntityType]
  );

  const getDisplayName = useCallback(
    (name: string): string => {
      const summary = getSummary(name);
      return summary?.display_name || name;
    },
    [getSummary]
  );

  const getIcon = useCallback(
    (name: string): string | null => {
      const summary = getSummary(name);
      return summary?.icon || null;
    },
    [getSummary]
  );

  const getColor = useCallback(
    (name: string): string | null => {
      const summary = getSummary(name);
      return summary?.color || null;
    },
    [getSummary]
  );

  // Entity types that should appear in navigation
  // (those with forms or lifecycle support)
  const navEntityTypes = useMemo(() => {
    return summaries.filter((s) => {
      if (!s.features) return true; // Include if no features defined
      return s.features.has_form || s.features.has_lifecycle;
    });
  }, [summaries]);

  return {
    entityTypes,
    summaries,
    loading,
    error,
    refetch: fetchEntityTypes,
    getEntityType,
    getSummary,
    hasFeature,
    getDisplayName,
    getIcon,
    getColor,
    navEntityTypes,
  };
}
