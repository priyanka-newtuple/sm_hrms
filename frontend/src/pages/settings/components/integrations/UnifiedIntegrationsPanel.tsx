import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, Loader2, PlugZap, RefreshCw, ShieldCheck, Trash2 } from 'lucide-react';

import Badge from '../../../../core/components/Badge';
import { Button } from '@/components/ui/button';
import Modal from '../../../../core/components/Modal';
import { unifiedIntegrations } from '../../../../core/services/api';

type DefinitionField = {
  name: string;
  label: string;
  field_type: string;
  required: boolean;
  secret: boolean;
  help_text?: string | null;
  placeholder?: string | null;
};

type IntegrationDefinition = {
  provider: string;
  label: string;
  description: string;
  auth_type: string;
  capabilities: string[];
  config_fields: DefinitionField[];
  secret_fields: DefinitionField[];
  supports_validate: boolean;
  supports_authorize: boolean;
  supports_callback: boolean;
};

type OrganizationIntegration = {
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

type DefaultsResponse = {
  items: Array<{ capability: string; provider?: string | null }>;
};

const capabilityOrder = ['llm', 'communication', 'storage', 'calendar', 'push_notification'];

function parseBoolean(value: unknown): boolean {
  return value === true || value === 'true' || value === '1';
}

function buildInitialConfig(definition: IntegrationDefinition, integration?: OrganizationIntegration | null) {
  const config: Record<string, unknown> = {};
  for (const field of definition.config_fields) {
    const existing = integration?.config?.[field.name];
    if (field.field_type === 'boolean') {
      config[field.name] = parseBoolean(existing);
    } else {
      config[field.name] = existing ?? '';
    }
  }
  return config;
}

function buildInitialSecrets(definition: IntegrationDefinition) {
  const secrets: Record<string, string> = {};
  for (const field of definition.secret_fields) {
    secrets[field.name] = '';
  }
  return secrets;
}

export default function UnifiedIntegrationsPanel({ organizationId }: { organizationId?: string }) {
  const [definitions, setDefinitions] = useState<IntegrationDefinition[]>([]);
  const [integrations, setIntegrations] = useState<OrganizationIntegration[]>([]);
  const [defaults, setDefaults] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDefinition, setSelectedDefinition] = useState<IntegrationDefinition | null>(null);
  const [displayName, setDisplayName] = useState('');
  const [configValues, setConfigValues] = useState<Record<string, unknown>>({});
  const [secretValues, setSecretValues] = useState<Record<string, string>>({});
  const [validationMessage, setValidationMessage] = useState<string | null>(null);
  const [validationOk, setValidationOk] = useState<boolean | null>(null);
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [setAsDefault, setSetAsDefault] = useState(false);
  const [testEmailTo, setTestEmailTo] = useState('');
  const [sendingTest, setSendingTest] = useState(false);
  const [testMessage, setTestMessage] = useState<string | null>(null);
  const [testOk, setTestOk] = useState<boolean | null>(null);

  const fetchData = useCallback(async () => {
    if (!organizationId) {
      setDefinitions([]);
      setIntegrations([]);
      setDefaults({});
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const [defsResponse, integrationsResponse, defaultsResponse] = await Promise.all([
        unifiedIntegrations.listDefinitions(),
        unifiedIntegrations.list(organizationId),
        unifiedIntegrations.listDefaults(organizationId),
      ]);
      setDefinitions(defsResponse.items ?? []);
      setIntegrations(integrationsResponse.items ?? []);
      const mappedDefaults = Object.fromEntries(
        ((defaultsResponse as DefaultsResponse).items ?? []).map((item) => [item.capability, item.provider ?? ''])
      );
      setDefaults(mappedDefaults);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load unified integrations');
    } finally {
      setLoading(false);
    }
  }, [organizationId]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const integrationsByProvider = useMemo(
    () => new Map(integrations.map((integration) => [integration.provider, integration])),
    [integrations]
  );

  const definitionsByCapability = useMemo(() => {
    const buckets = new Map<string, IntegrationDefinition[]>();
    for (const definition of definitions) {
      for (const capability of definition.capabilities) {
        const list = buckets.get(capability) ?? [];
        list.push(definition);
        buckets.set(capability, list);
      }
    }
    return buckets;
  }, [definitions]);

  const openModal = (definition: IntegrationDefinition) => {
    const integration = integrationsByProvider.get(definition.provider);
    setSelectedDefinition(definition);
    setDisplayName(integration?.display_name ?? '');
    setConfigValues(buildInitialConfig(definition, integration));
    setSecretValues(buildInitialSecrets(definition));
    setSetAsDefault(definition.capabilities.some((capability) => defaults[capability] !== definition.provider));
    setValidationMessage(null);
    setValidationOk(null);
  };

  const closeModal = () => {
    setSelectedDefinition(null);
    setDisplayName('');
    setConfigValues({});
    setSecretValues({});
    setValidationMessage(null);
    setValidationOk(null);
    setSetAsDefault(false);
    setTestEmailTo('');
    setSendingTest(false);
    setTestMessage(null);
    setTestOk(null);
  };

  const handleValidate = async () => {
    if (!organizationId || !selectedDefinition) return;
    try {
      setValidating(true);
      const result = await unifiedIntegrations.validate(organizationId, selectedDefinition.provider, {
        config: configValues,
        secrets: secretValues,
      });
      setValidationOk(Boolean(result.valid));
      setValidationMessage(result.message ?? (result.valid ? 'Validation succeeded' : 'Validation failed'));
    } catch (err) {
      setValidationOk(false);
      setValidationMessage(err instanceof Error ? err.message : 'Validation failed');
    } finally {
      setValidating(false);
    }
  };

  const handleSave = async () => {
    if (!organizationId || !selectedDefinition) return;
    try {
      setSaving(true);
      await unifiedIntegrations.upsert(organizationId, selectedDefinition.provider, {
        display_name: displayName || null,
        config: configValues,
        secrets: secretValues,
        validate: true,
        set_default: setAsDefault,
      });
      closeModal();
      await fetchData();
    } catch (err) {
      setValidationOk(false);
      setValidationMessage(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (provider: string) => {
    if (!organizationId) return;
    try {
      await unifiedIntegrations.delete(organizationId, provider);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed');
    }
  };

  const handleSetDefault = async (capability: string, provider: string) => {
    if (!organizationId) return;
    try {
      await unifiedIntegrations.setDefault(organizationId, capability, provider);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to set default provider');
    }
  };

  const handleSendTestEmail = async () => {
    if (!organizationId || !selectedDefinition || !testEmailTo.trim()) return;
    try {
      setSendingTest(true);
      setTestMessage(null);
      // Send using the values currently in the form (secrets blank on edit fall
      // back to the saved credentials on the backend), so a provider can be
      // tested before it is saved.
      const result = await unifiedIntegrations.sendTestEmail(
        organizationId,
        selectedDefinition.provider,
        testEmailTo.trim(),
        configValues,
        secretValues
      );
      setTestOk(Boolean(result.success));
      setTestMessage(result.message ?? (result.success ? 'Test email sent' : 'Failed to send test email'));
    } catch (err) {
      setTestOk(false);
      setTestMessage(err instanceof Error ? err.message : 'Failed to send test email');
    } finally {
      setSendingTest(false);
    }
  };

  return (
    <section className="rounded-xl border border-border bg-card p-6 shadow-sm">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Unified Integrations</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Org-scoped provider configurations for LLM, communication, storage, calendar, and push notification services.
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => void fetchData()} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
        </Button>
      </div>

      {!organizationId && (
        <div className="rounded-lg border border-warning/30 bg-warning-subtle p-3 text-sm text-warning">
          Select an organization to manage integrations.
        </div>
      )}

      {error && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive-subtle p-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading integrations…
        </div>
      ) : (
        <div className="space-y-6">
          {capabilityOrder.map((capability) => {
            const capabilityDefinitions = definitionsByCapability.get(capability) ?? [];
            if (capabilityDefinitions.length === 0) return null;
            return (
              <div key={capability}>
                <div className="mb-3 flex items-center gap-2">
                  <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">{capability}</h3>
                  {defaults[capability] && <Badge variant="success">Default: {defaults[capability]}</Badge>}
                </div>
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {capabilityDefinitions.map((definition) => {
                    const integration = integrationsByProvider.get(definition.provider);
                    const isDefault = integration?.is_default_for?.includes(capability);
                    return (
                      <div key={definition.provider} className="rounded-xl border border-border p-4">
                        <div className="mb-3 flex items-start justify-between gap-3">
                          <div>
                            <div className="flex items-center gap-2">
                              <PlugZap className="h-4 w-4 text-muted-foreground" />
                              <h4 className="font-medium text-foreground">{definition.label}</h4>
                            </div>
                            <p className="mt-1 text-sm text-muted-foreground">{definition.description}</p>
                          </div>
                          {integration ? (
                            <Badge variant={integration.status === 'error' ? 'error' : 'success'}>
                              {integration.status}
                            </Badge>
                          ) : (
                            <Badge variant="default">Not configured</Badge>
                          )}
                        </div>

                        <div className="mb-4 space-y-2 text-xs text-muted-foreground">
                          <div>Auth: {definition.auth_type}</div>
                          {integration?.validation_status && <div>Validation: {integration.validation_status}</div>}
                          {integration?.last_error && <div className="text-destructive">Error: {integration.last_error}</div>}
                          {integration?.secret_hints && Object.keys(integration.secret_hints).length > 0 && (
                            <div>Secrets: {Object.entries(integration.secret_hints).map(([key, value]) => `${key}=${value}`).join(', ')}</div>
                          )}
                        </div>

                        <div className="flex flex-wrap gap-2">
                          <Button variant="primary" size="sm" onClick={() => openModal(definition)}>
                            {integration ? 'Edit' : 'Configure'}
                          </Button>
                          {integration && !isDefault && (
                            <Button variant="secondary" size="sm" onClick={() => void handleSetDefault(capability, definition.provider)}>
                              <ShieldCheck className="mr-1 h-4 w-4" />
                              Make Default
                            </Button>
                          )}
                          {integration && (
                            <Button variant="ghost" size="sm" onClick={() => void handleDelete(definition.provider)}>
                              <Trash2 className="mr-1 h-4 w-4" />
                              Delete
                            </Button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <Modal open={Boolean(selectedDefinition)} onClose={closeModal} title={selectedDefinition?.label ?? 'Configure Integration'}>
        {selectedDefinition && (
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Display Name</label>
              <input
                className="w-full rounded-lg border border-border px-3 py-2 text-sm"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder={`${selectedDefinition.label} for this org`}
              />
            </div>

            {selectedDefinition.config_fields.map((field) => (
              <div key={field.name}>
                <label className="mb-1 block text-sm font-medium text-foreground">
                  {field.label}
                  {field.required && <span className="ml-1 text-destructive">*</span>}
                </label>
                {field.field_type === 'boolean' ? (
                  <label className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm">
                    <input
                      type="checkbox"
                      checked={Boolean(configValues[field.name])}
                      onChange={(event) => setConfigValues((current) => ({ ...current, [field.name]: event.target.checked }))}
                    />
                    <span>Enabled</span>
                  </label>
                ) : (
                  <>
                    <input
                      type={field.field_type === 'integer' ? 'number' : 'text'}
                      className="w-full rounded-lg border border-border px-3 py-2 text-sm"
                      value={String(configValues[field.name] ?? '')}
                      onChange={(event) =>
                        setConfigValues((current) => ({
                          ...current,
                          [field.name]: field.field_type === 'integer' ? Number(event.target.value) : event.target.value,
                        }))
                      }
                      placeholder={field.placeholder ?? ''}
                    />
                    {field.help_text && <p className="mt-1 text-xs text-muted-foreground">{field.help_text}</p>}
                  </>
                )}
              </div>
            ))}

            {selectedDefinition.secret_fields.map((field) => {
              const existingHint = integrationsByProvider.get(selectedDefinition.provider)?.secret_hints?.[field.name];
              // On edit the secret is never returned (only a masked hint), so
              // it's optional — leaving it blank keeps the saved value.
              const isConfigured = Boolean(integrationsByProvider.get(selectedDefinition.provider)?.configured);
              return (
                <div key={field.name}>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    {field.label}
                    {field.required && !isConfigured && <span className="ml-1 text-destructive">*</span>}
                  </label>
                  <input
                    type="password"
                    className="w-full rounded-lg border border-border px-3 py-2 text-sm"
                    value={secretValues[field.name] ?? ''}
                    onChange={(event) => setSecretValues((current) => ({ ...current, [field.name]: event.target.value }))}
                    placeholder={existingHint ? `Currently ${existingHint}` : field.placeholder ?? ''}
                  />
                  {existingHint ? (
                    <p className="mt-1 text-xs text-muted-foreground">Leave blank to keep the saved value.</p>
                  ) : (
                    field.help_text && <p className="mt-1 text-xs text-muted-foreground">{field.help_text}</p>
                  )}
                </div>
              );
            })}

            <label className="flex items-center gap-2 text-sm text-foreground">
              <input type="checkbox" checked={setAsDefault} onChange={(event) => setSetAsDefault(event.target.checked)} />
              Set as default provider for supported capabilities
            </label>

            {selectedDefinition.capabilities.includes('communication') && (
                <div className="rounded-lg border border-border p-3">
                  <label className="mb-1 block text-sm font-medium text-foreground">Send a test email</label>
                  <p className="mb-2 text-xs text-muted-foreground">
                    Sends a test message using the {selectedDefinition.label} details entered above (you can test before saving).
                  </p>
                  <div className="flex gap-2">
                    <input
                      type="email"
                      className="w-full rounded-lg border border-border px-3 py-2 text-sm"
                      value={testEmailTo}
                      onChange={(event) => setTestEmailTo(event.target.value)}
                      placeholder="recipient@example.com"
                    />
                    <Button
                      variant="secondary"
                      onClick={() => void handleSendTestEmail()}
                      disabled={sendingTest || !testEmailTo.trim()}
                    >
                      {sendingTest ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                      Send test
                    </Button>
                  </div>
                  {testMessage && (
                    <div
                      className={`mt-2 flex items-center gap-2 rounded-lg border p-2 text-sm ${
                        testOk ? 'border-success/30 bg-success-subtle text-success' : 'border-destructive/30 bg-destructive-subtle text-destructive'
                      }`}
                    >
                      {testOk ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
                      <span>{testMessage}</span>
                    </div>
                  )}
                </div>
              )}

            {validationMessage && (
              <div
                className={`flex items-center gap-2 rounded-lg border p-3 text-sm ${
                  validationOk ? 'border-success/30 bg-success-subtle text-success' : 'border-destructive/30 bg-destructive-subtle text-destructive'
                }`}
              >
                {validationOk ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
                <span>{validationMessage}</span>
              </div>
            )}

            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={closeModal}>
                Cancel
              </Button>
              {selectedDefinition.supports_validate && (
                <Button variant="secondary" onClick={() => void handleValidate()} disabled={validating}>
                  {validating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Validate
                </Button>
              )}
              <Button variant="primary" onClick={() => void handleSave()} disabled={saving}>
                {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                Save
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </section>
  );
}
