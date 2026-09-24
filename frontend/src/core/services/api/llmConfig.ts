import type {
  LLMApiKey,
  LLMApiKeyListResponse,
  LLMApiKeyCreateRequest,
  LLMApiKeyValidateRequest,
  LLMApiKeyValidateResponse,
  LLMProvider,
  LLMProvidersListResponse,
} from '../../types';
import { requireOrganizationId } from './internal';
import {
  listUnifiedCapabilityDefinitions,
  listUnifiedCapabilityIntegrations,
  mapUnifiedDefinitionToLlmProviderInfo,
  mapUnifiedIntegrationToLlmApiKey,
  normalizeLegacyLlmProvider,
  unifiedIntegrations,
  type UnifiedOrganizationIntegration,
} from './unifiedIntegrations';

export const llmConfig = {
  listProviders: async (orgId?: string): Promise<LLMProvidersListResponse> => {
    const [definitions, integrations] = await Promise.all([
      listUnifiedCapabilityDefinitions('llm'),
      listUnifiedCapabilityIntegrations('llm', orgId),
    ]);
    const integrationsByProvider = new Map(integrations.map((item) => [item.provider, item]));
    return {
      providers: definitions.map((definition) =>
        mapUnifiedDefinitionToLlmProviderInfo(definition, integrationsByProvider.get(definition.provider))
      ),
    };
  },

  list: async (orgId?: string): Promise<LLMApiKeyListResponse> => {
    const integrations = await listUnifiedCapabilityIntegrations('llm', orgId);
    return {
      items: integrations.map(mapUnifiedIntegrationToLlmApiKey),
    };
  },

  save: async (data: LLMApiKeyCreateRequest, orgId?: string): Promise<LLMApiKey> => {
    const organizationId = requireOrganizationId(orgId, 'LLM provider configuration');
    const provider = normalizeLegacyLlmProvider(data.provider);
    const extended = data as LLMApiKeyCreateRequest & Record<string, unknown>;
    let config: Record<string, unknown> = {};
    let secrets: Record<string, unknown> = {};

    if (provider === 'openai' || provider === 'anthropic' || provider === 'google_gemini') {
      secrets = { api_key: data.api_key };
    } else if (provider === 'azure_openai' || provider === 'azure_foundry') {
      config = {
        endpoint: extended.endpoint,
        deployment_name: extended.deployment_name,
      };
      if (provider === 'azure_openai') {
        config.api_version = extended.api_version;
      }
      secrets = { api_key: data.api_key };
    } else if (provider === 'aws_bedrock') {
      config = { region: extended.region, project: extended.project, api_mode: extended.api_mode };
      secrets = {
        api_key: data.api_key,
        aws_access_key_id: extended.aws_access_key_id,
        aws_secret_access_key: extended.aws_secret_access_key,
        aws_session_token: extended.aws_session_token,
      };
    }

    const result = await unifiedIntegrations.upsert(organizationId, provider, {
      config,
      secrets,
      validate: data.validate ?? true,
      set_default: true,
    }) as UnifiedOrganizationIntegration;
    return mapUnifiedIntegrationToLlmApiKey(result);
  },

  delete: async (provider: LLMProvider, orgId?: string): Promise<void> => {
    const organizationId = requireOrganizationId(orgId, 'LLM provider configuration');
    await unifiedIntegrations.delete(organizationId, normalizeLegacyLlmProvider(provider));
  },

  validate: async (data: LLMApiKeyValidateRequest, orgId?: string): Promise<LLMApiKeyValidateResponse> => {
    const organizationId = requireOrganizationId(orgId, 'LLM provider validation');
    const provider = normalizeLegacyLlmProvider(data.provider);
    const extended = data as LLMApiKeyValidateRequest & Record<string, unknown>;
    let config: Record<string, unknown> = {};
    let secrets: Record<string, unknown> = {};

    if (provider === 'openai' || provider === 'anthropic' || provider === 'google_gemini') {
      secrets = { api_key: data.api_key };
    } else if (provider === 'azure_openai' || provider === 'azure_foundry') {
      config = {
        endpoint: extended.endpoint,
        deployment_name: extended.deployment_name,
      };
      if (provider === 'azure_openai') {
        config.api_version = extended.api_version;
      }
      secrets = { api_key: data.api_key };
    } else if (provider === 'aws_bedrock') {
      config = { region: extended.region, project: extended.project, api_mode: extended.api_mode };
      secrets = {
        api_key: data.api_key,
        aws_access_key_id: extended.aws_access_key_id,
        aws_secret_access_key: extended.aws_secret_access_key,
        aws_session_token: extended.aws_session_token,
      };
    }

    return unifiedIntegrations.validate(organizationId, provider, {
      config,
      secrets,
    });
  },
};
