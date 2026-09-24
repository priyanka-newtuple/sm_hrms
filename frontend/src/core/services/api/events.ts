import type { EntityEvent, AuditEventListResponse } from '../../types';
import { request } from './client';

export const events = {
  list: (entityId: string) =>
    request<EntityEvent[]>(`/entities/${entityId}/events`),

  /** Fetch the activity timeline for an entity from the unified audit log endpoint. */
  listActivity: (
    entityId: string,
    params: { limit?: number; offset?: number; event_type?: string; metadata_type?: string } = {}
  ): Promise<AuditEventListResponse> => {
    const { limit = 50, offset = 0, event_type, metadata_type } = params;
    const qs = new URLSearchParams({ entity_id: entityId, limit: String(limit), offset: String(offset) });
    if (event_type) qs.set('event_type', event_type);
    if (metadata_type) qs.set('metadata_type', metadata_type);
    return request<AuditEventListResponse>(`/audit-events?${qs.toString()}`);
  },

  /** Org-wide record change history for the Logs page. Requires `logs:read`. */
  listFieldChanges: (
    params: {
      user_id?: string;
      date_from?: string;
      date_to?: string;
      limit?: number;
      offset?: number;
    } = {},
  ): Promise<AuditEventListResponse> => {
    const { user_id, date_from, date_to, limit = 50, offset = 0 } = params;
    const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (user_id) qs.set('user_id', user_id);
    if (date_from) qs.set('date_from', date_from);
    if (date_to) qs.set('date_to', date_to);
    return request<AuditEventListResponse>(`/audit-events/field-changes?${qs.toString()}`);
  },

  listUserActionActivity: (
    params: {
      user_id: string;
      event_type: string;
      date_from?: string;
      date_to?: string;
      limit?: number;
      offset?: number;
    },
  ): Promise<AuditEventListResponse> => {
    const { user_id, event_type, date_from, date_to, limit = 50, offset = 0 } = params;
    const qs = new URLSearchParams({
      user_id,
      event_type,
      limit: String(limit),
      offset: String(offset),
    });
    if (date_from) qs.set('date_from', date_from);
    if (date_to) qs.set('date_to', date_to);
    return request<AuditEventListResponse>(`/audit-events?${qs.toString()}`);
  },
};
