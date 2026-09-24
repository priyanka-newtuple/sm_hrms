import type {
  AIFeature,
  AIFeatureListResponse,
  AIFeatureConfigRead,
  AIFeatureConfigCreate,
  AvailableModelsResponse,
} from '../../types';
import { request } from './client';
import { buildOrgQuery, resolveOrganizationId } from './internal';
import { getModelsFromUnifiedIntegrations } from './unifiedIntegrations';

export const aiFeatures = {
  list: (orgId?: string) =>
    request<AIFeatureListResponse>(`/config/ai-features${buildOrgQuery(orgId)}`),

  getModels: async (orgId?: string) => {
    const organizationId = resolveOrganizationId(orgId);
    try {
      if (organizationId) {
        return await request<AvailableModelsResponse>(
          `/llm/models?organization_id=${encodeURIComponent(organizationId)}`
        );
      }
      return await request<AvailableModelsResponse>(`/config/ai-features/models${buildOrgQuery(orgId)}`);
    } catch (error) {
      const status = (error as Error & { status?: number }).status;
      if (status === 404) {
        return getModelsFromUnifiedIntegrations(orgId);
      }
      throw error;
    }
  },

  get: (feature: AIFeature, orgId?: string) =>
    request<AIFeatureConfigRead>(`/config/ai-features/${feature}${buildOrgQuery(orgId)}`),

  update: (feature: AIFeature, data: AIFeatureConfigCreate, orgId?: string) =>
    request<AIFeatureConfigRead>(`/config/ai-features/${feature}${buildOrgQuery(orgId)}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (feature: AIFeature, orgId?: string) =>
    request<{ message: string }>(`/config/ai-features/${feature}${buildOrgQuery(orgId)}`, {
      method: 'DELETE',
    }),
};
