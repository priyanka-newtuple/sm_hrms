import type {
  IntegrationProvider,
  IntegrationListResponse,
  GoogleCalendarAuthUrl,
  GoogleCalendarCallbackRequest,
  IntegrationConnectResponse,
} from '../../types';
import { request } from './client';
import { requireOrganizationId } from './internal';
import {
  listUnifiedCapabilityIntegrations,
  mapUnifiedIntegrationToLegacyUserIntegration,
  unifiedIntegrations,
} from './unifiedIntegrations';

export const integrations = {
  list: async (orgId?: string): Promise<IntegrationListResponse> => {
    const integrations = await listUnifiedCapabilityIntegrations('calendar', orgId);
    return {
      integrations: integrations
        .filter((item) => item.provider === 'google_calendar')
        .map(mapUnifiedIntegrationToLegacyUserIntegration),
    };
  },

  getGoogleCalendarAuthUrl: () =>
    request<GoogleCalendarAuthUrl>('/integrations/google-calendar/auth-url'),

  googleCalendarCallback: (data: GoogleCalendarCallbackRequest) =>
    request<IntegrationConnectResponse>('/integrations/google-calendar/callback', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  disconnect: async (provider: IntegrationProvider, orgId?: string) => {
    const organizationId = requireOrganizationId(orgId, 'Calendar integration');
    await unifiedIntegrations.delete(organizationId, provider);
    return { success: true, message: 'Integration disconnected' };
  },
};
