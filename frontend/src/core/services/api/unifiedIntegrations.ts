/**
 * Unified integrations layer: shared by llmConfig, emailConfig, integrations, aiFeatures.
 * Also exports mapper/helper utilities for those consumers.
 */

import type {
  LLMApiKey,
  LLMProvider,
  LLMProvidersListResponse,
  EmailConfig,
  EmailProvider,
  EmailProvidersListResponse,
  IntegrationListResponse,
  IntegrationProvider,
  AvailableModelsResponse,
  ProviderModels,
} from '../../types';
import { request } from './client';
import { resolveOrganizationId } from './internal';

export type UnifiedIntegrationDefinition = {
  provider: string;
  label: string;
  description: string;
  auth_type: string;
  capabilities: string[];
  supports_validate: boolean;
};

export type UnifiedIntegrationDefinitionListResponse = {
  items: UnifiedIntegrationDefinition[];
};

export type UnifiedOrganizationIntegration = {
  organization_id: string;
  provider: string;
  label: string;
  auth_type: string;
  capabilities: string[];
  configured: boolean;
  status: string;
  display_name?: string | null;
  config: Record<string, unknown>;
  secret_hints: Record<string, string>;
  validation_status?: string | null;
  last_validated_at?: string | null;
  last_error?: string | null;
  is_default_for: string[];
};

export type UnifiedOrganizationIntegrationListResponse = {
  organization_id: string;
  items: UnifiedOrganizationIntegration[];
};

export function normalizeLegacyLlmProvider(provider: LLMProvider): string {
  if (provider === 'google') {
    return 'google_gemini';
  }
  return provider;
}

function getFirstSecretHint(secretHints: Record<string, string> | undefined, preferredKeys: string[]): string | null {
  if (!secretHints) {
    return null;
  }
  for (const key of preferredKeys) {
    const value = secretHints[key];
    if (value) {
      return value;
    }
  }
  const firstValue = Object.values(secretHints).find(Boolean);
  return firstValue ?? null;
}

function fallbackTimestamp(value?: string | null): string {
  return value ?? new Date(0).toISOString();
}

export function mapUnifiedIntegrationToLlmApiKey(item: UnifiedOrganizationIntegration): LLMApiKey {
  return {
    id: `${item.organization_id}:${item.provider}`,
    provider: item.provider as LLMProvider,
    display_hint: getFirstSecretHint(item.secret_hints, ['api_key', 'aws_access_key_id']),
    is_active: item.status !== 'disabled' && item.status !== 'revoked',
    validation_status: (item.validation_status as LLMApiKey['validation_status']) ?? null,
    last_validated_at: item.last_validated_at ?? null,
    created_at: fallbackTimestamp(item.last_validated_at),
    updated_at: fallbackTimestamp(item.last_validated_at),
  };
}

export function mapUnifiedDefinitionToLlmProviderInfo(
  definition: UnifiedIntegrationDefinition,
  integration?: UnifiedOrganizationIntegration
): LLMProvidersListResponse['providers'][number] {
  return {
    id: definition.provider === 'google_gemini' ? 'google_gemini' : (definition.provider as LLMProvider),
    name: definition.label,
    description: definition.description,
    configured: Boolean(integration?.configured),
    validation_status: (integration?.validation_status as LLMProvidersListResponse['providers'][number]['validation_status']) ?? null,
  };
}

export function mapUnifiedIntegrationToEmailConfig(item: UnifiedOrganizationIntegration): EmailConfig {
  const config = item.config ?? {};
  return {
    id: `${item.organization_id}:${item.provider}`,
    provider: item.provider as EmailProvider,
    access_key_hint: getFirstSecretHint(item.secret_hints, ['aws_access_key_id', 'username']),
    region: typeof config.region === 'string' ? config.region : null,
    smtp_host: typeof config.smtp_host === 'string' ? config.smtp_host : null,
    smtp_port: typeof config.smtp_port === 'number' ? config.smtp_port : null,
    smtp_use_tls: typeof config.smtp_use_tls === 'boolean' ? config.smtp_use_tls : null,
    from_email: typeof config.from_email === 'string' ? config.from_email : '',
    from_name: typeof config.from_name === 'string' ? config.from_name : null,
    reply_to_email: typeof config.reply_to_email === 'string' ? config.reply_to_email : null,
    is_active: item.status !== 'disabled' && item.status !== 'revoked',
    validation_status: (item.validation_status as EmailConfig['validation_status']) ?? null,
    last_validated_at: item.last_validated_at ?? null,
    created_at: fallbackTimestamp(item.last_validated_at),
    updated_at: fallbackTimestamp(item.last_validated_at),
  };
}

export function mapUnifiedDefinitionToEmailProviderInfo(
  definition: UnifiedIntegrationDefinition,
  integration?: UnifiedOrganizationIntegration
): EmailProvidersListResponse['providers'][number] {
  const config = integration?.config ?? {};
  return {
    id: definition.provider as EmailProvider,
    name: definition.label,
    description: definition.description,
    configured: Boolean(integration?.configured),
    validation_status: (integration?.validation_status as EmailProvidersListResponse['providers'][number]['validation_status']) ?? null,
    from_email: typeof config.from_email === 'string' ? config.from_email : null,
    region: typeof config.region === 'string' ? config.region : null,
    smtp_host: typeof config.smtp_host === 'string' ? config.smtp_host : null,
    smtp_port: typeof config.smtp_port === 'number' ? config.smtp_port : null,
  };
}

function mapUnifiedIntegrationStatusToLegacyStatus(status: string): 'pending' | 'connected' | 'expired' | 'revoked' {
  if (status === 'revoked' || status === 'disabled') {
    return 'revoked';
  }
  if (status === 'expired') {
    return 'expired';
  }
  if (status === 'pending') {
    return 'pending';
  }
  return 'connected';
}

export function mapUnifiedIntegrationToLegacyUserIntegration(item: UnifiedOrganizationIntegration): IntegrationListResponse['integrations'][number] {
  return {
    id: `${item.organization_id}:${item.provider}`,
    user_id: 'modular-settings-user',
    organization_id: item.organization_id,
    provider: item.provider as IntegrationProvider,
    provider_email: typeof item.config?.provider_email === 'string' ? item.config.provider_email : null,
    status: mapUnifiedIntegrationStatusToLegacyStatus(item.status),
    scopes: Array.isArray(item.config?.scopes) ? (item.config.scopes as string[]) : null,
    connected_at: item.last_validated_at ?? null,
    last_used_at: null,
    last_error: item.last_error ?? null,
    last_error_at: item.last_error ? item.last_validated_at ?? null : null,
    created_at: fallbackTimestamp(item.last_validated_at),
    updated_at: fallbackTimestamp(item.last_validated_at),
  };
}

export async function listUnifiedCapabilityDefinitions(capability: string): Promise<UnifiedIntegrationDefinition[]> {
  const response = await unifiedIntegrations.listDefinitions() as UnifiedIntegrationDefinitionListResponse;
  return (response.items ?? []).filter((item) => Array.isArray(item.capabilities) && item.capabilities.includes(capability));
}

export async function listUnifiedCapabilityIntegrations(
  capability: string,
  orgId?: string
): Promise<UnifiedOrganizationIntegration[]> {
  const organizationId = resolveOrganizationId(orgId);
  if (!organizationId) {
    return [];
  }
  const response = await unifiedIntegrations.list(organizationId) as UnifiedOrganizationIntegrationListResponse;
  return (response.items ?? []).filter((item) => Array.isArray(item.capabilities) && item.capabilities.includes(capability));
}

const UNIFIED_LLM_MODELS: Record<string, { provider_name: string; models: Array<{ id: string; name: string }> }> = {
  openai: {
    provider_name: 'OpenAI',
    models: [
      { id: 'gpt-4o', name: 'GPT-4o' },
      { id: 'gpt-4o-mini', name: 'GPT-4o Mini' },
      { id: 'gpt-4.1', name: 'GPT-4.1' },
      { id: 'gpt-4.1-mini', name: 'GPT-4.1 Mini' },
    ],
  },
  anthropic: {
    provider_name: 'Anthropic',
    models: [
      { id: 'claude-3-5-sonnet-latest', name: 'Claude 3.5 Sonnet' },
      { id: 'claude-3-7-sonnet-latest', name: 'Claude 3.7 Sonnet' },
      { id: 'claude-3-5-haiku-latest', name: 'Claude 3.5 Haiku' },
    ],
  },
  google_gemini: {
    provider_name: 'Google Gemini',
    models: [
      { id: 'gemini/gemini-1.5-flash', name: 'Gemini 1.5 Flash' },
      { id: 'gemini/gemini-1.5-pro', name: 'Gemini 1.5 Pro' },
      { id: 'gemini/gemini-2.0-flash', name: 'Gemini 2.0 Flash' },
    ],
  },
  azure_openai: {
    provider_name: 'Azure OpenAI',
    models: [
      { id: 'azure/gpt-4o', name: 'Azure GPT-4o' },
      { id: 'azure/gpt-4.1', name: 'Azure GPT-4.1' },
    ],
  },
  azure_foundry: {
    provider_name: 'Microsoft Foundry',
    models: [],
  },
  aws_bedrock: {
    provider_name: 'AWS Bedrock',
    models: [],
  },
};

export async function getModelsFromUnifiedIntegrations(orgId?: string): Promise<AvailableModelsResponse> {
  if (!orgId) {
    return { providers: [], has_validated_keys: false };
  }

  const result = await unifiedIntegrations.list(orgId);
  const configuredLlmProviders = (result.items ?? []).filter(
    (item: any) =>
      Array.isArray(item.capabilities) &&
      item.capabilities.includes('llm') &&
      item.configured !== false &&
      item.status !== 'error'
  );

  const providers = configuredLlmProviders
    .map((item: any) => {
      const entry = UNIFIED_LLM_MODELS[item.provider];
      if (!entry) return null;
      const configuredDeployment = typeof item.config?.deployment_name === 'string'
        ? item.config.deployment_name.trim()
        : '';
      const models = item.provider === 'azure_foundry' && configuredDeployment
        ? [{ id: `foundry/${configuredDeployment}`, name: configuredDeployment }]
        : entry.models;
      return {
        provider: item.provider as LLMProvider,
        provider_name: entry.provider_name,
        models: models.map((model) => ({
          id: model.id,
          name: model.name,
          max_tokens: null,
          input_cost_per_token: null,
          output_cost_per_token: null,
        })),
      };
    })
    .filter(Boolean) as ProviderModels[];

  return {
    providers,
    has_validated_keys: providers.length > 0,
  };
}

export const unifiedIntegrations = {
  listDefinitions: () =>
    request<any>('/integrations/definitions'),

  list: (organizationId: string) =>
    request<any>(`/integrations/organizations/${organizationId}`),

  get: (organizationId: string, provider: string) =>
    request<any>(`/integrations/organizations/${organizationId}/${provider}`),

  upsert: (organizationId: string, provider: string, data: unknown) =>
    request<any>(`/integrations/organizations/${organizationId}/${provider}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (organizationId: string, provider: string) =>
    request<void>(`/integrations/organizations/${organizationId}/${provider}`, {
      method: 'DELETE',
    }),

  validate: (organizationId: string, provider: string, data: unknown) =>
    request<any>(`/integrations/organizations/${organizationId}/${provider}/validate`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  sendTestEmail: (
    organizationId: string,
    provider: string,
    toEmail: string,
    config?: Record<string, unknown>,
    secrets?: Record<string, string>
  ) =>
    request<{ success: boolean; message: string; message_id?: string | null }>(
      `/integrations/organizations/${organizationId}/${provider}/test-email`,
      {
        method: 'POST',
        body: JSON.stringify({ to_email: toEmail, config: config ?? {}, secrets: secrets ?? {} }),
      }
    ),

  listDefaults: (organizationId: string) =>
    request<any>(`/integrations/organizations/${organizationId}/defaults`),

  setDefault: (organizationId: string, capability: string, provider: string) =>
    request<any>(`/integrations/organizations/${organizationId}/defaults/${capability}`, {
      method: 'PUT',
      body: JSON.stringify({ provider }),
    }),
};
