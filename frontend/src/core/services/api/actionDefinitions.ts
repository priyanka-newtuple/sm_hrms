import type { ActionDefinition } from '../../types';
import { request } from './client';

/** API client for action definitions — lists available action types from /action-definitions. */
export const actionDefinitions = {
  list: (): Promise<{ items: ActionDefinition[] }> =>
    request<{ items: ActionDefinition[] }>('/action-definitions'),
};
