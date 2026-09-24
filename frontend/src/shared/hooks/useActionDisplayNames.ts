import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import {
  actionDefinitions,
  agent,
  connectors,
  emailTemplates,
  schedules,
} from '@/core/services/api';
import { humanize } from '@/shared/utils/labels';

const CACHE_TTL_MS = 5 * 60_000;

export interface ActionDisplaySource {
  kind?: string;
  config?: Record<string, unknown>;
  actionDisplayName?: string;
  connectorId?: string;
}

const text = (value: unknown): string =>
  typeof value === 'string' ? value.trim() : '';

const firstText = (...values: unknown[]): string =>
  values.map(text).find(Boolean) ?? '';

const stringArray = (value: unknown): string[] =>
  Array.isArray(value) ? value.map(text).filter(Boolean) : [];

function configuredName(config: Record<string, unknown> | undefined): string {
  if (!config) return '';
  return firstText(
    config.action_display_name,
    config.action_name,
    config.display_name,
    config.name,
    config.label,
  );
}

/** Returns a resolver: given an action's `{ kind, config }`, produces its display
 *  name from cached connector/agent/template/schedule data, else the humanized kind. */
export function useActionDisplayNames() {
  const connectorsQuery = useQuery({
    queryKey: ['actionDisplayNames', 'connectors'],
    queryFn: () => connectors.list(),
    staleTime: CACHE_TTL_MS,
    retry: false,
  });

  const definitionsQuery = useQuery({
    queryKey: ['actionDisplayNames', 'definitions'],
    queryFn: () => actionDefinitions.list(),
    staleTime: CACHE_TTL_MS,
    retry: false,
  });

  const templatesQuery = useQuery({
    queryKey: ['actionDisplayNames', 'emailTemplates'],
    queryFn: () => emailTemplates.list(),
    staleTime: CACHE_TTL_MS,
    retry: false,
  });

  const agentsQuery = useQuery({
    queryKey: ['actionDisplayNames', 'agents'],
    queryFn: () => agent.listDefinitions(true),
    staleTime: CACHE_TTL_MS,
    retry: false,
  });

  const schedulesQuery = useQuery({
    queryKey: ['actionDisplayNames', 'schedules'],
    queryFn: () => schedules.list(),
    staleTime: CACHE_TTL_MS,
    retry: false,
  });

  const connectorNames = useMemo(
    () => new Map((connectorsQuery.data?.items ?? []).map((item) => [item.id, item.name])),
    [connectorsQuery.data?.items],
  );
  const definitionNames = useMemo(
    () => new Map((definitionsQuery.data?.items ?? []).map((item) => [item.kind, item.name])),
    [definitionsQuery.data?.items],
  );
  const templateNames = useMemo(
    () => new Map((templatesQuery.data?.items ?? []).map((item) => [item.template_id, item.name])),
    [templatesQuery.data?.items],
  );
  const agentNames = useMemo(
    () => new Map((agentsQuery.data ?? []).map((item) => [item.definition_id, item.display_name || item.name])),
    [agentsQuery.data],
  );
  const scheduleNames = useMemo(
    () => new Map((schedulesQuery.data?.items ?? []).map((item) => [item.schedule_id, item.name])),
    [schedulesQuery.data?.items],
  );

  return useMemo(
    () => (source: ActionDisplaySource): string => {
      const config = source.config;
      const explicit = source.actionDisplayName || configuredName(config);
      if (explicit) return explicit;

      const connectorId = source.connectorId || text(config?.connector_id);
      if (connectorId && connectorNames.get(connectorId)) {
        return connectorNames.get(connectorId) as string;
      }

      const templateId = text(config?.template_id);
      if (templateId && templateNames.get(templateId)) {
        return templateNames.get(templateId) as string;
      }

      const agentId = text(config?.agent_id);
      if (agentId && agentNames.get(agentId)) {
        return agentNames.get(agentId) as string;
      }

      const scheduleIds = stringArray(config?.schedule_ids);
      const scheduleId = text(config?.schedule_id);
      const ids = scheduleIds.length > 0 ? scheduleIds : scheduleId ? [scheduleId] : [];
      const names = ids.map((id) => scheduleNames.get(id)).filter((name): name is string => Boolean(name));
      if (names.length === 1) return names[0];
      if (names.length > 1 && names.length === ids.length) return names.join(', ');
      if (ids.length > 1) return `${ids.length} schedules`;

      const trigger = text(config?.trigger);
      if (source.kind === 'signal.fire' && trigger) return `Fire ${humanize(trigger)}`;

      const definitionName = source.kind ? definitionNames.get(source.kind) : '';
      return definitionName || humanize(source.kind);
    },
    [agentNames, connectorNames, definitionNames, scheduleNames, templateNames],
  );
}
