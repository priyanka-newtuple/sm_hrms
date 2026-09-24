/**
 * Skin Context Provider
 *
 * Provides skin configuration to all components via React Context.
 * Fetches state machine definitions and derives pipeline stages dynamically.
 */

import { createContext, useContext, useState, useEffect, useCallback, useMemo, type ReactNode } from 'react';
import type {
  SkinManifest,
  StageConfig,
  EntityTypeConfig,
  EntityViewConfig,
  StateMachineDefinition,
} from './types';
import { skin as defaultSkin } from './skin.config';
import { SKIN_REGISTRY } from './registry';
import type { StateMachineRecord } from '../core/types';
import {
  useStateMachinesList,
  useInvalidateStateMachinesList,
} from '../core/hooks/useStateMachinesList';
import { getAccessToken } from '../core/auth/api';

/** Context value shape */
interface SkinContextValue {
  /** Current skin manifest */
  skin: SkinManifest;
  /** Derived pipeline stages from state machine (or fallback) */
  pipelineStages: StageConfig[];
  /** Derived transition triggers: { [fromState]: { [toState]: triggerName } } */
  transitionTriggers: Record<string, Record<string, string>>;
  /** Full state machine definition (if loaded) */
  stateMachineDefinition: StateMachineDefinition | null;
  /** Loading state for async operations */
  loading: boolean;
  /** Error state */
  error: string | null;
  /** Helper to get entity config by type */
  getEntityConfig: (entityType: string) => EntityTypeConfig | undefined;
  /** Helper to get entity view config by type */
  getEntityView: (entityType: string) => EntityViewConfig | undefined;
  /** Helper to get static list by name */
  getStaticList: (listName: string) => string[];
}

const SkinContext = createContext<SkinContextValue | null>(null);

const ACTIVE_SKIN_ID = import.meta.env.VITE_SKIN_ID ?? defaultSkin.id;

interface SkinProviderProps {
  /** Skin ID to use — must match a key in the SKINS registry (default: 'state-machine') */
  skinId?: string;
  children: ReactNode;
}

/**
 * Format state name as a human-readable label
 * e.g., "SCREENING" -> "Screening", "BGV" -> "BGV"
 */
function formatStateLabel(state: string): string {
  // Keep short acronyms as-is
  if (state.length <= 3) return state;
  // Title case for longer names
  return state
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

/** Minimal forward-progression triggers derived from the skin's static
 *  fallback stages, used whenever no live state machine is available
 *  (unauthenticated, still loading, or none found for this skin). */
function buildFallbackTriggers(fallbackStages: StageConfig[]): Record<string, Record<string, string>> {
  const triggers: Record<string, Record<string, string>> = {};
  for (let i = 0; i < fallbackStages.length - 1; i++) {
    const from = fallbackStages[i].state;
    const to = fallbackStages[i + 1].state;
    if (!triggers[from]) triggers[from] = {};
    triggers[from][to] = `${from.toLowerCase()}_to_${to.toLowerCase()}`;
  }
  return triggers;
}

function findActiveMachine(
  machines: StateMachineRecord[],
  skin: SkinManifest,
): StateMachineRecord | undefined {
  return machines.find((m) => m.machine_name === skin.board.machineName && m.is_active);
}

interface DerivedSkinData {
  pipelineStages: StageConfig[];
  transitionTriggers: Record<string, Record<string, string>>;
  stateMachineDefinition: StateMachineDefinition | null;
}

/** Derives board stages + transition triggers from the live state machine
 *  definition, falling back to the skin's static config when there's no
 *  active machine for it yet. Pure — callers handle logging/side effects. */
function deriveSkinData(machines: StateMachineRecord[], skin: SkinManifest): DerivedSkinData {
  const activeMachine = findActiveMachine(machines, skin);
  if (!activeMachine) {
    return {
      pipelineStages: skin.board.fallbackStages,
      transitionTriggers: buildFallbackTriggers(skin.board.fallbackStages),
      stateMachineDefinition: null,
    };
  }

  const def = activeMachine.definition as unknown as StateMachineDefinition;

  // The backend may return states as either plain strings or State objects
  // { name, tags, order, ... }. Normalise to a list of { name, tags, order } records.
  type RawState = { name: string; tags?: string[]; order?: number | null };
  const normalizedStates: RawState[] = def.states
    .map((s) => (typeof s === 'string' ? { name: s, tags: [], order: null } : (s as RawState)))
    .filter((s) => typeof s.name === 'string' && s.name.length > 0);

  // Sort by order when present so board columns appear in the right sequence.
  normalizedStates.sort((a, b) => {
    const aOrd = typeof a.order === 'number' ? a.order : Infinity;
    const bOrd = typeof b.order === 'number' ? b.order : Infinity;
    return aOrd - bOrd;
  });

  // Terminal states: union of skin config list and states tagged 'terminal'.
  const terminalStates = new Set([
    ...skin.board.terminalStates,
    ...normalizedStates
      .filter((s) => Array.isArray(s.tags) && s.tags.includes('terminal'))
      .map((s) => s.name),
  ]);

  const pipelineStages: StageConfig[] = normalizedStates
    .filter((s) => !terminalStates.has(s.name))
    .map((s) => ({
      state: s.name,
      label: formatStateLabel(s.name),
      color: skin.board.stateColors[s.name] || '#9ca3af',
    }));

  // Derive transition triggers. The backend serialises fields as either
  // to/from (Pydantic alias) or to_state/from_state (field name). Handle both.
  const transitionTriggers: Record<string, Record<string, string>> = {};
  for (const t of def.transitions) {
    const raw = t as unknown as Record<string, unknown>;
    const toState = (t.to as string | undefined) ?? (raw['to_state'] as string | undefined);
    const fromRaw = (t.from as string | string[] | undefined) ?? (raw['from_state'] as string | undefined);
    if (!toState || !fromRaw) continue;
    const fromStates = Array.isArray(fromRaw) ? (fromRaw as string[]) : [fromRaw as string];
    for (const from of fromStates) {
      if (!from) continue;
      if (!transitionTriggers[from]) transitionTriggers[from] = {};
      transitionTriggers[from][toState] = t.trigger;
    }
  }

  return { pipelineStages, transitionTriggers, stateMachineDefinition: def };
}

export function SkinProvider({ skinId = ACTIVE_SKIN_ID, children }: SkinProviderProps) {
  const skin = SKIN_REGISTRY[skinId] ?? defaultSkin;

  // Bumped whenever the auth token changes (login/logout, same-tab or
  // cross-tab) so `hasToken` below is re-evaluated and the cached list gets
  // invalidated — it may belong to a different actor/org than before.
  const [authTick, setAuthTick] = useState(0);
  const invalidateStateMachines = useInvalidateStateMachinesList();

  useEffect(() => {
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'ats_access_token') setAuthTick((t) => t + 1);
    };
    const handleTokenChange = () => setAuthTick((t) => t + 1);

    window.addEventListener('storage', handleStorageChange);
    window.addEventListener('token-changed', handleTokenChange);
    return () => {
      window.removeEventListener('storage', handleStorageChange);
      window.removeEventListener('token-changed', handleTokenChange);
    };
  }, []);

  useEffect(() => {
    if (authTick > 0) void invalidateStateMachines();
  }, [authTick, invalidateStateMachines]);

  const hasToken = Boolean(getAccessToken());
  const { data: machines, isLoading, error: queryError } = useStateMachinesList(hasToken);

  const derived = useMemo<DerivedSkinData>(() => {
    if (!hasToken || !machines) {
      return {
        pipelineStages: skin.board.fallbackStages,
        transitionTriggers: buildFallbackTriggers(skin.board.fallbackStages),
        stateMachineDefinition: null,
      };
    }
    return deriveSkinData(machines, skin);
  }, [hasToken, machines, skin]);

  // Side-effect logging only — kept out of the pure derivation above.
  useEffect(() => {
    if (hasToken && machines && !findActiveMachine(machines, skin)) {
      console.warn(`No active state machine found for ${skin.board.machineName}, using fallback stages`);
    }
  }, [hasToken, machines, skin]);

  useEffect(() => {
    // Only log/surface fetch errors once authenticated, to avoid spam on the login page.
    if (hasToken && queryError) {
      const message = queryError instanceof Error ? queryError.message : 'Failed to load state machine';
      console.error('Failed to load state machine:', message);
    }
  }, [hasToken, queryError]);

  const { pipelineStages, transitionTriggers, stateMachineDefinition } = derived;
  const loading = hasToken ? isLoading : false;
  const error = hasToken && queryError ? (queryError instanceof Error ? queryError.message : 'Failed to load state machine') : null;

  // Helper functions
  const getEntityConfig = useCallback(
    (entityType: string): EntityTypeConfig | undefined =>
      skin.entityTypes.find((e) => e.entityType === entityType),
    [skin],
  );

  const getEntityView = useCallback(
    (entityType: string): EntityViewConfig | undefined =>
      skin.entityViews.find((e) => e.entityType === entityType),
    [skin],
  );

  const getStaticList = useCallback(
    (listName: string): string[] => skin.staticLists[listName] || [],
    [skin],
  );

  // Every consumer of useSkin() re-renders whenever this object's identity
  // changes — without memoization it's a fresh object on every render of
  // SkinProvider, so any state change anywhere near the app root re-renders
  // the entire tree that reads skin config.
  const value: SkinContextValue = useMemo(
    () => ({
      skin,
      pipelineStages,
      transitionTriggers,
      stateMachineDefinition,
      loading,
      error,
      getEntityConfig,
      getEntityView,
      getStaticList,
    }),
    [
      skin,
      pipelineStages,
      transitionTriggers,
      stateMachineDefinition,
      loading,
      error,
      getEntityConfig,
      getEntityView,
      getStaticList,
    ],
  );

  return <SkinContext.Provider value={value}>{children}</SkinContext.Provider>;
}

/**
 * Hook to access skin configuration
 * Must be used within a SkinProvider
 */
export function useSkin(): SkinContextValue {
  const context = useContext(SkinContext);
  if (!context) {
    throw new Error('useSkin must be used within a SkinProvider');
  }
  return context;
}
